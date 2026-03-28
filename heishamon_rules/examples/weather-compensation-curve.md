# Weather Compensation Curve (WAR - Weerafhankelijke Regeling)

## Overview

Weather compensation (Dutch: **Weerafhankelijke Regeling** or **WAR**) is a fundamental heating control strategy that automatically adjusts the heat pump's target water temperature based on outdoor temperature. This approach optimizes efficiency and comfort by matching heat output to actual heat loss.

## The Core Principle

The fundamental concept is simple: **the colder it is outside, the higher the water temperature needs to be**.

### Why Weather Compensation?

1. **Heat Loss is Temperature-Dependent**: Buildings lose more heat when it's colder outside
2. **Efficiency Optimization**: Running lower water temperatures when possible improves COP (Coefficient of Performance)
3. **Automatic Adjustment**: No manual intervention needed as weather changes
4. **Comfort**: Maintains consistent indoor temperatures across varying outdoor conditions

### The Linear Relationship

```
High Outside Temp (e.g., 15°C) → Low Water Temp (e.g., 25°C)
Low Outside Temp (e.g., -10°C) → High Water Temp (e.g., 45°C)
```

The relationship between these points forms a **heating curve** or **compensation curve**.

## Mathematical Model

The weather compensation curve is defined by **four parameters** that create two coordinate points:

### Curve Definition Points

```
Point 1 (Mild Weather):
  Tb1 = Outside_High_Temp     (e.g., 15°C - warmest outdoor temp requiring heat)
  Ta1 = Target_Low_Temp       (e.g., 25°C - lowest water temp needed)

Point 2 (Cold Weather):
  Tb2 = Outside_Low_Temp      (e.g., -10°C - design outdoor temperature)
  Ta2 = Target_High_Temp      (e.g., 45°C - highest water temp needed)
```

### The Calculation Formula

```
IF outdoor_temp >= Tb1 THEN
    setpoint = Ta1                    (minimum water temp)

ELSE IF outdoor_temp <= Tb2 THEN
    setpoint = Ta2                    (maximum water temp)

ELSE
    setpoint = Ta1 + ((Tb1 - outdoor_temp) × (Ta2 - Ta1) / (Tb1 - Tb2))
END IF
```

This creates a **linear interpolation** between the two points.

## Implementation Examples

### Example 1: curlymoo_rules.txt

This implementation calculates the weather-compensated setpoint (`#maxTa`) based on the heating curve parameters.

#### Core Logic (lines 104-118)

```lua
on berekenWar then
    if isset(@Outside_Temp) &&
       isset(@Z1_Heat_Curve_Outside_High_Temp) &&
       isset(@Z1_Heat_Curve_Target_Low_Temp) &&
       isset(@Z1_Heat_Curve_Outside_Low_Temp) &&
       isset(@Z1_Heat_Curve_Target_High_Temp) then

        -- Case 1: Outside temp at or above high point (mild weather)
        if @Outside_Temp >= @Z1_Heat_Curve_Outside_High_Temp then
            #maxTa = @Z1_Heat_Curve_Target_Low_Temp;

        -- Case 2: Outside temp at or below low point (very cold)
        else if @Outside_Temp <= @Z1_Heat_Curve_Outside_Low_Temp then
            #maxTa = @Z1_Heat_Curve_Target_High_Temp;

        -- Case 3: Outside temp between the two points (interpolate)
        else
            #maxTa = ceil(
                @Z1_Heat_Curve_Target_Low_Temp +
                ((@Z1_Heat_Curve_Outside_High_Temp - @Outside_Temp) *
                 (@Z1_Heat_Curve_Target_High_Temp - @Z1_Heat_Curve_Target_Low_Temp) /
                 (@Z1_Heat_Curve_Outside_High_Temp - @Z1_Heat_Curve_Outside_Low_Temp))
            );
        end
    end

    stooklijn();  -- Call heating curve adjustment function
end
```

**Trigger Points:**
- Called on `@Main_Outlet_Temp` changes (line 202)
- Called on `@Main_Inlet_Temp` changes (line 207)
- Called every 60 seconds (timer=3, line 247)

**Result:**
- `#maxTa` = Base weather-compensated target temperature
- This value is then adjusted by `#maxShift` for dynamic control

---

### Example 2: HeishaMon_Rules_BlB4_commented.txt

This implementation uses a dedicated timer function and stores the result as `#WCS` (Weather Compensation Setpoint).

#### Core Logic (timer=10, lines 451-461)

```lua
on timer=10 then
    setTimer(10,1800);  -- Run this rule every half hour

    -- Read curve parameters from HP settings
    $Ta1 = @Z1_Heat_Curve_Target_Low_Temp;      -- e.g., 25°C
    $Tb1 = @Z1_Heat_Curve_Outside_High_Temp;    -- e.g., 15°C
    $Ta2 = 34;  -- Hardcoded high target (instead of reading from HP)
    $Tb2 = @Z1_Heat_Curve_Outside_Low_Temp;     -- e.g., -10°C

    -- Case 1: Mild weather (outdoor >= high temp point)
    if #OutsideTemp >= $Tb1 then
        #WCS = $Ta1;

    -- Case 2: Cold weather (outdoor <= low temp point)
    elseif #OutsideTemp <= $Tb2 then
        #WCS = $Ta2;

    -- Case 3: Interpolate between the two points
    else
        #WCS = ceil($Ta1 +
                   (($Tb1 - #OutsideTemp) * ($Ta2 - $Ta1) / ($Tb1 - $Tb2)));
    end
end
```

**Key Differences:**
- Uses smoothed outdoor temp (`#OutsideTemp`) instead of raw `@Outside_Temp`
- Updates every **30 minutes** (not on every temperature change)
- Hardcodes `$Ta2 = 34°C` as the high target
- Stores result in `#WCS` which is then modified by `#SHifT`

#### Outdoor Temperature Smoothing (timer=8, line 410)

```lua
#OutsideTemp = (#OutsideTemp * 59 + @Outside_Temp) / 60;
```

This creates a **rolling average** that updates every 30 seconds:
- Takes 59 parts of old value + 1 part new value
- Smooths out rapid temperature fluctuations
- Prevents frequent setpoint adjustments from sensor noise
- Time constant ≈ 30 minutes for 63% response

---

## Visual Representation

### Example Heating Curve

```
Water Temp (°C)
    │
 45 │                              ●  (Point 2: -10°C outdoor, 45°C water)
    │                            ╱
 40 │                          ╱
    │                        ╱
 35 │                      ╱
    │                    ╱
 30 │                  ╱
    │                ╱
 25 │              ●                 (Point 1: 15°C outdoor, 25°C water)
    │
 20 │
    └─────┬─────┬─────┬─────┬─────┬─────┬─────┬───── Outside Temp (°C)
        -10    -5     0     5    10    15    20

The diagonal line is the heating curve.
For any outdoor temperature, read up to the line, then left to get water temp.
```

### Practical Example

**System Configuration:**
- `Outside_High_Temp` (Tb1) = 15°C
- `Target_Low_Temp` (Ta1) = 25°C
- `Outside_Low_Temp` (Tb2) = -10°C
- `Target_High_Temp` (Ta2) = 45°C

**Calculated Setpoints:**

| Outdoor Temp | Calculation | Water Setpoint |
|--------------|-------------|----------------|
| 20°C | Above curve → | 25°C (minimum) |
| 15°C | At point 1 → | 25°C |
| 10°C | Interpolate → 25 + (5×20/25) = 29°C |
| 5°C | Interpolate → 25 + (10×20/25) = 33°C |
| 0°C | Interpolate → 25 + (15×20/25) = 37°C |
| -5°C | Interpolate → 25 + (20×20/25) = 41°C |
| -10°C | At point 2 → | 45°C |
| -15°C | Below curve → | 45°C (maximum) |

## Curve Tuning Guidelines

### Step 1: Determine Design Temperatures

**Outside Low Temp (Tb2):**
- Set to your region's design temperature (coldest expected)
- Netherlands: typically -5°C to -10°C
- Germany: typically -10°C to -15°C
- Scandinavia: -15°C to -25°C

**Outside High Temp (Tb1):**
- Temperature above which no heating is needed
- Typically 15°C to 18°C
- Depends on building insulation and internal heat gains

### Step 2: Determine Water Temperatures

**Target Low Temp (Ta1):**
- Minimum water temp that provides comfort at Tb1
- Typically 20°C to 30°C
- Lower is better for efficiency
- Depends on:
  - Radiator/underfloor sizing
  - Building heat loss
  - Desired indoor temperature

**Target High Temp (Ta2):**
- Water temp needed at design outdoor temp (Tb2)
- Typically 35°C to 50°C
- Underfloor heating: 30-40°C
- Standard radiators: 40-50°C
- Old radiators: 50-60°C

### Step 3: Fine-Tuning Process

1. **Start Conservative:**
   - Begin with manufacturer recommendations
   - Or use: Ta1 = 25°C, Ta2 = 45°C

2. **Monitor Performance:**
   - Too cold indoors at mild temps? → Increase Ta1
   - Too cold indoors at design temp? → Increase Ta2
   - Too warm indoors? → Decrease both Ta1 and Ta2
   - Indoor temp fluctuates with weather? → Adjust curve slope

3. **Optimize for Efficiency:**
   - Gradually **lower both points** while maintaining comfort
   - Each 1°C reduction in water temp ≈ 2-3% efficiency gain
   - Monitor COP (Coefficient of Performance)

4. **Seasonal Adjustments:**
   - Some systems allow parallel curve shifting
   - Move entire curve up/down by 2-3°C
   - Useful for:
     - Windy vs calm periods
     - High vs low sun angle
     - Occupancy patterns

## Curve Slope Interpretation

### Steep Curve (Large Ta2-Ta1 difference)
```
Ta1 = 25°C, Ta2 = 50°C → Slope = 25°C / 25°C outdoor range
```
- **Characteristics:**
  - Large water temp changes with weather
  - Aggressive response to outdoor conditions
- **Typical for:**
  - Poorly insulated buildings
  - Undersized radiators
  - High heat loss

### Shallow Curve (Small Ta2-Ta1 difference)
```
Ta1 = 30°C, Ta2 = 40°C → Slope = 10°C / 25°C outdoor range
```
- **Characteristics:**
  - Small water temp changes with weather
  - Gentle response to outdoor conditions
- **Typical for:**
  - Well-insulated buildings
  - Oversized radiators / underfloor heating
  - Low temperature heat distribution

## Advanced: Parallel Shift

Both implementations allow **shifting the entire curve** up or down:

```lua
-- curlymoo style:
Actual_Setpoint = #maxTa + #maxShift

-- BlB4 style:
Actual_Setpoint = #WCS + #SHifT
```

This **parallel shift** moves the entire curve without changing its slope:

```
Original Curve (shift = 0):
    Outside: 10°C → Water: 29°C

With shift = +3°C:
    Outside: 10°C → Water: 32°C

With shift = -2°C:
    Outside: 10°C → Water: 27°C
```

**Use Cases:**
- **Positive shift:** Room too cold, increase heat output
- **Negative shift:** Room too warm, reduce heat output
- **Dynamic shift:** Part of minimum frequency control strategy
- **Manual shift:** Compensate for wind, solar gains, occupancy

## Integration with Room Temperature Control

Modern implementations combine weather compensation with room feedback:

```
Final_Setpoint = Weather_Curve + Room_Compensation + Dynamic_Adjustments

Where:
  Weather_Curve      = f(outdoor_temp)         [WAR baseline]
  Room_Compensation  = PID(room_temp_error)    [Feedback control]
  Dynamic_Adjustments = Soft-start, min-freq   [Optimization]
```

This creates a **cascaded control system:**
1. **Primary:** Weather compensation (feedforward)
2. **Secondary:** Room temperature (feedback)
3. **Tertiary:** Dynamic optimization

## Comparison of Implementations

| Aspect | curlymoo | BlB4 TaSHifT |
|--------|----------|--------------|
| **Variable Name** | `#maxTa` | `#WCS` |
| **Update Frequency** | On temp change + 60s | Every 30 minutes |
| **Outdoor Temp Source** | Raw `@Outside_Temp` | Smoothed `#OutsideTemp` |
| **High Target** | From HP settings | Hardcoded `34°C` |
| **Calculation** | Identical formula | Identical formula |
| **Rounding** | `ceil()` | `ceil()` |
| **Further Processing** | `+ #maxShift` | `+ #SHifT` |

## Practical Tips

### 1. Start with Manufacturer Defaults
Most heat pumps have recommended curves for different radiator types:
- Underfloor: 15°C/25°C outdoor → 25°C/35°C water
- Low-temp radiators: 15°C/25°C outdoor → 25°C/40°C water
- Standard radiators: 15°C/25°C outdoor → 30°C/45°C water

### 2. Use the Lowest Possible Temperatures
- Each degree lower improves COP by 2-3%
- But comfort must not be compromised
- Find the minimum that maintains comfort

### 3. Monitor COP vs Outdoor Temperature
```
COP = Heat_Output_kW / Electrical_Input_kW

Typical values:
  Water 35°C, Outdoor 7°C  → COP ≈ 4.5
  Water 45°C, Outdoor 7°C  → COP ≈ 3.5
  Water 35°C, Outdoor -5°C → COP ≈ 2.5
```

### 4. Account for Thermal Mass
- Buildings with high thermal mass (concrete) respond slowly
- May need **steeper curve** to pre-heat before cold periods
- Or use weather forecast to anticipate changes

### 5. Sun and Wind Corrections
Some advanced systems adjust for:
- **Solar radiation:** Lower setpoint on sunny days
- **Wind speed:** Higher setpoint on windy days
- Can be implemented as additional shift terms

## Formula Derivation

For those interested in the mathematics:

**Linear equation between two points:**
```
y = y1 + (x1 - x) × (y2 - y1) / (x1 - x2)

Where:
  x = outdoor_temp
  y = water_temp
  (x1, y1) = (Tb1, Ta1) = Point 1
  (x2, y2) = (Tb2, Ta2) = Point 2

Substituting:
water_temp = Ta1 + (Tb1 - outdoor_temp) × (Ta2 - Ta1) / (Tb1 - Tb2)
```

**Slope of the curve:**
```
slope = (Ta2 - Ta1) / (Tb1 - Tb2)

Example:
  Ta1 = 25°C, Ta2 = 45°C
  Tb1 = 15°C, Tb2 = -10°C

  slope = (45 - 25) / (15 - (-10)) = 20 / 25 = 0.8°C water per °C outdoor

Interpretation: For every 1°C drop in outdoor temp, water temp increases by 0.8°C
```

## Common Mistakes to Avoid

1. **Curve Too Steep:**
   - Symptoms: Water temp changes dramatically with small weather changes
   - Fix: Reduce Ta2 or increase Ta1

2. **Curve Too Shallow:**
   - Symptoms: Insufficient heat in cold weather, excessive in mild weather
   - Fix: Increase Ta2 or decrease Ta1

3. **Too Frequent Updates:**
   - Causes system instability and hunting
   - Solution: Update every 15-30 minutes, use smoothed outdoor temp

4. **Ignoring Building Dynamics:**
   - Weather compensation is feedforward (no room feedback)
   - Must combine with room temperature control for best results

5. **One-Size-Fits-All:**
   - Optimal curve varies by building, location, and heating system
   - Always tune to your specific situation

## Conclusion

Weather compensation is the **foundation** of efficient heat pump control:

✓ **Provides baseline setpoint** based on outdoor conditions
✓ **Improves efficiency** by using lowest necessary water temperature
✓ **Reduces cycling** by anticipating heat demand
✓ **Enables advanced control** when combined with room feedback and dynamic adjustments

The simple linear curve calculation shown in both implementations is robust, well-proven, and forms the basis for more sophisticated heating strategies like minimum frequency operation and room-compensated control.
