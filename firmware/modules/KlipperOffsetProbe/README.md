# KlipperOffsetProbe
A Klippy plugin which solves the problem (when paired with a removable hardware probe) of finding the Z-offset between multiple tools.

If you have a toolchanger or IDEX printer you probably find yourself having to manually set Z offsets from time to time, either when changing tools or changing nozzles.

This script will cycle through each tool and probe the nozzle on a hardware probe somewhere on the printer and report the difference between the nozzle and the standard Z limit switch for each tool.

## How's it work?
When `offset_probe` is called on the printer the script will:
- Home the Z limit switch on top of the probe to get a Z0 location
- Check the config for a toolchange command named `toolchange_gcode_<tool number>` where tool number is between 0 and 99
- Executes the specified ttolchange Gcode, then moves to (`probe_x`, `probe_y`) and performs a probe using the custom probe specified by `pin` config
- Calculates the difference between the trigger of the Z probe and the custom probe to determine offset

After probing each tool the final results will be logged in the console to be saved by you.
Since toolchanging has no standardised approach in the Klipper world this is an easier approach than making assumptions about any specific implementation.

## Config example

```yaml
[offset_probe]
# Define the pin that the extra probe is connected to
pin: ^PC16
# X,Y coordinates to probe - these should be the native coordinates before any offsets are applied
probe_x: 150
probe_y: 150
# Z offset of the Z limit switch, which will be added to the calculated offset
z_offset: 0
# Additional offset added to each determined tool offset to account for micro switch pre-travel
# e.g. when using a removable hardware probe that utilises a micro switch to trigger
switch_offset: 0
# The speed (in mm/sec) to move tools down onto the probe
speed: 5
# The speed (in mm/sec) to retract between probes
lift_speed: 5
# Distance to retract between probes - default of 0.5
lift_distance: 10
# The speed (in mm/sec) of X/Y moves - default of 100
move_speed: 100
# Gcode macro to be run before anything else happens. A good use might be to ensure no tools are attached
start_gcode:
    TOOL_DROPOFF
# Gcode macro to run after all tools are probed, for example to ensure all tools were parked
end_gcode:
    TOOL_DROPOFF
# Defines 3 tools to be probed. Note that they do not have to be sequential, you may skip tools if that's desirable
toolchange_gcode_0:
    T0
toolchange_gcode_1:
    T1
toolchange_gcode_2:
    T2
```

## Installation
The simplest maintainable approach is to clone this repo to your host and then link the script to the klippy folder:
```bash
git clone https://github.com/Xonman/KlipperOffsetProbe ~/KlipperOffsetProbe
ln -s ~/KlipperOffsetProbe/offset_probe.py ~/klipper/klippy/extras/offset_probe.py
```
This should allow you to pull updates to the script without having to copy/paste it into the klippy folder each time.
