# Tools for klipper

This are python extras, macros and example config for the
[Klipper 3D printer firmware](https://github.com/Klipper3d/klipper). I
originally created this as macros when converting my Jubilee based
toolchanger from RRF and Duet3 to Klipper.

I welcome all contribution!

This is working great but treat it as a Beta version in development.

## Features

* **Each Tool is treated as an object and has it's own configuration** -
having configurable coordinates for parking, zoning, tool offset, 
meltzonelength, extruder, fan, etc.
*  **Multiple tools can be grouped in ToolGroup.** -Most configuration can
be inherited from the group if not specified in the tool config section.
*  **Virtual tools** - A tool can be virtual andhave a physical parent,
inheriting all nonspecified configuration from parent, parent group and
then toolgroup. Use case example of an ERCF on a PLA tool,a ERCF on a 
PETG tool, one tool without virtual tools for abrasive and yet another
tool with 3 markers that can switch between 3 markers by rotation.
* **Tools don't need to be extruders/hotends**, can be anything.
* **User defineable macro to Lock / Unlock** - Uses custom gcodes in config 
like the gcode_button. This can call a macro or multiple lines. 
* **User defineable macro to Pickup / Dropoff tools** - Can be inherited.
In the macro, `myself` refers to the calling toolobject so you can get 
myself.id for tool number or myself.offset[0] for X offset in the macro.
Ex. having same pickup gcode macro inherited for all tools from a group 
except for one that uses another type of toolwipe and has it's own pickup_gcode.
* **Global ToolLock parameters** - example purge_on_toolchange can be set 
to false when aligning tools with TAMV/ZTATP.
* **Fan speed** is carried over on toolchange if the tool has a fan. Also
`M106`/`M107` defaults to current_tool to set fan speed but can also use a Pnnn 
parameter to specify another tool.
* **Extruder temperature control** - 
  - Definable for any tool with a Pnnn parameter or defaults to current_tool
  - Has diffrent Active and Standby temperatures.
  - Can be set in Active, Standby or Off mode.
  - Can have delayed Standby and Off. Configured and/or customized with N and O parameters at runtime.
    - Example. Set Standby temperature 30 sec after putting the tool in standby and in Off after 30 minutes of not being activated.
    - Or set Time to standby to 0.1 for instant standby and Time to Powerdown to 604800 for a having it powered for a week.
    - Usefull when having sporadic toolchanges in a large print or many toolchanges in a small print.
  - Wait to reach temperature with tolerance. Set temperature +/- configurable tolerance.
* Current Tool is saved and restored at powerdown. Default but optional.
* Input shaper parameters for each tool.
* Position prior to toolchange can optionaly be saved and restored.

## Installation Instructions
### Install with Moonraker Autoupdate Support
This plugin assumes that you installed Klipper into your home directory (usually `/home/pi`). 

1) Clone this repo into your home directory where Klipper is installed:
```
cd ~
git clone https://github.com/TypQxQ/Klipper_ToolChanger.git
```

2) Edit `moonraker.conf` by adding the following entry:
```
[update_manager client klipper_toolchanger]
type: git_repo
path: ~/Klipper_ToolChanger
origin: https://github.com/TypQxQ/Klipper_ToolChanger.git
install_script: install.sh
is_system_service: False
```

3) Run the `install.sh` script
```
~/Klipper_ToolChanger/install.sh
```

Klipper_ToolChanger will show up in the update the next time you restart moonraker, or you can restart mooraker right away with: `sudo systemctl restart moonraker`.
If you encouter errors after an automatic Klipper update you can safetly run the `install.sh` scipt again to repair the links to the extension.

### Manual Install
Copy the python (`*.py`) files into the `\klipper\klipper\extras` directory. Assuming Klipper is installed in your home directory:
```
cp ./*.py ~/klipper/klippy/extras/
```
Then restart Klipper to pick up the extensions.

## To do:
* Add virtual tools select code.
* Add selectable automatic calculation of active times based on previous times. Ex:
  * Mean Layer time Standby mode. - Save time at every layerchange and at toolchange set to mean time of last 3 layers *2 or at last layer *1.5 with a Maximum and a minimum time. Needs to be analyzed further.
  * Save the time it was in Standby last time and apply a fuzzfactor. Put tool in standby and heatup with presumption that next time will be aproximatley after the same time as last. +/- Fuzzfactor.
* Save pressure avance per tool to be restored on toolchange. Also between virtual tools. Check Slicer output first if this is needed or can be put in Filament custom gcode.

## Configuration requirements
* `[input_shaper]` needs to be used for input shaper to wordk.

## G-Code commands:
* `TOOL_LOCK` - Lock command
* `TOOL_UNLOCK` - Unlock command
* `Tn` - T0, T1, T2, etc... A select command is created for each tool. 
  * `R` - Calls SAVE_CURRENT_POSITION with the variable as a RESTORE_POSITION_TYPE. For example "T0 R1" will call "SAVE_CURRENT_POSITION RESTORE_POSITION_TYPE=1" before moving. Positioned is restored with "RESTORE_POSITION" from below.
* `T_1` - Dropoff the current tool without picking up another tool
* `SET_AND_SAVE_FAN_SPEED` - Set the fan speed of specified tool or current tool if no `P` is supplied. Then save to be recovered at ToolChange.
  * `S` - Fan speed 0-255 or 0-1, default is 1, full speed.
  * `P` - Fan of this tool. Default current tool.
* `TEMPERATURE_WAIT_WITH_TOLERANCE` - Waits for all temperatures, or a specified tool or heater's temperature.
This command can be used without any additional parameters. Without parameters it waits for bed and current extruder. Only one of either TOOL or HEATER may be used.
  - `TOOL` - Tool number.
  - `HEATER` - Heater number. 0="heater_bed", 1="extruder", 2="extruder1", 3="extruder2", etc. Only works if named as default, this way.
  - `TOLERANCE` - Tolerance in degC. Defaults to 1*C. Wait will wait until heater is between set temperature +/- tolerance.
* `SET_TOOL_TEMPERATURE` - Set tool temperature.
  * `TOOL` - Tool number, optional. If this parameter is not provided, the current tool is used.
  * `STDB_TMP` - Standby temperature(s), optional
  * `ACTV_TMP` - Active temperature(s), optional
  * `CHNG_STATE` - Change Heater State, optional: 0 = off, 1 = standby temperature(s), 2 = active temperature(s).
  * `STDB_TIMEOUT` - Time in seconds to wait between changing heater state to standby and setting heater target temperature to standby temperature when standby temperature is lower than tool temperature.
    * Use for example 0.1 to change immediately to standby temperature.
  * `SHTDWN_TIMEOUT` - Time in seconds to wait from docking tool to shutting off the heater, optional.
    * Use for example 86400 to wait 24h if you want to disable shutdown timer.
* `SET_GLOBAL_OFFSET` - Set a global offset that can be applied to all tools
  * `X` / `Y` / `Z` - Set the X/Y/Z offset position
  * `X_ADJUST` / `Y_ADJUST` / `Z_ADJUST` - Adjust the X/Y/Z offset position incramentally
* `SET_TOOL_OFFSET` - Set the offset of an individual tool
  * `TOOL` - Tool number, optional. If this parameter is not provided, the current tool is used.
  * `X` / `Y` / `Z` - Set the X/Y/Z offset position
  * `X_ADJUST` /`Y_ADJUST` / `Z_ADJUST` - Adjust the X/Y/Z offset position incramentally  
* `SET_PURGE_ON_TOOLCHANGE` - Sets a global variable that can disable all purging (can be used in macros) when loading/unloading. For example when doing a TAMV/ZTATP tool alignement.
* `SAVE_POSITION` - Sets the Restore type and saves specified position for the toolhead. This command is usually used inside the custom g-code of the slicer software. The restore_position_on_toolchange_type will be changed to reflect the passed parameters.
  * X= X position to save, optional but Y must be specifie or this will be ignored.
  * Y= Y position to save, optional but X must be specifie or this will be ignored.
  * Z= Z position to save, optional but X and Y must be specifie or this will be ignored.
    * With no parameters it will set Restore type to 0, no restore.
    * With X and Y parameters it will save the specified X and Y. Sets restore type to 1, restore XY.
    * With X, Y and Z parameters it will save the specified X, Y and Z. Sets restore type to 2, restore XYZ.
* `SAVE_CURRENT_POSITION` - Save the current G-Code position of the toolhead. This command is usually used inside the pickup_gcode script or the custom g-code of the slicer software.
  * RESTORE_POSITION_TYPE= Type of restore, optional. If not specified, restore_position_on_toolchange_type will not be changed.
    * 0: No restore
    * 1: Restore XY
    * 2: Restore XYZ
* `RESTORE_POSITION` - Restore position to the latest saved position. This command is usually used inside the pickup_gcode script.
  * RESTORE_POSITION_TYPE= Type of restore, optional. If not specified, restore_position_on_toolchange_type will be used.
    * 0: No restore
    * 1: Restore XY
    * 2: Restore XYZ
## Values accesible from Macro for each object
- **Toollock**
  - `global_offset` - Global offset.
  - `tool_current` - -2: Unknown tool locked, -1: No tool locked, 0: and up are toolnames.
  - `saved_fan_speed` - Speed saved at each fanspeedchange to be recovered at Toolchange.
  - `purge_on_toolchange` - For use in macros to enable/disable purge/wipe code globaly.
  - `restore_position_on_toolchange_type` - The type of restore position:
    - 0: No restore
    - 1: Restore XY
    - 2: Restore XYZ
  - `saved_position` - The position saved when the latest T# command had a RESTORE_POSITION parameter to other than 0
- **Tool** - The tool calling this macro is referenced as `myself` in macros. When running for example `T3` to pickup the physical tool, in `pickup_gcode:` of one can write `{myself.name}` which would return `3`.
  - `name` - id. 0, 1, 2, etc.
  - `is_virtual` - If this tool has another layer of toolchange possible.
  - `physical_parent_id` - Parent physical tool that holds tool coordinates. Can be same as this.
  - `extruder` - extruder name as configured.
  - `fan` - fan name.
  - `lazy_home_when_parking` - When set to 1, will home unhomed XY axes if needed and will not move any axis if already homed and parked. 2 Will also home Z if not homed.
  - `meltzonelength` - Meltzonelength to unload/load filament at toolpak. See e3d documentation.
  - `zone` - Fast aproach coordinates when parking
  - `park` - Parking spot, slow aproach.
  - `offset` - Tool offset.
  - `heater_state` - 0 = off, 1 = standby temperature, 2 = active temperature. Placeholder.
  - `heater_active_temp` - Temperature to set when in active mode.
  - `heater_standby_temp` - Temperature to set when in standby mode.
  - `idle_to_standby_time` - Time in seconds from being parked to setting temperature to standby the temperature above. Use 0.1 to change imediatley to standby temperature.
  - `idle_to_powerdown_time` - Time in seconds from being parked to setting temperature to 0. Use something like 86400 to wait 24h if you want to disable. Requred on Physical tool.
- **ToolGroup**
  - `is_virtual` - As above
  - `physical_parent_id` - As above
  - `lazy_home_when_parking` - As above
