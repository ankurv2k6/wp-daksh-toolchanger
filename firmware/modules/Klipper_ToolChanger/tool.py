# Tool support
#
# Copyright (C) 2022  Andrei Ignat <andrei@ignat.se>
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging
import time

class Tool:
    def __init__(self, config = None):
        self.name = None
        self.toolgroup = None               # defaults to 0. Check if tooltype is defined.
        self.is_virtual = None
        self.physical_parent_id = None      # Parent tool is used as a Physical parent for all tools of this group. Only used if the tool i virtual. None gets remaped to -1.
        self.extruder = None                # Name of extruder connected to this tool. Defaults to None.
        self.fan = None                     # Name of general fan configuration connected to this tool as a part fan. Defaults to "none".
        self.meltzonelength = None          # Length of the meltzone for retracting and inserting filament on toolchange. 18mm for e3d Revo
        self.lazy_home_when_parking = None  # (default: 0 - disabled) - When set to 1, will home unhomed XY axes if needed and will not move any axis if already homed and parked. 2 Will also home Z if not homed.
                                            # Wipe. -1 = none, 1= Only load filament, 2= Wipe in front of carriage, 3= Pebble wiper, 4= First Silicone, then pebble. Defaults to None.
        self.zone = None                    # Position of the parking zone in the format X, Y  
        self.park = None                    # Position to move to when fully parking the tool in the dock in the format X, Y
        self.offset = None                  # Offset of the nozzle in the format X, Y, Z

        self.pickup_gcode = None            # The plain gcode string is to load for virtual tool having this tool as parent.
        self.dropoff_gcode = None           # The plain gcode string is to load for virtual tool having this tool as parent.

        self.heater_state = 0               # 0 = off, 1 = standby temperature, 2 = active temperature. Placeholder. Requred on Physical tool.
        self.heater_active_temp = 0         # Temperature to set when in active mode. Placeholder. Requred on Physical and virtual tool if any has extruder.
        self.heater_standby_temp = 0        # Temperature to set when in standby mode.  Placeholder. Requred on Physical and virtual tool if any has extruder.
        self.idle_to_standby_time = 0.1     # Time in seconds from being parked to setting temperature to standby the temperature above. Use 0.1 to change imediatley to standby temperature. Requred on Physical tool
        self.idle_to_powerdown_time = 600   # Time in seconds from being parked to setting temperature to 0. Use something like 86400 to wait 24h if you want to disable. Requred on Physical tool.

        # Tool specific input shaper parameters. Initiated as Klipper standard.
        self.shaper_freq_x = 0
        self.shaper_freq_y = 0
        self.shaper_type_x = "mzv"
        self.shaper_type_y = "mzv"
        self.shaper_damping_ratio_x = 0.1
        self.shaper_damping_ratio_y = 0.1
        self.extra_extrude_mm = 0
        self.hotend_type = "V6"
        self.cooling_tube_retraction = 35
		
        # Under Development:
        HeatMultiplyerAtFullFanSpeed = 1    # Multiplier to be aplied to hotend temperature when fan is at maximum. Will be multiplied with fan speed. Ex. 1.1 at 205*C and fan speed of 40% will set temperature to 213*C

        # If called without config then just return a dummy object.
        if config is None:
            return None

        # Load used objects.
        self.printer = config.get_printer()
        self.gcode = config.get_printer().lookup_object('gcode')
        gcode_macro = self.printer.load_object(config, 'gcode_macro')
        self.toollock = self.printer.lookup_object('toollock')

        ##### Name #####
        try:
            _, name = config.get_name().split(" ", 1)
            self.name = int(name)
        except ValueError:
            raise config.error(
                    "Name of section '%s' contains illegal characters. Use only integer tool number."
                    % (config.get_name()))

        ##### ToolGroup #####
        self.toolgroup = 'toolgroup ' + str(config.getint('tool_group'))
        if config.has_section(self.toolgroup):
            self.toolgroup = self.printer.lookup_object(self.toolgroup)
        else:
            raise config.error(
                    "ToolGroup of T'%s' is not defined. It must be configured before the tool."
                    % (config.get_name()))
        tg_status = self.toolgroup.get_status()

        ##### Is Virtual #####
        self.is_virtual = config.getboolean('is_virtual', 
                                            tg_status["is_virtual"])

        ##### Physical Parent #####
        self.physical_parent_id = config.getint('physical_parent', 
                                                tg_status["physical_parent_id"])
        if self.physical_parent_id is None:
            self.physical_parent_id = -1

        # Used as sanity check for tools that are virtual with same physical as themselves.
        if self.is_virtual and self.physical_parent_id == -1:
            raise config.error(
                    "Section Tool '%s' cannot be virtual without a valid physical_parent. If Virtual and Physical then use itself as parent."
                    % (config.get_name()))
        
        if self.physical_parent_id >= 0 and not self.physical_parent_id == self.name:
            pp = self.printer.lookup_object("tool " + str(self.physical_parent_id))
        else:
            pp = Tool()     # Initialize physical parent as a dummy object.

        pp_status = pp.get_status()


        ##### Extruder #####
        self.extruder = config.get('extruder', pp_status['extruder'])      

        ##### Fan #####
        self.fan = config.get('fan', pp_status['fan'])                     

        ##### Meltzone Length #####
        self.meltzonelength = config.get('meltzonelength', pp_status['meltzonelength'])      
        if self.meltzonelength is None:
            self.meltzonelength = tg_status["meltzonelength"]

        ##### Lazy Home when parking #####
        self.lazy_home_when_parking = config.get('lazy_home_when_parking', pp_status['lazy_home_when_parking'])   
        if self.lazy_home_when_parking is None:
            self.lazy_home_when_parking = tg_status["lazy_home_when_parking"]

        ##### Coordinates #####
        self.zone = config.get('zone', pp_status['zone'])
        if not isinstance(self.zone, list):
            self.zone = str(self.zone).split(',')
        self.park = config.get('park', pp_status['park'])                  
        if not isinstance(self.park, list):
            self.park = str(self.park).split(',')
        self.offset = config.get('offset', pp_status['offset'])
        if not isinstance(self.offset, list):
            self.offset = str(self.offset).split(',')
		
        # Tool specific input shaper parameters. Initiated with Klipper standard values where not specified.
        self.shaper_freq_x = config.get('shaper_freq_x', pp_status['shaper_freq_x'])                     
        self.shaper_freq_y = config.get('shaper_freq_y', pp_status['shaper_freq_y'])                     
        self.shaper_type_x = config.get('shaper_type_x', pp_status['shaper_type_x'])                     
        self.shaper_type_y = config.get('shaper_type_y', pp_status['shaper_type_y'])                     
        self.shaper_damping_ratio_x = config.get('shaper_damping_ratio_x', pp_status['shaper_damping_ratio_x'])                     
        self.shaper_damping_ratio_y = config.get('shaper_damping_ratio_y', pp_status['shaper_damping_ratio_y'])  
                           
        self.extra_extrude_mm = config.get('extra_extrude_mm', pp_status['extra_extrude_mm'])
        self.hotend_type = config.get('hotend_type', pp_status['hotend_type'])
        self.cooling_tube_retraction = config.get('cooling_tube_retraction', pp_status['cooling_tube_retraction'])
        
        
        ##### Standby settings #####
        if self.extruder is not None:
            if self.physical_parent_id < 0 or self.physical_parent_id == self.name:
                self.idle_to_standby_time = config.getfloat(
                    'idle_to_standby_time', tg_status['idle_to_standby_time'], minval = 0.1)
                self.timer_idle_to_standby = ToolStandbyTempTimer(self.printer, self.name, 1)

                self.idle_to_powerdown_time = config.getfloat(
                    'idle_to_powerdown_time', tg_status['idle_to_powerdown_time'], minval = 0.1)
                self.timer_idle_to_powerdown = ToolStandbyTempTimer(self.printer, self.name, 0)
            else:
                self.idle_to_standby_time = pp.idle_to_standby_time
                self.idle_to_powerdown_time = pp.idle_to_powerdown_time
                self.timer_idle_to_standby = pp.get_timer_to_standby()
                self.timer_idle_to_powerdown = pp.get_timer_to_powerdown()

        ##### G-Code ToolChange #####
        self.pickup_gcode = config.get('pickup_gcode', None)
        self.dropoff_gcode = config.get('dropoff_gcode', None)

        temp_pickup_gcode = pp.get_pickup_gcode()
        if temp_pickup_gcode is None:
            temp_pickup_gcode =  self.toolgroup.get_pickup_gcode()
        self.pickup_gcode_template = gcode_macro.load_template(config, 'pickup_gcode', temp_pickup_gcode)

        temp_dropoff_gcode = pp.get_dropoff_gcode()
        if temp_dropoff_gcode is None:
            temp_dropoff_gcode = self.toolgroup.get_dropoff_gcode()
        self.dropoff_gcode_template = gcode_macro.load_template(config, 'dropoff_gcode', temp_dropoff_gcode)


        ##### Register Tool select command #####
        self.gcode.register_command("T" + str(self.name), self.cmd_SelectTool, desc=self.cmd_SelectTool_help)


    cmd_SelectTool_help = "Select Tool"
    def cmd_SelectTool(self, gcmd):

        current_tool_id = int(self.toollock.get_status()['tool_current']) # int(self.toollock.get_tool_current())

        self.toollock.LogThis("T" + str(self.name) + " Selected.", 1)
        self.toollock.LogThis("Current Tool is T" + str(current_tool_id) + ".")
        self.toollock.LogThis("This tool is_virtual is " + str(self.is_virtual) + ".")

        if current_tool_id == self.name:              # If trying to select the already selected tool:
            return None                                   # Exit

        if current_tool_id < -1:
            raise self.printer.command_error("TOOL_PICKUP: Unknown tool already mounted Can't park it before selecting new tool.")

        if self.extruder is not None:               # If the new tool to be selected has an extruder prepare warmup before actual tool change so all unload commands will be done while heating up.
            self.gcode.run_script_from_command("M568 P%d A2" % (int(self.name)))
            #pass

        # If optional RESTORE_POSITION_TYPE parameter is passed as 1 or 2 then save current position and restore_position_on_toolchange_type as passed. Otherwise do not change either the restore_position_on_toolchange_type or saved_position. This makes it possible to call SAVE_POSITION or SAVE_CURRENT_POSITION before the actual T command.
        param = gcmd.get_int('R', None, minval=0, maxval=2)
        if param is not None:
            if param in [ 1, 2 ]:
                self.toollock.SaveCurrentPosition(param) # Sets restore_position_on_toolchange_type to 1 or 2 and saves current position
            else:
                self.toollock.SavePosition()  # Sets restore_position_on_toolchange_type to 0

        # Drop any tools already mounted.
        if current_tool_id >= 0:                    # If there is a current tool already selected and it's a dropable.
            current_tool = self.printer.lookup_object('tool ' + str(current_tool_id))
                                                        # If the next tool is not another virtual tool on the same physical tool.
            
            self.toollock.LogThis("self.physical_parent_id:" + str(self.physical_parent_id) + ".")
            self.toollock.LogThis("current_tool.get_status()['physical_parent_id']:" + str(current_tool.get_status()["physical_parent_id"]) + ".")

            if int(self.physical_parent_id ==  -1 or
                        self.physical_parent_id) !=  int( 
                        current_tool.get_status()["physical_parent_id"]
                        ):
                self.toollock.LogThis("Will Dropoff():")
                current_tool.Dropoff()
                current_tool_id = -1

        # Now we asume tool has been dropped if needed be.

        if not self.is_virtual:
            self.toollock.LogThis("cmd_SelectTool: T" + str(self.name) + "- Not Virtual - Pickup")
            self.Pickup()
        else:
            if current_tool_id >= 0:                 # If still has a selected tool: (This tool is a virtual tool with same physical tool as the last)
                current_tool = self.printer.lookup_object('tool ' + str(current_tool_id))
                self.toollock.LogThis("cmd_SelectTool: T" + str(self.name) + "- Virtual - Tool is not Dropped - ")
                if self.physical_parent_id >= 0 and self.physical_parent_id == current_tool.get_status()["physical_parent_id"]:
                    self.toollock.LogThis("cmd_SelectTool: T" + str(self.name) + "- Virtual - Same physical tool - Pickup")
                    current_tool.UnloadVirtual()
                    self.LoadVirtual()
                    return ""
                else:
                    self.toollock.LogThis("cmd_SelectTool: T" + str(self.name) + "- Virtual - Not Same physical tool")
                    # Shouldn't reach this because it is dropped in previous.
                    #self.Pickup()
            else:
                self.toollock.LogThis("cmd_SelectTool: T" + str(self.name) + "- Virtual - Tool is dropped")
                self.Pickup()
                self.toollock.LogThis("cmd_SelectTool: T" + str(self.name) + "- Virtual - Picked up tool and now Loading tool.")
                # To be implemented

        self.toollock.LogThis("T%d Loaded" % (int(self.name)))
        self.toollock.SaveCurrentTool(self.name)

    def Pickup(self):
        # Check if homed
        if not self.toollock.PrinterIsHomedForToolchange():
            raise self.printer.command_error("Tool.Pickup: Printer not homed and Lazy homing option is: " + self.lazy_home_when_parking)
            return None

        # If has an extruder then activate that extruder.
        if self.extruder is not None:
            self.gcode.run_script_from_command(
                "ACTIVATE_EXTRUDER extruder=%s" % 
                (self.extruder))

        # Run the gcode for pickup.
        try:
            context = self.pickup_gcode_template.create_template_context()
            context['myself'] = self.get_status()
            context['toollock'] = self.toollock.get_status()
            self.pickup_gcode_template.run_gcode_from_command(context)
            
            
        except Exception:
            logging.exception("Pickup gcode: Script running error")

        # Restore fan if has a fan.
        if self.fan is not None:
            self.gcode.run_script_from_command(
                "SET_FAN_SPEED FAN=" + self.fan + " SPEED=" + str(self.toollock.get_status()['saved_fan_speed'])) #  self.toollock.get_saved_fan_speed()) )

        # Set Tool specific input shaper.
        if self.shaper_freq_x != 0 or self.shaper_freq_y != 0:
            cmd = ("SET_INPUT_SHAPER" +
                " SHAPER_FREQ_X=" + str(self.shaper_freq_x) +
                " SHAPER_FREQ_Y=" + str(self.shaper_freq_y) +
                " DAMPING_RATIO_X=" + str(self.shaper_damping_ratio_x) +
                " DAMPING_RATIO_Y=" + str(self.shaper_damping_ratio_y) +
                " SHAPER_TYPE_X=" + str(self.shaper_type_x) +
                " SHAPER_TYPE_Y=" + str(self.shaper_type_y) )
            self.toollock.LogThis("Pickup_inpshaper: " + cmd)
            self.gcode.run_script_from_command(cmd)

        # Save current picked up tool and print on screen.
        self.toollock.SaveCurrentTool(self.name)
        self.toollock.LogThis("T%d picked up." % (self.name))

    def Dropoff(self):
        # Check if homed
        if not self.toollock.PrinterIsHomedForToolchange():
            self.toollock.LogThis("Tool.Dropoff: Printer not homed and Lazy homing option is: " + str(self.lazy_home_when_parking), 1)
            return None

        # Turn off fan if has a fan.
        if self.fan is not None:
            self.gcode.run_script_from_command(
                "SET_FAN_SPEED FAN=" + self.fan + " SPEED=0" )
            
        # Run the gcode for dropoff.
        try:
            context = self.dropoff_gcode_template.create_template_context()
            context['myself'] = self.get_status()
            context['toollock'] = self.toollock.get_status()
            self.dropoff_gcode_template.run_gcode_from_command(context)         
            
        except Exception:
            logging.exception("Dropoff gcode: Script running error")

        self.toollock.SaveCurrentTool(-1)   # Dropoff successfull

    def LoadVirtual(self):
        self.toollock.LogThis("LoadVirtual: Virtual tools not implemented yet. T%d." % self.name, 0 )
        self.toollock.SaveCurrentTool(self.name)

    def UnloadVirtual(self):
        self.toollock.LogThis("UnloadVirtual: Virtual tools not implemented yet. T%d." % self.name, 0 )

    def set_offset(self, **kwargs):
        for i in kwargs:
            if i == "x_pos":
                self.offset[0] = float(kwargs[i])
            elif i == "x_adjust":
                self.offset[0] = float(self.offset[0]) + float(kwargs[i])
            elif i == "y_pos":
                self.offset[1] = float(kwargs[i])
            elif i == "y_adjust":
                self.offset[1] = float(self.offset[1]) + float(kwargs[i])
            elif i == "z_pos":
                self.offset[2] = float(kwargs[i])
            elif i == "z_adjust":
                self.offset[2] = float(self.offset[2]) + float(kwargs[i])

        self.toollock.LogThis("T%d offset now set to: %f, %f, %f." % (int(self.name), float(self.offset[0]), float(self.offset[1]), float(self.offset[2])))

    def set_heater(self, **kwargs):
        if self.extruder is None:
            self.toollock.LogThis("set_heater: T%d has no extruder! Nothing to do." % self.name )
            return None

        #if self.physical_parent_id >= 0 and self.physical_parent_id != self.name:
        #    physical_tool = self.physical_parent_id
        #else:
        #    physical_tool = self

        heater = self.printer.lookup_object(self.extruder).get_heater()

        for i in kwargs:
            if i == "heater_active_temp":
                self.heater_active_temp = kwargs[i]
                if int(self.heater_state) == 2:
                    heater.set_temp(self.heater_active_temp)
            elif i == "heater_standby_temp":
                self.heater_standby_temp = kwargs[i]
            elif i == "idle_to_standby_time":
                self.idle_to_standby_time = kwargs[i]
            elif i == "idle_to_powerdown_time":
                self.idle_to_powerdown_time = kwargs[i]

        # Change Active mode:
        if "heater_state" in kwargs:
            chng_state = kwargs["heater_state"]
            if chng_state == 0:                                                                         # If Change to Shutdown
                self.timer_idle_to_standby.set_timer(0)
                self.timer_idle_to_powerdown.set_timer(0.1)
            elif chng_state == 2:
                self.timer_idle_to_standby.set_timer(0)
                self.timer_idle_to_powerdown.set_timer(0)
                heater.set_temp(self.heater_active_temp)
            elif chng_state == 1:                                                                       # Else If Standby
                curtime = self.printer.get_reactor().monotonic()
                if int(self.heater_state) == 2 and int(self.heater_standby_temp) < int(heater.get_status(curtime)["temperature"]):
                    self.timer_idle_to_standby.set_timer(self.idle_to_standby_time)
                    self.timer_idle_to_powerdown.set_timer(self.idle_to_powerdown_time)
                else:                                                                                   # Else (Standby temperature is lower than the current temperature)
                    self.toollock.LogThis("set_heater: T%d standbytemp:%d;heater_state:%d; current_temp:%d." % (self.name, int(self.heater_state), int(self.heater_standby_temp), int(heater.get_status(curtime)["temperature"])))
                    self.timer_idle_to_standby.set_timer(0.1)
                    self.timer_idle_to_powerdown.set_timer(self.idle_to_powerdown_time)
            self.heater_state = kwargs["heater_state"]
            self.toollock.LogThis("set_heater: T%d heater_state now set to:%d." % (int(self.name), int(self.heater_state)))

    def get_pickup_gcode(self):
        return self.pickup_gcode

    def get_dropoff_gcode(self):
        return self.dropoff_gcode

    def get_timer_to_standby(self):
        return self.timer_idle_to_standby

    def get_timer_to_powerdown(self):
        return self.timer_idle_to_powerdown

    def get_status(self, eventtime= None):
        status = {
            "name": self.name,
            "is_virtual": self.is_virtual,
            "physical_parent_id": self.physical_parent_id,
            "extruder": self.extruder,
            "fan": self.fan,
            "lazy_home_when_parking": self.lazy_home_when_parking,
            "meltzonelength": self.meltzonelength,
            "zone": self.zone,
            "park": self.park,
            "offset": self.offset,
            "heater_state": self.heater_state,
            "heater_active_temp": self.heater_active_temp,
            "heater_standby_temp": self.heater_standby_temp,
            "idle_to_standby_time": self.idle_to_standby_time,
            "idle_to_powerdown_time": self.idle_to_powerdown_time,
            "shaper_freq_x": self.shaper_freq_x,
            "shaper_freq_y": self.shaper_freq_y,
            "shaper_type_x": self.shaper_type_x,
            "shaper_type_y": self.shaper_type_y,
            "shaper_damping_ratio_x": self.shaper_damping_ratio_x,
            "shaper_damping_ratio_y": self.shaper_damping_ratio_y,
            "extra_extrude_mm": self.extra_extrude_mm,
            "cooling_tube_retraction":self.cooling_tube_retraction,
            "hotend_type":self.hotend_type
        }
        return status

    # Based on DelayedGcode.
class ToolStandbyTempTimer:
    def __init__(self, printer, tool_id, temp_type):
        self.printer = printer
        self.tool_id = tool_id
        self.duration = 0.
        self.temp_type = temp_type      # 0= Time to shutdown, 1= Time to standby.

        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.timer_handler = None
        self.inside_timer = self.repeat = False
        self.printer.register_event_handler("klippy:ready", self._handle_ready)
        self.toollock = self.printer.lookup_object('toollock')

    def _handle_ready(self):
        self.timer_handler = self.reactor.register_timer(
            self._standby_tool_temp_timer_event, self.reactor.NEVER)
    def _standby_tool_temp_timer_event(self, eventtime):
        self.inside_timer = True
        self.toollock.LogThis("_standby_tool_temp_timer_event: Running for T" + str(self.tool_id) + ". temp_type:" + str(self.temp_type))
        try:
            tool = self.printer.lookup_object("tool " + str(self.tool_id))
            temperature = 0
            if self.temp_type == 1:
                temperature = tool.get_status()["heater_standby_temp"]
            heater = self.printer.lookup_object(tool.extruder).get_heater()
            heater.set_temp(temperature)
        except Exception:
            self.toollock.LogThis("Failed to set Standby temp for tool T" + str(self.tool_id) + ".",0)
            logging.exception("Failed to set Standby temp for tool T" + str(self.tool_id) + ".")
        nextwake = self.reactor.NEVER
        if self.repeat:
            nextwake = eventtime + self.duration
        self.inside_timer = self.repeat = False
        return nextwake
    def set_timer(self, duration):
        self.toollock.LogThis("ToolStandbyTempTimer.set_timer: T" + str(self.tool_id) + "; temp_type:" + str(self.temp_type) + "; duration:" + str(duration) + ".", 1)
        self.duration = float(duration)
        if self.inside_timer:
            self.repeat = (self.duration != 0.)
        else:
            waketime = self.reactor.NEVER
            if self.duration:
                waketime = self.reactor.monotonic() + self.duration
            self.reactor.update_timer(self.timer_handler, waketime)
    def get_status(self, eventtime= None):
        status = {
            "tool": self.tool,
            "temp_type": self.temp_type,
            "duration": self.duration
        }
        return status

    # Todo: 
    # Inspired by https://github.com/jschuh/klipper-macros/blob/main/layers.cfg
class MeanLayerTime:
    def __init__(self, printer):
        # Run before toolchange to set time like in StandbyToolTimer.
        # Save time for last 5 (except for first) layers
        # Provide a mean layer time.
        # Have Tool have a min and max 2standby time.
        # If mean time for 3 layers is higher than max, then set min time.
        # Reset time if layer time is higher than max time. Pause or anything else that has happened.
        # Function to reset layer times.
        pass


def load_config_prefix(config):
    return Tool(config)
