.PHONY: help rules

help:
	@echo "Bakhuis Heishamon rules - Development Commands"
	@echo ""
	@echo "Available commands:"
	@echo "  make rules        - Minify HeishaMon rules"
	@echo "  make comments     - Minify HeishaMon -> only remove comments"

rules:
	@echo "Minifying HeishaMon rules..."
	.venv/bin/python -m heishamon_rules_minify heishamon_rules/heishamon_rules_commented.txt heishamon_rules/heishamon_rules_minified.txt
	@echo "Rules minified successfully!"
	@echo "Input:  heishamon_rules/heishamon_rules_commented.txt"
	@echo "Output: heishamon_rules/heishamon_rules_minified.txt"
	@wc -c heishamon_rules/heishamon_rules_minified.txt | awk '{print "Size:   " $$1 " bytes"}'

comments:
	@echo "Minifying HeishaMon --> only comments..."
	.venv/bin/python -m heishamon_rules_minify -c heishamon_rules/heishamon_rules_commented.txt heishamon_rules/heishamon_rules_minified.txt
	@echo "Rules minified successfully!"
	@echo "Input:  heishamon_rules/heishamon_rules_commented.txt"
	@echo "Output: heishamon_rules/heishamon_rules_minified.txt"
	@wc -c heishamon_rules/heishamon_rules_minified.txt | awk '{print "Size:   " $$1 " bytes"}'
