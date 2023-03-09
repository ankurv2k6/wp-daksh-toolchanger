# Nozzle alignment module for 3d kinematic probes. 
#
# This module has been adapted from code written by Kevin O'Connor <kevin@koconnor.net> and Martin Hierholzer <martin@hierholzer.info>

import logging
import pins
from . import manual_probe

HINT_TIMEOUT = """
If the probe did not move far enough to trigger, then
consider reducing/increasing the axis minimum/maximum
position so the probe can travel further (the minimum
position can be negative).
"""

direction_types = {'x+': [0,+1],'x-': [0,-1],'y+': [1,+1],'y-': [1,-1],'z+': [2,+1],'z-': [2,-1]}


class PrinterProbeMultiAxis:
    def __init__(self, config, mcu_probe_x, mcu_probe_y, mcu_probe_z):
        self.printer = config.get_printer()
        self.name = config.get_name()
        self.mcu_probe = [mcu_probe_x, mcu_probe_y, mcu_probe_z]
        self.speed = config.getfloat('speed', 5.0, above=0.)
        self.lift_speed = config.getfloat('lift_speed', self.speed, above=0.)
        self.max_travel = config.getfloat("max_travel", 4, above=0)
        self.x_offset = config.getfloat('x_offset', 0.)
        self.y_offset = config.getfloat('y_offset', 0.)
        self.z_offset = config.getfloat('z_offset', 0.)
        self.probe_calibrate_x = 0.
        self.probe_calibrate_y = 0.
        self.probe_calibrate_z = 0.
        self.last_state = False
        self.last_result = [0., 0., 0.]
        self.last_x_result = 0.
        self.last_y_result = 0.
        self.last_z_result = 0.
        self.gcode_move = self.printer.load_object(config, "gcode_move")

        xconfig = config.getsection('stepper_x')
        yconfig = config.getsection('stepper_y')
        zconfig = config.getsection('stepper_z')
        # Note: This may not work for all kinematics (delta)...
        self.axis_range = [ { -1: xconfig.getfloat('position_min', 0.),
                              +1: xconfig.getfloat('position_max')      },
                            { -1: yconfig.getfloat('position_min', 0.),
                              +1: yconfig.getfloat('position_max')      },
                            { -1: zconfig.getfloat('position_min', 0.),
                              +1: zconfig.getfloat('position_max')      } ]

        # Multi-sample support (for improved accuracy)
        self.sample_count = config.getint('samples', 1, minval=1)
        self.sample_retract_dist = config.getfloat('sample_retract_dist', 2.,
                                                   above=0.)
        atypes = {'median': 'median', 'average': 'average'}
        self.samples_result = config.getchoice('samples_result', atypes,
                                               'average')
        self.samples_tolerance = config.getfloat('samples_tolerance', 0.100,
                                                 minval=0.)
        self.samples_retries = config.getint('samples_tolerance_retries', 0,
                                             minval=0)
        # Register xy_virtual_endstop pin
        self.printer.lookup_object('pins').register_chip('probe_multi_axis', self)
        # Register homing event handlers
        #self.printer.register_event_handler("homing:homing_move_begin",
        #                                    self._handle_homing_move_begin)
        #self.printer.register_event_handler("homing:homing_move_end",
        #                                    self._handle_homing_move_end)
        self.printer.register_event_handler("homing:home_rails_begin",
                                            self._handle_home_rails_begin)
        self.printer.register_event_handler("homing:home_rails_end",
                                            self._handle_home_rails_end)
        # Register PROBE/QUERY_PROBE commands
        self.gcode = self.printer.lookup_object('gcode')
        self.gcode.register_command('PROBE_MULTI_AXIS', self.cmd_PROBE,
                                    desc=self.cmd_PROBE_help)
        self.gcode.register_command('QUERY_PROBE_MULTI_AXIS', self.cmd_QUERY_PROBE,
                                    desc=self.cmd_QUERY_PROBE_help)
        self.gcode.register_command('PROBE_MULTI_AXIS_ACCURACY',
                                    self.cmd_PROBE_ACCURACY,
                                    desc=self.cmd_PROBE_ACCURACY_help)
        self.gcode.register_command('QUERY_PROBE_MULTI_AXIS_STATUS',
                                    self.cmd_GET_PROBE_RESULT,
                                    desc=self.cmd_GET_PROBE_RESULT_help)
    #def _handle_homing_move_begin(self, hmove):
    #    if self.mcu_probe[0] in hmove.get_mcu_endstops():
    #        self.mcu_probe[0].probe_prepare(hmove)
    #    if self.mcu_probe1[1] in hmove.get_mcu_endstops():
    #        self.mcu_probe[1].probe_prepare(hmove)
    #def _handle_homing_move_end(self, hmove):
    #    if self.mcu_probe[0] in hmove.get_mcu_endstops():
    #        self.mcu_probe[0].probe_finish(hmove)
    #    if self.mcu_probe[1] in hmove.get_mcu_endstops():
    #        self.mcu_probe[1].probe_finish(hmove)
    def _handle_home_rails_begin(self, homing_state, rails):
        endstops = [es for rail in rails for es, name in rail.get_endstops()]
    def _handle_home_rails_end(self, homing_state, rails):
        endstops = [es for rail in rails for es, name in rail.get_endstops()]
    def setup_pin(self, pin_type, pin_params):
        if pin_type != 'endstop' or pin_params['pin'] != 'xy_virtual_endstop':
            raise pins.error("Probe virtual endstop only useful as endstop pin")
        if pin_params['invert'] or pin_params['pullup']:
            raise pins.error("Can not pullup/invert probe virtual endstop")
        return self.mcu_probe
    def get_lift_speed(self, gcmd=None):
        if gcmd is not None:
            return gcmd.get_float("LIFT_SPEED", self.lift_speed, above=0.)
        return self.lift_speed
    def _probe(self, speed, axis, sense):
        toolhead = self.printer.lookup_object('toolhead')
        curtime = self.printer.get_reactor().monotonic()
        if 'x' not in toolhead.get_status(curtime)['homed_axes'] or            \
           'y' not in toolhead.get_status(curtime)['homed_axes'] or            \
           'z' not in toolhead.get_status(curtime)['homed_axes']:
            raise self.printer.command_error("Must home before probe")
        phoming = self.printer.lookup_object('homing')
        pos = toolhead.get_position()
        pos[axis] = self.axis_range[axis][sense]
        try:
            epos = phoming.probing_move(self.mcu_probe[axis], pos, speed)
        except self.printer.command_error as e:
            reason = str(e)
            if "Timeout during endstop homing" in reason:
                reason += HINT_TIMEOUT
            raise self.printer.command_error(reason)
        #self.gcode.respond_info("probe at %.3f,%.3f is z=%.6f"
        self.gcode.respond_info("Probe made contact at %.6f,%.6f,%.6f"
                                % (epos[0], epos[1], epos[2]))
        return epos[:3]
    def _move(self, coord, speed):
        self.printer.lookup_object('toolhead').manual_move(coord, speed)
    def _calc_mean(self, positions):
        count = float(len(positions))
        return [sum([pos[i] for pos in positions]) / count
                for i in range(3)]
    def _calc_median(self, positions, axis):
        axis_sorted = sorted(positions, key=(lambda p: p[axis]))
        middle = len(positions) // 2
        if (len(positions) & 1) == 1:
            # odd number of samples
            return axis_sorted[middle]
        # even number of samples
        return self._calc_mean(axis_sorted[middle-1:middle+1])
    def run_probe(self, gcmd):
        speed = gcmd.get_float("PROBE_SPEED", self.speed, above=0.)
        direction = gcmd.get("DIRECTION").lower()
        if direction not in direction_types:
          raise self.printer.command_error("Wrong value for DIRECTION.")
          
        logging.info("run_probe direction = "+str(direction))
          
        (axis,sense) = direction_types[direction]

        logging.info("run_probe axis = %d, sense = %d" % (axis,sense))
        
        lift_speed = self.get_lift_speed(gcmd)
        sample_count = gcmd.get_int("SAMPLES", self.sample_count, minval=1)
        sample_retract_dist = gcmd.get_float("SAMPLE_RETRACT_DIST",
                                             self.sample_retract_dist, above=0.)
        samples_tolerance = gcmd.get_float("SAMPLES_TOLERANCE",
                                           self.samples_tolerance, minval=0.)
        samples_retries = gcmd.get_int("SAMPLES_TOLERANCE_RETRIES",
                                       self.samples_retries, minval=0)
        samples_result = gcmd.get("SAMPLES_RESULT", self.samples_result)
        
#         travel_ave = sum(travel_dist) / len(travel_dist)
#         self.gcode.respond_info("Average: %0.6f" % z_ave)
#         travel_adjust = []
#         for travel in travel_dist:
#             travel_max.append(travel_ave - travel)
        
#         travel_max = max(z_travel)
#         if travel_max > self.max_travel:
#             raise self.gcode.error("Aborting"
#                                    " required travel %0.6f"
#                                    " is greater than max_travel %0.6f"
#                                    % (travel_max, self.max_travel))
            
        probe_start = self.printer.lookup_object('toolhead').get_position()
        retries = 0
        positions = []
        while len(positions) < sample_count:
            # Probe position
            pos = self._probe(speed, axis, sense)
            positions.append(pos)
            # Check samples tolerance
            axis_positions = [p[axis] for p in positions]
            if max(axis_positions) - min(axis_positions) > samples_tolerance:
                if retries >= samples_retries:
                    raise gcmd.error("Probe samples exceed samples_tolerance")
                gcmd.respond_info("Probe samples exceed tolerance. Retrying...")
                retries += 1
                positions = []
            # Retract
            if len(positions) < sample_count:
                liftpos = probe_start
                liftpos[axis] = pos[axis] - sense*sample_retract_dist
                self._move(liftpos, lift_speed)
        # Calculate and return result
        if samples_result == 'median':
            return self._calc_median(positions, axis)
        return self._calc_mean(positions)
    cmd_PROBE_help = "Probe Z-height at current XY position"
    def cmd_PROBE(self, gcmd):
        pos = self.run_probe(gcmd)
        gcmd.respond_info("Result is x,y,z=%.6f,%.6f,%.6f" % (pos[0],pos[1],pos[2]))
        self.last_result = pos
        self.last_x_result = pos[0]
        self.last_y_result = pos[1]
        self.last_z_result = pos[2]
        self._move(pos, self.get_lift_speed(gcmd))
    cmd_QUERY_PROBE_help = "Return the status of the xy-probe"
    def cmd_QUERY_PROBE(self, gcmd):
        toolhead = self.printer.lookup_object('toolhead')
        print_time = toolhead.get_last_move_time()
        res = self.mcu_probe[0].query_endstop(print_time)
        self.last_state = res
        gcmd.respond_info("probe: %s" % (["open", "TRIGGERED"][not not res],))
    def get_status(self, eventtime):
        return {'last_query': self.last_state,
                'last_result': self.last_result,
                'last_x_result': self.last_x_result,
                'last_y_result': self.last_y_result,
                'last_z_result': self.last_z_result}
    cmd_GET_PROBE_RESULT_help = "Return the status of the xy-probe"
    def cmd_GET_PROBE_RESULT(self, eventtime):
        return {'last_query': self.last_state,
                'last_result': self.last_result,
                'last_x_result': self.last_x_result,
                'last_y_result': self.last_y_result,
                'last_z_result': self.last_z_result}
    cmd_PROBE_ACCURACY_help = "Probe Z-height accuracy at current XY position"
    def cmd_PROBE_ACCURACY(self, gcmd):
        speed = gcmd.get_float("PROBE_SPEED", self.speed, above=0.)
        direction = gcmd.get("DIRECTION")
        if direction not in direction_types:
          raise self.printer.command_error("Wrong value for DIRECTION.")
        (axis,sense) = direction_types[direction]
        lift_speed = self.get_lift_speed(gcmd)
        sample_count = gcmd.get_int("SAMPLES", 10, minval=1)
        sample_retract_dist = gcmd.get_float("SAMPLE_RETRACT_DIST",
                                             self.sample_retract_dist, above=0.)
        toolhead = self.printer.lookup_object('toolhead')
        pos = toolhead.get_position()
        gcmd.respond_info("PROBE_ACCURACY at X:%.3f Y:%.3f Z:%.3f"
                          " (samples=%d retract=%.3f"
                          " speed=%.1f lift_speed=%.1f)\n"
                          % (pos[0], pos[1], pos[2],
                             sample_count, sample_retract_dist,
                             speed, lift_speed))
        # Probe bed sample_count times
        positions = []
        while len(positions) < sample_count:
            # Probe position
            pos = self._probe(speed, axis, sense)
            positions.append(pos)
            # Retract
            liftpos = toolhead.get_position()
            liftpos[axis] = pos[axis] - sense*sample_retract_dist
            self._move(liftpos, lift_speed)
        # Calculate maximum, minimum and average values
        max_value = max([p[axis] for p in positions])
        min_value = min([p[axis] for p in positions])
        range_value = max_value - min_value
        avg_value = self._calc_mean(positions)[axis]
        median = self._calc_median(positions, axis)[axis]
        # calculate the standard deviation
        deviation_sum = 0
        for i in range(len(positions)):
            deviation_sum += pow(positions[i][axis] - avg_value, 2.)
        sigma = (deviation_sum / len(positions)) ** 0.5
        # Show information
        gcmd.respond_info(
            "probe accuracy results: maximum %.6f, minimum %.6f, range %.6f, "
            "average %.6f, median %.6f, standard deviation %.6f" % (
            max_value, min_value, range_value, avg_value, median, sigma))

# Endstop wrapper that enables probe specific features
class ProbeXEndstopWrapper:
    def __init__(self, config):
        self.printer = config.get_printer()
        # Create an "endstop" object to handle the probe pin
        ppins = self.printer.lookup_object('pins')
        pin = config.get('pin')
        ppins.allow_multi_use_pin(pin.replace('^','').replace('!',''))
        pin_params = ppins.lookup_pin(pin, can_invert=True, can_pullup=True)
        mcu = pin_params['chip']
        self.mcu_endstop = mcu.setup_pin('endstop', pin_params)
        self.printer.register_event_handler('klippy:mcu_identify',
                                            self._handle_mcu_identify)
        # Wrappers
        self.get_mcu = self.mcu_endstop.get_mcu
        self.add_stepper = self.mcu_endstop.add_stepper
        self.get_steppers = self.mcu_endstop.get_steppers
        self.home_start = self.mcu_endstop.home_start
        self.home_wait = self.mcu_endstop.home_wait
        self.query_endstop = self.mcu_endstop.query_endstop
    def _handle_mcu_identify(self):
        kin = self.printer.lookup_object('toolhead').get_kinematics()
        for stepper in kin.get_steppers():
            if stepper.is_active_axis('x'):
                self.add_stepper(stepper)
    def get_position_endstop(self):
        return self.position_endstop

# Endstop wrapper that enables probe specific features
class ProbeYEndstopWrapper:
    def __init__(self, config):
        self.printer = config.get_printer()
        # Create an "endstop" object to handle the probe pin
        ppins = self.printer.lookup_object('pins')
        pin = config.get('pin')
        pin_params = ppins.lookup_pin(pin, can_invert=True, can_pullup=True)
        mcu = pin_params['chip']
        self.mcu_endstop = mcu.setup_pin('endstop', pin_params)
        self.printer.register_event_handler('klippy:mcu_identify',
                                            self._handle_mcu_identify)
        # Wrappers
        self.get_mcu = self.mcu_endstop.get_mcu
        self.add_stepper = self.mcu_endstop.add_stepper
        self.get_steppers = self.mcu_endstop.get_steppers
        self.home_start = self.mcu_endstop.home_start
        self.home_wait = self.mcu_endstop.home_wait
        self.query_endstop = self.mcu_endstop.query_endstop
    def _handle_mcu_identify(self):
        kin = self.printer.lookup_object('toolhead').get_kinematics()
        for stepper in kin.get_steppers():
            if stepper.is_active_axis('y'):
                self.add_stepper(stepper)
    def get_position_endstop(self):
        return self.position_endstop

# Endstop wrapper that enables probe specific features
class ProbeZEndstopWrapper:
    def __init__(self, config):
        self.printer = config.get_printer()
        # Create an "endstop" object to handle the probe pin
        ppins = self.printer.lookup_object('pins')
        pin = config.get('pin')
        pin_params = ppins.lookup_pin(pin, can_invert=True, can_pullup=True)
        mcu = pin_params['chip']
        self.mcu_endstop = mcu.setup_pin('endstop', pin_params)
        self.printer.register_event_handler('klippy:mcu_identify',
                                            self._handle_mcu_identify)
        # Wrappers
        self.get_mcu = self.mcu_endstop.get_mcu
        self.add_stepper = self.mcu_endstop.add_stepper
        self.get_steppers = self.mcu_endstop.get_steppers
        self.home_start = self.mcu_endstop.home_start
        self.home_wait = self.mcu_endstop.home_wait
        self.query_endstop = self.mcu_endstop.query_endstop
    def _handle_mcu_identify(self):
        kin = self.printer.lookup_object('toolhead').get_kinematics()
        for stepper in kin.get_steppers():
            if stepper.is_active_axis('z'):
                self.add_stepper(stepper)
    def get_position_endstop(self):
        return self.position_endstop
    
def load_config(config):
    return PrinterProbeMultiAxis(config, ProbeXEndstopWrapper(config), ProbeYEndstopWrapper(config), ProbeZEndstopWrapper(config))