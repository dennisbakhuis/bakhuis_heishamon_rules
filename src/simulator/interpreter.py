"""
HeishaMon rules interpreter.

Implements a lightweight interpreter for the HeishaMon scripting language.
The language uses:
  #globals   - persistent global variables
  $locals    - local/temporary variables (scoped to current handler)
  @params    - heat pump sensor/actuator parameters
  %datetime  - date/time variables (not used in WDC rules)

Blocks are defined as:
  on <event> then
    <body>
  end

Supported builtins: isset, max, min, ceil, floor, round, setTimer, print
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------

_COMMENT_BLOCK = re.compile(r"--\[\[.*?\]\]", re.DOTALL)
_COMMENT_LINE = re.compile(r"--.*$", re.MULTILINE)

# Variable references in expressions
_VAR_RE = re.compile(
    r"(#[A-Za-z_][A-Za-z0-9_]*"
    r"|\$[A-Za-z_][A-Za-z0-9_]*"
    r"|@[A-Za-z_][A-Za-z0-9_]*"
    r"|%[A-Za-z_][A-Za-z0-9_]*)"
)

# Block header: "on <event> then"
_BLOCK_HEADER = re.compile(r"^on\s+(.+?)\s+then\s*$", re.IGNORECASE)

# Assignment: "#var = expr;" or "$var = expr;" or "@var = expr;"
# Use =(?!=) to avoid matching ==
_ASSIGN_RE = re.compile(
    r"^([#$@%][A-Za-z_][A-Za-z0-9_]*)\s*=(?!=)\s*(.+?);?\s*$",
    re.DOTALL,
)

# Function call (with or without args): "name(args);"
_CALL_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\((.*?)\);?\s*$", re.DOTALL)


def _strip_comments(src: str) -> str:
    src = _COMMENT_BLOCK.sub("", src)
    src = _COMMENT_LINE.sub("", src)
    return src


def _extract_blocks(src: str) -> dict[str, str]:
    """
    Extract all on…end blocks.
    Returns {event_name → body_text}.
    """
    blocks: dict[str, str] = {}
    lines = src.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        m = _BLOCK_HEADER.match(line)
        if m:
            event = m.group(1).strip()
            body_lines: list[str] = []
            i += 1
            depth = 1
            while i < len(lines):
                inner = lines[i].strip()
                if inner.lower() == "end":
                    depth -= 1
                    if depth == 0:
                        break
                # nested if…end increases depth
                if re.match(r"^if\b", inner, re.IGNORECASE):
                    depth += 1
                body_lines.append(lines[i])
                i += 1
            blocks[event] = "\n".join(body_lines)
        i += 1
    return blocks


# ---------------------------------------------------------------------------
# Pre-processing: join multi-line conditions into a single logical line
# ---------------------------------------------------------------------------

def _count_parens(s: str) -> int:
    """Return open-paren depth: positive means unclosed '('."""
    depth = 0
    in_str = False
    for ch in s:
        if ch == "(" and not in_str:
            depth += 1
        elif ch == ")" and not in_str:
            depth -= 1
    return depth


def _preprocess_lines(lines: list[str]) -> list[str]:
    """
    Join multi-line constructs into single logical lines:
      1. if/elseif conditions that span multiple lines (until 'then' at EOL)
      2. Expressions/assignments with unclosed parentheses (until balanced)
    """
    result: list[str] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip() if isinstance(lines[i], str) else lines[i]

        # Join if/elseif that don't end with 'then'
        if re.match(r"^(if|elseif)\b", stripped, re.IGNORECASE):
            while not re.search(r"\bthen\s*$", stripped, re.IGNORECASE):
                if i + 1 >= len(lines):
                    break
                i += 1
                stripped = stripped.rstrip() + " " + (
                    lines[i].strip() if isinstance(lines[i], str) else lines[i]
                )
            result.append(stripped)
            i += 1
            continue

        # Join any line with unclosed parentheses with the next line(s)
        paren_depth = _count_parens(stripped)
        while paren_depth > 0 and i + 1 < len(lines):
            i += 1
            next_stripped = lines[i].strip() if isinstance(lines[i], str) else lines[i]
            stripped = stripped.rstrip() + " " + next_stripped
            paren_depth = _count_parens(stripped)

        result.append(stripped)
        i += 1
    return result


# ---------------------------------------------------------------------------
# Expression translation
# ---------------------------------------------------------------------------

def _translate_expr(expr: str) -> str:
    """
    Translate a HeishaMon expression to Python:
      - Replace && → and, || → or
      - Replace #var / $var / @var / %var with _get('name') calls
    """
    expr = expr.replace("&&", " and ").replace("||", " or ")

    def var_repl(m: re.Match) -> str:
        return f"_get({m.group(1)!r})"

    return _VAR_RE.sub(var_repl, expr)


# ---------------------------------------------------------------------------
# Argument splitting
# ---------------------------------------------------------------------------

def _split_args(raw: str) -> list[str]:
    """
    Split a comma-separated argument list, respecting parentheses nesting.
    E.g. 'max(-3, $x), 1' → ['max(-3, $x)', '1']
    """
    args: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in raw:
        if ch == "(" :
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            args.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        args.append("".join(current).strip())
    return [a for a in args if a]


# ---------------------------------------------------------------------------
# Statement executor
# ---------------------------------------------------------------------------

def _execute_body(body: str, interp: "HeishaMonInterpreter", extra_locals: dict) -> None:
    raw = [l for l in body.splitlines()]
    processed = _preprocess_lines(raw)
    _exec_lines(processed, 0, len(processed), interp, extra_locals)


def _exec_lines(
    lines: list[str],
    start: int,
    end: int,
    interp: "HeishaMonInterpreter",
    extra_locals: dict,
) -> int:
    i = start
    while i < end:
        line = lines[i].strip() if isinstance(lines[i], str) else lines[i]
        if not line:
            i += 1
            continue

        # if / elseif / else / end
        if re.match(r"^if\b", line, re.IGNORECASE):
            i = _exec_if_block(lines, i, end, interp, extra_locals)
            continue

        # Skip bare control keywords that we've already consumed
        if line.lower() in ("end", "else") or re.match(r"^elseif\b", line, re.IGNORECASE):
            i += 1
            continue

        # Assignment: #var = expr;
        assign_m = _ASSIGN_RE.match(line)
        if assign_m:
            target = assign_m.group(1)
            expr_str = assign_m.group(2).strip()
            value = interp._eval(expr_str, extra_locals)
            interp._set(target, value, extra_locals)
            i += 1
            continue

        # Function/builtin call: name(args);
        call_m = _CALL_RE.match(line)
        if call_m:
            fname = call_m.group(1)
            raw_args = call_m.group(2).strip()
            if raw_args:
                arg_strs = _split_args(raw_args)
                arg_vals = [interp._eval(a, extra_locals) for a in arg_strs]
            else:
                arg_vals = []
            interp._call(fname, arg_vals, extra_locals)
            i += 1
            continue

        # Fallback: silently skip unknown statements
        i += 1

    return end


def _exec_if_block(
    lines: list[str],
    start: int,
    end: int,
    interp: "HeishaMonInterpreter",
    extra_locals: dict,
) -> int:
    """
    Parse and execute if/elseif/else/end.
    Returns the line index AFTER the closing 'end'.
    """
    clauses: list[tuple[str | None, list[str]]] = []
    current_cond: str | None = None
    current_body: list[str] = []

    first_line = lines[start].strip() if isinstance(lines[start], str) else lines[start]
    if_m = re.match(r"^if\s+(.+?)\s+then\s*$", first_line, re.IGNORECASE)
    if not if_m:
        return start + 1
    current_cond = if_m.group(1)

    i = start + 1
    depth = 1

    while i < end:
        line = lines[i].strip() if isinstance(lines[i], str) else lines[i]

        # Nested if increases depth
        if re.match(r"^if\b", line, re.IGNORECASE) and depth >= 1:
            if depth > 1:
                current_body.append(lines[i])
            else:
                current_body.append(lines[i])
            depth += 1
            i += 1
            continue

        if depth == 1:
            elif_m = re.match(r"^elseif\s+(.+?)\s+then\s*$", line, re.IGNORECASE)
            if elif_m:
                clauses.append((current_cond, current_body))
                current_cond = elif_m.group(1)
                current_body = []
                i += 1
                continue

            if line.lower() == "else":
                clauses.append((current_cond, current_body))
                current_cond = None
                current_body = []
                i += 1
                continue

            if line.lower() == "end":
                clauses.append((current_cond, current_body))
                i += 1
                break

        else:
            if line.lower() == "end":
                depth -= 1

        current_body.append(lines[i])
        i += 1

    # Execute first matching clause
    for cond, body in clauses:
        if cond is None:
            _exec_lines(body, 0, len(body), interp, extra_locals)
            break
        try:
            result = interp._eval(cond, extra_locals)
            if result:
                _exec_lines(body, 0, len(body), interp, extra_locals)
                break
        except Exception:
            pass

    return i


# ---------------------------------------------------------------------------
# Interpreter
# ---------------------------------------------------------------------------

class HeishaMonInterpreter:
    """
    Lightweight interpreter for HeishaMon WDC rules.

    State namespaces:
      globals_  (#vars) — persistent across events
      hpparams_ (@vars) — heat pump sensors/actuators
      timers_   — scheduled timer intervals set by setTimer()
    """

    def __init__(self) -> None:
        self.globals_: dict[str, Any] = {}
        self.hpparams_: dict[str, Any] = {}
        self.timers_: dict[int, int] = {}
        self._blocks: dict[str, str] = {}
        self._func_params: dict[str, str] = {}  # fname → param_name
        self._timer_log: list[str] = []
        self._print_log: list[str] = []

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_file(self, path: str | Path) -> None:
        src = Path(path).read_text(encoding="utf-8")
        self.load_source(src)

    def load_source(self, src: str) -> None:
        stripped = _strip_comments(src)
        raw_blocks = _extract_blocks(stripped)
        self._blocks = {}
        self._func_params = {}
        for key, body in raw_blocks.items():
            # Check if this is a function with a parameter: name($param)
            m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\((\$[A-Za-z_][A-Za-z0-9_]*)\)$", key)
            if m:
                fname = m.group(1)
                param = m.group(2)
                self._blocks[fname] = body  # store under bare name
                self._func_params[fname] = param
            else:
                self._blocks[key] = body

    # ------------------------------------------------------------------
    # Event firing
    # ------------------------------------------------------------------

    def boot(self) -> None:
        self._fire("System#Boot")

    def fire_timer(self, n: int) -> None:
        self._fire(f"timer={n}")

    def call_function(self, name: str, args: list[Any]) -> None:
        self._call(name, args, {})

    def _fire(self, event: str) -> None:
        body = self._blocks.get(event)
        if body is None:
            raise KeyError(f"No block registered for event: {event!r}")
        _execute_body(body, self, {})

    def _call(self, name: str, args: list[Any], extra_locals: dict) -> None:
        # Builtins first
        if name == "setTimer":
            if len(args) >= 2:
                tid = int(args[0])
                interval = int(args[1])
                self.timers_[tid] = interval
                self._timer_log.append(f"setTimer({tid}, {interval})")
            return
        if name == "print":
            self._print_log.append(str(args[0]) if args else "")
            return

        # User-defined function
        body = self._blocks.get(name)
        if body is None:
            return  # unknown, silently ignore

        fn_locals: dict[str, Any] = {}
        param = self._func_params.get(name)
        if param and args:
            fn_locals[param] = args[0]

        _execute_body(body, self, fn_locals)

    # ------------------------------------------------------------------
    # Variable access
    # ------------------------------------------------------------------

    def _get(self, name: str, extra_locals: dict | None = None) -> Any:
        el = extra_locals or {}
        if name.startswith("$"):
            return el.get(name)
        if name.startswith("#"):
            return self.globals_.get(name)
        if name.startswith("@"):
            return self.hpparams_.get(name)
        return None

    def _set(self, name: str, value: Any, extra_locals: dict) -> None:
        if name.startswith("$"):
            extra_locals[name] = value
        elif name.startswith("#"):
            self.globals_[name] = value
        elif name.startswith("@"):
            self.hpparams_[name] = value

    # ------------------------------------------------------------------
    # Expression evaluation
    # ------------------------------------------------------------------

    def _eval(self, expr: str, extra_locals: dict | None = None) -> Any:
        el = extra_locals if extra_locals is not None else {}
        expr = expr.strip()

        # Fast path: numeric literal
        try:
            return float(expr) if "." in expr else int(expr)
        except ValueError:
            pass

        # Build evaluation namespace
        def _get_var(name: str) -> Any:
            return self._get(name, el)

        ns: dict[str, Any] = {
            "_get": _get_var,
            "isset": lambda v: v is not None,
            "max": max,
            "min": min,
            "ceil": math.ceil,
            "floor": math.floor,
            "round": round,
            "print": lambda v: self._print_log.append(str(v)),
            "setTimer": lambda t, i: self.timers_.update({int(t): int(i)}),
            "True": True,
            "False": False,
            "None": None,
        }

        py_expr = _translate_expr(expr)

        try:
            return eval(py_expr, {"__builtins__": {}}, ns)  # noqa: S307
        except Exception as exc:
            raise RuntimeError(
                f"Failed to eval {expr!r} → {py_expr!r}: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    def set_sensor(self, name: str, value: Any) -> None:
        key = name if name.startswith("@") else f"@{name}"
        self.hpparams_[key] = value

    def set_global(self, name: str, value: Any) -> None:
        key = name if name.startswith("#") else f"#{name}"
        self.globals_[key] = value

    def get_sensor(self, name: str) -> Any:
        key = name if name.startswith("@") else f"@{name}"
        return self.hpparams_.get(key)

    def get_global(self, name: str) -> Any:
        key = name if name.startswith("#") else f"#{name}"
        return self.globals_.get(key)
