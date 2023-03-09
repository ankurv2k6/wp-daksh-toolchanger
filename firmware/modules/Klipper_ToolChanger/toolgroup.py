# Toolgroup support
#
# Copyright (C) 2022  Andrei Ignat <andrei@ignat.se>
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging

class ToolGroup:
    def __init__(self, config):
        self.printer = config.get_printer()
        gcode_macro = self.printer.load_object(config, 'gcode_macro')

        try:
            _, name = config.get_name().split(' ', 1)
            self.name = int(name)
        except ValueError:
            raise config.error(
                    "Name of section '%s' contains illegal characters. Use only integer ToolGroup number."
                    % (config.get_name()))

        self.is_virtual = config.getboolean(    # If True then must have a physical_parent declared and shares extruder, hotend and fan with the physical_parent
            'is_virtual', False)
        self.physical_parent_id = config.getint(   # Tool used as a Physical parent for all toos of this group. Only used if the tool i virtual.
            'physical_parent', None)
        self.lazy_home_when_parking = config.get('lazy_home_when_parking', 0)    # (default: 0) - When set to 1, will home unhomed XY axes if needed and will not move any axis if already homed and parked. 2 Will also home Z if not homed.
       # -1 = none, 1= Only load filament, 2= Wipe in front of carriage, 3= Pebble wiper, 4= First Silicone, then pebble. Defaults to 0.
        self.pickup_gcode = config.get('pickup_gcode', '')
        self.dropoff_gcode = config.get('dropoff_gcode', '')
        self.meltzonelength = config.get('meltzonelength', 0)
        self.idle_to_standby_time = config.getfloat( 'idle_to_standby_time', 30, minval = 0.1)
        self.idle_to_powerdown_time = config.getfloat( 'idle_to_powerdown_time', 600, minval = 0.1)

    def get_pickup_gcode(self):
        return self.pickup_gcode

    def get_dropoff_gcode(self):
        return self.dropoff_gcode

    def get_status(self, eventtime= None):
        status = {
            "is_virtual": self.is_virtual,
            "physical_parent_id": self.physical_parent_id,
            "lazy_home_when_parking": self.lazy_home_when_parking,
            "meltzonelength": self.meltzonelength,
            "idle_to_standby_time": self.idle_to_standby_time,
            "idle_to_powerdown_time": self.idle_to_powerdown_time
        }
        return status

def load_config_prefix(config):
    return ToolGroup(config)




