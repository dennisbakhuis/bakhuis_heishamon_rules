# Minimum Frequency Operation Strategy

## Overview

This document explains how HeishaMon rules can be designed to keep a heat pump operating at minimum frequency (duty) instead of cycling on and off. This approach is beneficial for:

* **Improved efficiency**: Heat pumps are most efficient when running continuously at low output
* **Reduced wear**: Fewer start/stop cycles extend compressor life
* **Better comfort**: More stable temperature control
* **Noise reduction**: Minimum frequency operation is quieter than frequent cycling

## The Core Principle

The fundamental strategy involves maintaining a **dynamic setpoint** that stays just above the actual inlet temperature. This creates a "moving target" that prevents the heat pump from reaching its setpoint and shutting off.

### How It Works

1. **Target Tracking**: Set the heat pump's target temperature to be 3-4°C above the current inlet flow temperature
2. **Automatic Minimum Duty**: The heat pump automatically reduces to minimum frequency when the outlet temperature approaches the setpoint
3. **Prevents Shutdown**: By keeping the setpoint slightly above the inlet, the HP never fully satisfies the target and continues running
4. **Safety Margin**: If the outlet gets too close to the setpoint (< 1-2°C), the HP may turn itself off

## Implementation Examples

### Example 1: curlymoo_rules.txt

This implementation uses a simpler approach with `#maxShift` to dynamically adjust the setpoint.

#### Key Variables

```lua
#maxTa         -- Weather-compensated target temperature (base setpoint)
#maxShift      -- Dynamic adjustment applied to setpoint (-5 to +1°C)
#outletOnTemp  -- Flag: 1 when outlet temp >= target
```

#### Core Logic (from lines 130-149)

```lua
on setNewTemp then
    if isset(@Main_Outlet_Temp) && isset(@Main_Inlet_Temp) &&
       isset(@Main_Target_Temp) && isset(?setpoint) && isset(@High_Pressure) then

        -- Calculate delta between outlet and inlet
        #dT = @Main_Outlet_Temp - @Main_Inlet_Temp;

        -- Safety check: Don't lower setpoint if dT is small or pressure is low
        if #maxShift < 0 && ((#dT < 3 && #outletOnTemp == 0) || @High_Pressure < 15) then
            #maxShift = 0;
        end

        -- Calculate how far outlet is from target
        #dTOutlet = @Main_Outlet_Temp - (#maxTa + #maxShift);

        -- If outlet is more than 1°C above target, schedule a shift reduction
        if #dTOutlet > 1 && @Defrosting_State == 0 && #allowShift == 1 then
            setTimer(5, 90);  -- Reduce shift in 90 seconds
            #allowShift = 0;
        end

        -- Apply the shift to the setpoint
        @SetZ1HeatRequestTemperature = #maxShift;
    end
end
```

#### Automatic Shift Reduction (timer=5, line 124)

```lua
on timer=5 then
    -- Gradually reduce shift, keeping it between -1 and 0 when outlet > target
    #maxShift = max(min((#maxTa - @Main_Outlet_Temp), 0), -1);
    setTimer(6, 900);  -- Allow new shift in 15 minutes
    setNewTemp();
end
```

**How this maintains minimum frequency:**

* When outlet temp approaches or exceeds the weather-compensated target (`#maxTa`), `#maxShift` becomes negative
* This effectively lowers the setpoint slightly (by -1 to -3°C), keeping it just above inlet temp
* The HP continues running at minimum frequency to maintain this small temperature difference
* The shift is automatically adjusted based on the outlet-to-target difference

---

### Example 2: HeishaMon_Rules_BlB4_commented.txt (TaSHifT Function)

This more sophisticated implementation uses the "TaSHifT" (Target Shift) function with separate controls for soft-start and room temperature compensation.

#### Key Variables

```lua
#WCS              -- Weather Compensation Setpoint (base from curve)
#SHifT            -- Total shift applied (-5 to +5°C)
#SoftStartControl -- Soft-start component of shift
#RoomTempControl  -- Room temperature compensation component
#CompRunSec       -- Compressor runtime in seconds (during first 18 min)
```

#### Core Logic (timer=3, lines 171-212)

```lua
on timer=3 then
    setTimer(3,30);  -- Run every 30 seconds

    -- Only active during heating mode, not DHW, not defrosting
    $NoDefrost = @Defrosting_State == 0 || (@Pump_Flow > 5 && @Pump_Flow < 30);
    if #Heat && @ThreeWay_Valve_State == 0 && $NoDefrost && #DHWRun < 1 then

        -- Calculate current shift
        #SHifT = @Z1_Heat_Request_Temp - #WCS;

        if #CompState > 0 then  -- Compressor is running

            if #OutsideTemp < 8 then  -- Cold weather: soft-start control

                if #RoomTempDelta > 1 || %hour < 3 then
                    -- Room too warm or night: maximum negative shift
                    #SHifT = -3;

                elseif #CompRunSec < 1080 then  -- First 18 minutes: soft-start
                    -- Gradually increase from -5 to 0 over ~13 minutes
                    #SoftStartControl = floor((#CompRunSec^0.5 - 28)/5.16);
                    #SHifT = #SoftStartControl;

                    -- Add room temp control if negative (Ta too high)
                    if #RoomTempControl < 0 then
                        #SHifT = #SoftStartControl + #RoomTempControl;
                    end

                elseif #RoomTempControl > #SHifT || @Compressor_Freq > 21 then
                    -- After soft-start: use room temp control
                    #SHifT = #RoomTempControl;
                else
                    -- Keep current shift to avoid shutdown
                    #SHifT = #SHifT;
                end

            else  -- Mild weather (>8°C): simpler control
                if (@Main_Outlet_Temp - 1.8) > (#RoomTempControl + #WCS) &&
                   #CompRunTime < 30 then
                    -- Keep setpoint just above outlet temp
                    #SHifT = ceil(@Main_Outlet_Temp - 1.8 - #WCS);
                else
                    #SHifT = #RoomTempControl;
                end
            end

        else  -- Compressor is not running
            $StopConditions = #CompRunTime > (- 2 * #OutsideTemp - 30) ||
                             %hour < 7 || %hour > 22 || #RoomTempDelta < 0.2;

            if #CompState == 0 && $StopConditions && #CompRunTime < 2 then
                -- Just stopped: prevent short cycling
                #SHifT = -5;
            else
                -- Normal: reset shift to 0
                #SHifT = 0;
            end
        end

        -- Limit shift range
        #SHifT = min(max(#SHifT, -5), 5);

        -- Apply shift to setpoint
        if #ExternalOverRide == -2 then
            $Z1HRT = #WCS;  -- Override: weather curve only
        else
            $Z1HRT = #SHifT + #WCS;  -- Normal: weather curve + shift
        end

        if $Z1HRT != @Z1_Heat_Request_Temp && #ExternalOverRide < 1 then
            @SetZ1HeatRequestTemperature = $Z1HRT;
        end
    end
end
```

#### Soft-Start Formula (line 181)

```lua
#SoftStartControl = floor((#CompRunSec^0.5 - 28)/5.16);
```

This mathematical formula creates a **non-linear ramp**:
* Starts at approximately -5°C when compressor starts
* Increases rapidly at first, then more slowly
* Reaches 0°C after about 1080 seconds (18 minutes)
* The square root function creates the accelerating curve

**How this maintains minimum frequency:**

* **Soft-start phase** (0-18 min): Setpoint gradually rises from (WCS - 5°C) to WCS
  * This keeps the setpoint well above inlet during startup
  * HP runs at minimum frequency trying to reach the moving target
  * Prevents overshooting and short-cycling

* **Steady-state phase** (>18 min): Shift is based on room temperature feedback
  * If room is too cold: positive shift (increase setpoint, more heat)
  * If room is too warm: negative shift (decrease setpoint, less heat)

* **Mild weather** (>8°C): Shift keeps setpoint just 1.8°C above outlet temperature
  * This is the "minimum frequency zone"
  * HP runs continuously at lowest duty to maintain this small gap

## Comparison of Approaches

| Aspect | curlymoo (Simple) | BlB4 TaSHifT (Advanced) |
|--------|-------------------|-------------------------|
| **Complexity** | Low - basic inlet tracking | High - multi-phase control |
| **Shift Range** | -5 to +1°C | -5 to +5°C |
| **Primary Input** | Outlet vs Target temp | Room temp + Compressor state |
| **Soft-Start** | Implicit via shift logic | Explicit 18-min ramp |
| **Update Frequency** | On temp changes + timer | Every 30 seconds |
| **Room Control** | Via thermostat only | Integrated PID control |
| **Weather Zones** | Single approach | Different logic <8°C vs >8°C |

## Key Takeaways

### For Simple Implementation (curlymoo style):
```
IF outlet_temp > target THEN
    Lower setpoint by 1-3°C
    (Makes HP reduce to minimum frequency)
END IF
```

### For Advanced Implementation (TaSHifT style):
```
AT STARTUP:
    Start with setpoint = weather_curve - 5°C
    Gradually increase over 18 minutes
    (Keeps HP at minimum frequency during warm-up)

DURING OPERATION:
    IF outlet approaching setpoint THEN
        Keep setpoint 2-4°C above inlet
        (Maintains minimum frequency)
    END IF

    Adjust based on room temperature feedback
END
```

## Benefits vs Traditional On/Off Control

### Traditional Thermostat Control:
* HP runs at full power until setpoint reached
* Shuts off when target reached
* Frequent cycling: ON (5-10 min) → OFF (20-30 min) → ON...
* Lower average efficiency, more wear

### Minimum Frequency Control:
* HP starts at minimum frequency
* Runs continuously at low output
* Adapts output to actual heat loss
* Higher efficiency, longer compressor life

## Implementation Considerations

1. **Inlet-Outlet Delta**: Monitor `dT = Outlet - Inlet`
   * Typical: 3-7°C at minimum frequency
   * Too low (<2°C): Risk of HP shutdown
   * Too high (>10°C): HP may be working too hard

2. **High Pressure Check**: Some implementations check pressure to avoid lowering setpoint when system pressure is already low

3. **Defrost Protection**: Disable minimum frequency logic during defrost cycles

4. **Time-of-Day**: Some rules reduce shift at night or early morning to allow heat buildup before occupants wake

5. **Weather Dependency**: Different strategies for mild vs cold weather
   * Cold (<5°C): Allow higher frequencies, focus on preventing shutdown
   * Mild (>10°C): Aggressive minimum frequency control works well

## Mathematical Model

The relationship between setpoint adjustment and frequency:

```
Setpoint = Weather_Curve_Base + Dynamic_Shift

Where:
  Dynamic_Shift = f(Outlet_Temp, Inlet_Temp, Room_Temp, Runtime)

Goal:
  Outlet_Temp ≈ Setpoint - 2°C  (minimum frequency zone)

When:
  Outlet_Temp > (Setpoint - 2°C) → Reduce shift (lower setpoint)
  Outlet_Temp < (Setpoint - 4°C) → Increase shift (raise setpoint)
```

This creates a **control band** where the HP operates at minimum frequency, continuously trying to close a small temperature gap that is deliberately maintained by the dynamic setpoint adjustment.
