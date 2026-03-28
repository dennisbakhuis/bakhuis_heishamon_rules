# Pump Speed Control Strategy

## Overview

Pump speed control (Dutch: **Pompsnelheid regeling**) is a critical aspect of heat pump optimization that balances:

1. **Energy transport capacity**: Sufficient flow to carry heat energy
2. **Noise reduction**: Lower speeds reduce water flow noise in pipes and radiators
3. **Electrical efficiency**: Pumps consume less power at lower speeds (cubic relationship)
4. **System protection**: Adequate flow prevents errors and component damage

This document explains how HeishaMon rules dynamically adjust pump speed based on operating mode and heat demand.

## The Core Principle

The pump speed must be **just high enough** to:
- Transport the required thermal energy (Power = Flow × dT × Specific_Heat)
- Maintain minimum flow requirements for heat pump operation
- Avoid cavitation, air pockets, and error codes

But **not higher**, because:
- Pump power scales with speed³ (doubling speed = 8× power consumption)
- Excess flow creates noise in pipes and radiators
- Turbulent flow reduces overall system efficiency

### Flow Rate Requirements

**Required flow rate depends on heat output:**

```
Flow_Rate (l/min) = Power_Output (kW) × 14.3 / dT (°C)

Where:
  14.3 = Conversion factor (60 sec/min ÷ 4.2 kJ/kg/°C)
  dT = Temperature difference (outlet - inlet)

Example:
  6 kW output at 5°C dT → 6 × 14.3 / 5 = 17.2 l/min
  6 kW output at 7°C dT → 6 × 14.3 / 7 = 12.3 l/min
```

**Key insight**: Higher dT allows lower flow rates for same power.

## Understanding Pump Duty Values

**Important**: The `#MaxPumpDuty` values are **byte values (0-255)**, NOT percentages.

These values are sent directly to the heat pump's pump controller and represent:
- **Range**: 0 to 255 (unsigned 8-bit integer)
- **Meaning**: PWM (Pulse Width Modulation) duty cycle or controller setpoint
- **System-specific**: The relationship between duty value and actual flow rate varies by pump model and system resistance

**Why 140 as maximum in the example?**
- At duty value 140, the pump reaches its practical maximum flow for that specific system
- Higher values (e.g., 200+) may barely increase flow further due to system resistance
- Each system will have a different "effective maximum" duty value
- The value 140 is empirically determined for the BlB4 system, NOT a universal standard

**Common duty value ranges:**
- **Minimum**: 50-80 (minimal circulation, ~6-8 l/min)
- **Low**: 80-100 (quiet operation, ~8-12 l/min)
- **Medium**: 100-120 (moderate flow, ~12-14 l/min)
- **High**: 120-140 (high flow, ~14-16 l/min)
- **Maximum**: 140-180 (DHW mode, ~16-18 l/min)

## Implementation: HeishaMon_Rules_BlB4_commented.txt

The BlB4 implementation provides sophisticated weather-dependent pump control.

### Core Logic (timer=6, lines 305-338)

```lua
on timer=6 then
    setTimer(6, 60);  -- Run this rule every minute

    if #ExternalOverRide < 5 then
        #MaxPumpDuty = 82;  -- Default/baseline duty value

        ************************************************************************
        * CASE 1: DHW (Domestic Hot Water) MODE
        ************************************************************************
        if @ThreeWay_Valve_State then  -- 3-way valve in DHW position

            -- High pump duty for DHW (rapid heat transfer to tank)
            #MaxPumpDuty = 140;  -- Duty value 140 (effective maximum for this system)

            -- Reduce duty at end of DHW run to minimize noise when valve switches
            if (@Sterilization_State == 0 && @DHW_Temp > @DHW_Target_Temp) ||
               (@Sterilization_State && @DHW_Temp > 57) then
                #MaxPumpDuty = #MaxPumpDuty - 10;  -- 140 → 130
            end

        ************************************************************************
        * CASE 2: COOLING MODE
        ************************************************************************
        elseif @Operating_Mode_State then  -- OM = 1 (Cooling)
            #MaxPumpDuty = 92;  -- Fixed duty value for cooling

        ************************************************************************
        * CASE 3: HEATING MODE
        ************************************************************************
        elseif @Heatpump_State then  -- HP is ON

            -- Sub-case 3a: Compressor off, just circulation
            if @Compressor_Freq == 0 && @Defrosting_State != 1 then
                #MaxPumpDuty = 82;  -- Minimal circulation duty

            -- Sub-case 3b: Compressor running - weather-dependent flow
            else
                -- Define flow requirements based on outdoor temperature
                $QFH = 10;   -- Flow at high outdoor temp (l/min)
                $QFL = 16;   -- Flow at low outdoor temp (l/min)
                $tH = 11;    -- High outdoor temp threshold (°C)
                $tL = -3;    -- Low outdoor temp threshold (°C)

                -- Calculate required flow rate
                if #OutsideTemp >= $tH then
                    $MaxPumpFlow = $QFH;  -- 10 l/min when warm

                elseif #OutsideTemp <= $tL then
                    $MaxPumpFlow = $QFL;  -- 16 l/min when cold

                else
                    -- Linear interpolation between the two points
                    $MaxPumpFlow = ceil($QFH +
                        ($tH - #OutsideTemp) * ($QFL - $QFH) / ($tH - $tL));
                end

                -- Error prevention: Increase if flow too low
                if @Pump_Flow > 1 && @Pump_Flow < 8 &&
                   #MaxPumpDuty <= @Max_Pump_Duty then
                    #MaxPumpDuty = @Max_Pump_Duty + 1;  -- Prevent E62 error

                else
                    -- Convert flow rate to pump duty percentage
                    #MaxPumpDuty = 55 + floor($MaxPumpFlow * 3);

                    -- Fine-tune based on actual flow efficiency
                    if (@Pump_Speed / @Pump_Flow) > 145 then
                        if @Pump_Flow > 8 then
                            #MaxPumpDuty = @Max_Pump_Duty - 1;  -- Can reduce
                        else
                            #MaxPumpDuty = @Max_Pump_Duty;  -- Keep current
                        end
                    end
                end
            end
        end

        -- Safety minimum: Never go below 82%
        #MaxPumpDuty = max(#MaxPumpDuty, 82);

        -- Apply setting only when changed
        if @Max_Pump_Duty != #MaxPumpDuty then
            @SetMaxPumpDuty = #MaxPumpDuty;
        end
    end
end
```

## Detailed Analysis by Operating Mode

### Mode 1: DHW (Domestic Hot Water) Production

**Characteristics:**
- 3-way valve diverted to DHW tank
- High power transfer needed (rapid heating)
- Noise less critical (water doesn't flow through radiators)

**Strategy:**
```lua
#MaxPumpDuty = 140  -- Maximum speed (high energy transport)

-- At end of DHW cycle:
if DHW_temp_satisfied then
    #MaxPumpDuty = 130  -- Reduce by 10% to minimize valve switching noise
end
```

**Rationale:**
- **Duty value 140**: Enables rapid DHW heating (typically 6-10 kW) at maximum practical flow
- **Noise tolerance**: Tank heating doesn't create radiator noise
- **End-of-cycle reduction**: Prevents loud "thunk" when 3-way valve returns to heating position
- **Power requirement**: DHW often requires maximum HP output

---

### Mode 2: Cooling

**Characteristics:**
- Lower power output than heating (typically)
- Different flow requirements due to smaller dT
- Fixed strategy (less complex than heating)

**Strategy:**
```lua
#MaxPumpDuty = 92  -- Fixed moderate speed
```

**Rationale:**
- **Duty value 92**: Moderate flow suitable for typical cooling loads
- **Fixed value**: Cooling demand less variable than heating
- **Simpler control**: No weather dependency needed

---

### Mode 3: Heating (Most Complex)

#### 3a: Circulation Mode (Compressor Off)

**Between heating cycles:**
```lua
if @Compressor_Freq == 0 && @Defrosting_State != 1 then
    #MaxPumpDuty = 82  -- Minimal circulation
end
```

**Rationale:**
- **Duty value 82**: Maintains water movement to prevent stratification
- **Noise minimization**: Critical when compressor is silent
- **Energy saving**: No need for high flow without heat production
- **Freeze protection**: Keeps water moving in cold weather

#### 3b: Active Heating (Compressor Running)

**This is where the sophisticated weather-dependent control happens.**

##### Weather-Dependent Flow Curve

The system defines a **flow rate curve** similar to the weather compensation curve:

```
Flow Rate (l/min)
    │
 16 │                              ●  (Point 2: -3°C outdoor, 16 l/min)
    │                            ╱
 14 │                          ╱
    │                        ╱
 12 │                      ╱
    │                    ╱
 10 │              ●                 (Point 1: 11°C outdoor, 10 l/min)
    │
  8 │
    └─────┬─────┬─────┬─────┬─────┬─────┬───── Outside Temp (°C)
         -3    0     3     6     9    11

Cold weather → High flow (more power to transport)
Mild weather → Low flow (less power needed, quieter)
```

##### The Flow Calculation Formula

```lua
-- Define the two reference points
$QFH = 10;   -- Flow at high temp (mild weather)
$QFL = 16;   -- Flow at low temp (cold weather)
$tH = 11;    -- High temp threshold
$tL = -3;    -- Low temp threshold

-- Calculate required flow (linear interpolation)
if outdoor_temp >= $tH then
    required_flow = $QFH

elseif outdoor_temp <= $tL then
    required_flow = $QFL

else
    required_flow = $QFH + (($tH - outdoor_temp) × ($QFL - $QFH) / ($tH - $tL))
end
```

**Example Calculations:**

| Outdoor Temp | Calculation | Flow Rate | Why? |
|--------------|-------------|-----------|------|
| 15°C | Above curve → | 10 l/min | Low heat demand, minimize noise |
| 11°C | At point 1 → | 10 l/min | Mild weather baseline |
| 4°C | Interpolate → 10 + (7×6/14) = 13 l/min | 13 l/min | Medium demand |
| -3°C | At point 2 → | 16 l/min | High heat demand, max flow |
| -10°C | Below curve → | 16 l/min | Maximum flow (safety limit) |

##### Converting Flow Rate to Pump Duty Value

```lua
#MaxPumpDuty = 55 + floor($MaxPumpFlow × 3)
```

This **empirical formula** converts flow rate (l/min) to pump duty value (0-255):

| Flow (l/min) | Calculation | Pump Duty Value | Approximate Flow |
|--------------|-------------|-----------------|------------------|
| 10 | 55 + (10×3) | 85 | ~10 l/min |
| 12 | 55 + (12×3) | 91 | ~12 l/min |
| 14 | 55 + (14×3) | 97 | ~14 l/min |
| 16 | 55 + (16×3) | 103 | ~16 l/min |

**Note**: The constants (55 and 3) are **system-specific** and must be calibrated for each installation:
- Pump characteristics (head/flow curve)
- Pipe diameter and length
- System resistance (bends, valves, radiators)
- Heat exchanger design

**The formula creates a linear mapping:**
- At the author's system: duty value 85 produces ~10 l/min
- At the author's system: duty value 103 produces ~16 l/min
- **Your system will be different** - you must calibrate these constants!

##### Feedback Control: Flow Efficiency Monitoring

```lua
if (@Pump_Speed / @Pump_Flow) > 145 then
    if @Pump_Flow > 8 then
        #MaxPumpDuty = @Max_Pump_Duty - 1  -- Reduce if flow is adequate
    else
        #MaxPumpDuty = @Max_Pump_Duty      -- Keep if flow marginal
    end
end
```

**Purpose**: Optimize pump efficiency by monitoring speed-to-flow ratio.

**Interpretation:**
- **Ratio > 145**: Pump working harder than needed for achieved flow
- **Indicates**: High system resistance or pump oversized for current conditions
- **Action**: Reduce duty slightly if flow is still adequate (>8 l/min)
- **Result**: Lower electrical consumption, less noise

This creates a **feedback loop**:
1. Calculate target flow from outdoor temp
2. Set pump duty based on formula
3. Monitor actual flow achieved
4. Fine-tune duty for optimal efficiency

##### Error Prevention: E62 Protection

```lua
if @Pump_Flow > 1 && @Pump_Flow < 8 && #MaxPumpDuty <= @Max_Pump_Duty then
    #MaxPumpDuty = @Max_Pump_Duty + 1  -- Increase to prevent error
end
```

**E62 Error**: Low water flow alarm (protection against dry running)

**Logic:**
- **Condition**: Flow is between 1-8 l/min (dangerously low)
- **Action**: Incrementally increase pump duty
- **Safety**: Only if not already at maximum
- **Result**: Prevents HP shutdown due to low flow

**Common causes of low flow:**
- Air in system
- Partially closed valves
- Clogged filter
- Pump degradation
- System resistance higher than expected

---

## Visual Flow Chart

```
┌─────────────────────────────────────────────────────────────┐
│              PUMP SPEED CONTROL DECISION TREE               │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ What is HP mode?│
                    └─────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
   ┌─────────┐         ┌─────────┐         ┌──────────┐
   │   DHW   │         │ Cooling │         │  Heating │
   └─────────┘         └─────────┘         └──────────┘
        │                    │                    │
        ▼                    ▼                    ▼
  Set duty=140      Set duty=92      Compressor running?
        │                    │                    │
        │                    │         ┌──────────┴──────────┐
        │                    │         ▼                     ▼
        │                    │      Yes (Heat)            No (Circulate)
        │                    │         │                     │
        │                    │         ▼                     ▼
        │                    │  Calculate flow        Set duty=82
        │                    │  from outdoor temp
        │                    │         │
        │                    │         ▼
        │                    │  Convert to duty value
        │                    │         │
        │                    │         ▼
        │                    │  Check flow adequate?
        │                    │         │
        │                    │   ┌─────┴─────┐
        │                    │   ▼           ▼
        │                    │  Yes         No
        │                    │   │           │
        │                    │   │      Increase duty +1
        │                    │   │           │
        └────────────────────┴───┴───────────┘
                             │
                             ▼
                    Apply #MaxPumpDuty
```

## Why This Matters: Energy and Noise Analysis

### Pump Power Consumption

Pump electrical power follows the **affinity laws** (approximately):

```
Power ∝ Speed³

Note: The relationship between duty value and actual pump speed is system-specific,
but generally higher duty values mean higher power consumption.
```

**Practical Impact (example values for reference):**

| Pump Duty Value | Operating Mode | Approx Power | Daily Cost (€0.30/kWh) |
|-----------------|----------------|--------------|------------------------|
| 140 (DHW) | Hot water heating | ~180W | €1.30 |
| 92 (Cool) | Cooling | ~65W | €0.47 |
| 85 (Heat mild) | Heating (mild weather) | ~52W | €0.37 |
| 82 (Circulate) | Circulation only | ~46W | €0.33 |

**Note**: Actual power consumption depends on your specific pump model and system resistance.

**Annual savings example**: Running at duty value 85 vs 100 for heating season (200 days):
- Approximate power reduction: 100W → 52W = 48W saved
- Hours: 200 days × 12 hrs/day = 2400 hrs
- Energy: 48W × 2400h = 115 kWh
- Cost savings: 115 kWh × €0.30 = **€34.50/year**

### Noise Reduction

Water flow noise is approximately proportional to **velocity²**:

```
Noise ∝ Velocity² ∝ Flow_Rate²

Reducing flow from 16 to 10 l/min:
  Noise reduction ≈ 10²/16² = 0.39
  → Approximately 61% quieter (or about -4 dB)
```

**Perceptual impact:**
- **Duty value 140 (DHW)**: Audible flow noise in pipes
- **Duty value 92 (Cooling)**: Moderate noise, acceptable
- **Duty value 85 (Heating)**: Quiet, barely perceptible
- **Duty value 82 (Circulation)**: Nearly silent

**This is why the BlB4 rules explicitly state:**
> "The main reason for this function is to avoid water running sounds in the piping and radiators."

## Tuning Guidelines

### Step 1: Determine Your Flow Requirements

**Measure your system's flow-to-duty relationship:**

1. Set pump to known duty value (e.g., 100)
2. Read actual flow from HP display (@Pump_Flow)
3. Repeat for several duty values
4. Create a calibration curve

**Example data:**
```
Duty Value 100 → Flow 18 l/min
Duty Value 90  → Flow 15 l/min
Duty Value 80  → Flow 12 l/min
Duty Value 70  → Flow 9 l/min
```

**Important**: Your duty-to-flow relationship will be unique to your system!

### Step 2: Calculate Required Flow Range

**Based on your heat pump capacity:**

```
Max_Flow = Max_Power_kW × 14.3 / Min_dT

Example:
  8 kW heat pump, minimum 4°C dT
  Max_Flow = 8 × 14.3 / 4 = 28.6 l/min

  But if your dT is typically 6°C:
  Typical_Flow = 8 × 14.3 / 6 = 19 l/min
```

### Step 3: Set Flow Curve Parameters

**Adjust the curve points for your system:**

```lua
-- For mild weather (low demand):
$QFH = ?   -- Set to minimum comfortable flow (typically 8-12 l/min)
$tH = ?    -- Outdoor temp where minimum flow is adequate (10-15°C)

-- For cold weather (high demand):
$QFL = ?   -- Set to flow for max power (from Step 2)
$tL = ?    -- Design outdoor temp (your region's minimum)
```

### Step 4: Calibrate Duty Formula

**Adjust the conversion constants:**

```lua
#MaxPumpDuty = A + floor($MaxPumpFlow × B)

Where:
  A = Offset (baseline duty)
  B = Scaling factor (duty per l/min)
```

**To find your A and B:**

1. From your flow-duty measurements (Step 1), find:
   - Flow_Low and corresponding Duty_Low
   - Flow_High and corresponding Duty_High

2. Calculate:
   ```
   B = (Duty_High - Duty_Low) / (Flow_High - Flow_Low)
   A = Duty_Low - (B × Flow_Low)
   ```

**Example:**
```
At 10 l/min → need 85% duty
At 16 l/min → need 103% duty

B = (103 - 85) / (16 - 10) = 18 / 6 = 3
A = 85 - (3 × 10) = 55

Formula: Duty = 55 + floor(Flow × 3)  ← This matches the BlB4 code!
```

### Step 5: Monitor and Optimize

**Key metrics to watch:**

1. **Actual flow achieved** (@Pump_Flow)
   - Should match calculated requirement ±10%
   - If consistently low: increase duty or check for blockages
   - If consistently high: decrease duty to save energy

2. **Temperature differential** (dT = Outlet - Inlet)
   - Target: 4-7°C during heating
   - Too low (<3°C): Flow too high, reduce pump speed
   - Too high (>8°C): Flow too low, increase pump speed

3. **Compressor frequency** (@Compressor_Freq)
   - Should modulate smoothly with load
   - Hunting/cycling: May indicate flow issues

4. **Noise level** (subjective)
   - Listen at pipes, radiators, heat pump
   - Reduce pump duty until barely perceptible
   - Balance against performance requirements

## Advanced: Adaptive Flow Control

Some advanced implementations add **feedback correction**:

```lua
-- Target dT (outlet - inlet difference)
$target_dT = 6;  -- degrees

-- Current dT
$actual_dT = @Main_Outlet_Temp - @Main_Inlet_Temp;

-- If dT too small, reduce flow (reduce pump duty)
if $actual_dT < ($target_dT - 1) then
    #MaxPumpDuty = #MaxPumpDuty - 1;

-- If dT too large, increase flow (increase pump duty)
elseif $actual_dT > ($target_dT + 1) then
    #MaxPumpDuty = #MaxPumpDuty + 1;
end
```

This creates a **cascaded control**:
1. **Primary**: Weather-based feedforward (from outdoor temp)
2. **Secondary**: dT-based feedback (from actual system response)

## Common Issues and Solutions

### Issue 1: E62 Low Flow Error

**Symptoms:**
- Heat pump shuts down
- Error code E62 or similar
- @Pump_Flow < 8 l/min

**Solutions:**
1. Increase `#MaxPumpDuty` baseline (duty value 82 → 90)
2. Check for air in system (bleed radiators)
3. Clean system filter
4. Check for closed/stuck valves
5. Verify pump operation (bearing wear)

### Issue 2: Excessive Noise

**Symptoms:**
- Water rushing sound in pipes/radiators
- Worse at higher outdoor temps (low heat demand)

**Solutions:**
1. Reduce `$QFH` (mild weather flow) from 10 → 8 l/min
2. Lower overall duty: decrease `A` constant in formula
3. Add noise dampers to pipes
4. Adjust thermostatic radiator valves (TRVs)

### Issue 3: Poor Heat Distribution

**Symptoms:**
- Some rooms cold despite HP running
- Large temp differences between flow and return
- Radiators only hot at top

**Solutions:**
1. Increase `$QFL` (cold weather flow) from 16 → 18 l/min
2. Raise overall duty: increase `A` constant
3. Balance radiator system (valve adjustment)
4. Check for blocked pipes or radiators

### Issue 4: High Pump Energy Consumption

**Symptoms:**
- Pump always running at high duty
- High electricity usage from circulation

**Solutions:**
1. Lower both `$QFH` and `$QFL` by 1-2 l/min
2. Reduce `A` constant in duty formula
3. Implement dT-based feedback control
4. Consider system resistance reduction (larger pipes, fewer bends)

## Comparison: Fixed vs. Dynamic Pump Control

### Fixed Speed (Traditional)

```lua
-- Simple approach
#MaxPumpDuty = 100;  -- Always duty value 100
```

**Pros:**
- Simple, no tuning needed
- Guaranteed adequate flow

**Cons:**
- High energy consumption (pump always at same high duty)
- Excessive noise in mild weather
- Wears pump faster
- Suboptimal dT (too low)

**Typical result**: ~100W pump consumption, noisy

---

### Weather-Dependent (BlB4 Implementation)

```lua
-- Sophisticated approach
Flow = f(outdoor_temp)
Duty = g(Flow, actual_flow_feedback)
```

**Pros:**
- 30-50% pump energy savings
- Much quieter operation
- Optimal dT maintained
- Longer pump life
- Better system efficiency

**Cons:**
- Requires tuning for each system
- More complex rules
- Need flow sensor feedback

**Typical result**: ~40-70W pump consumption, quiet

**Important**: The duty values are system-specific byte values (0-255), not universal percentages or standards.

## Integration with Other Controls

Pump speed control works together with:

1. **Weather Compensation**:
   - Low outdoor temp → High water temp + High flow
   - Both scale together with heat demand

2. **Minimum Frequency Operation**:
   - Lower flow can help maintain higher dT
   - Higher dT encourages HP to run at lower frequency
   - Synergistic effect for quiet operation

3. **Room Temperature Control**:
   - If rooms too cold despite adequate flow → increase water temp, not flow
   - If rooms OK but HP cycling → may need flow adjustment

## Conclusion

Effective pump speed control:

✓ **Saves energy**: 30-50% reduction in pump consumption
✓ **Reduces noise**: Quieter operation, especially in mild weather
✓ **Protects system**: Prevents low-flow errors and component damage
✓ **Optimizes efficiency**: Maintains proper dT for HP operation
✓ **Adapts to demand**: Higher flow when needed, lower when possible

**The BlB4 implementation demonstrates a well-balanced approach:**
- Weather-dependent feedforward (anticipates demand)
- Flow feedback monitoring (responds to actual conditions)
- Error prevention logic (protects equipment)
- Mode-specific strategies (DHW, cooling, heating, circulation)

**Key takeaway**: Don't run your pump at a fixed high duty value all the time. Match flow to actual heat transport requirements using outdoor temperature as the primary input, with feedback corrections for optimal efficiency.

**Critical reminder**: Pump duty values (0-255) are **not** percentages or universal standards. The value 140 in the BlB4 example is the empirically-determined practical maximum for that specific system. Your system will have different optimal values that must be calibrated through testing and measurement.
