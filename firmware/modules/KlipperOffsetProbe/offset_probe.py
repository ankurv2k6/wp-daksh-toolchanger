import logging
from . import probe
from . import gcode_macro

HINT_TIMEOUT = """
If the probe did not move far enough to trigger, consider
reducing the Z axis minimum position so the probe can travel further.
The probe will not move further than the minimum Z position.
"""

class OffsetProbe:
  def __init__(self, config, mcu_probe):
    self.printer = config.get_printer()
    self.name = config.get_name()
    self.mcu_probe = mcu_probe

    self.probe_x = config.getfloat('probe_x', 0.)
    self.probe_y = config.getfloat('probe_y', 0.)

    # Offset between the origin of the toolhead and the probe
    self.x_offset = config.getfloat('x_offset', 0.)
    self.y_offset = config.getfloat('y_offset', 0.)
    # The trigger distance of the probe, the plunge height of a switch based probe
    self.z_offset = config.getfloat('z_offset', 0.)

    self.switch_offset = config.getfloat('switch_offset', 0.)

    # The starting Z height when probing tools - all tools must be accurate to within this value
    self.tool_probe_z = config.getfloat('reprobe_height', 1., above=0.)

    # Plunge speed
    self.speed = config.getfloat('speed', 5.0, above=0.)
    # Speed to move Z away from the probe after trigger
    self.lift_speed = config.getfloat('lift_speed', self.speed, above=0.)
    self.lift_distance = config.getfloat('lift_distance', 0.5, above=0.)
    # X/Y move speeds
    self.move_speed = config.getfloat('move_speed', 100.0, above=0.)

    # Gcode-based moves, this moves the toolhead relative to the tool offsets
    self.gcode_move = self.printer.load_object(config, "gcode_move")

    # Infer Z position to move to during a probe
    if config.has_section('stepper_z'):
        zconfig = config.getsection('stepper_z')
        self.z_position = zconfig.getfloat('position_min', 0.,
                                            note_valid=False)
    else:
        pconfig = config.getsection('printer')
        self.z_position = pconfig.getfloat('minimum_z_position', 0.,
                                            note_valid=False)

    # Register custom gcode commands
    self.gcode = self.printer.lookup_object('gcode')
    self.gcode.register_command('OFFSET_PROBE', self.cmd_OFFSET_PROBE,
                                desc=self.cmd_OFFSET_PROBE_help)

    gcode_macro = self.printer.lookup_object('gcode_macro')
    self.start_gcode = gcode_macro.load_template(config, 'start_gcode', '')
    self.end_gcode = gcode_macro.load_template(config, 'end_gcode', '')
    self.toolchange_gcode = []

    for i in range(99):
      gcode = config.get('toolchange_gcode_%d' % (i), None)
      if gcode is None:
        continue
      logging.info('Loaded toolchange gcode for extruder %d: %s', (i, gcode))
      self.toolchange_gcode.append(gcode_macro.load_template(config, 'toolchange_gcode_%d' % (i), ''))

  def get_lift_speed(self, gcmd=None):
    if gcmd is not None:
      return gcmd.get_float('LIFT_SPEED', self.lift_speed, above=0.)
    return self.lift_speed
  
  def get_offsets(self):
    return self.x_offset, self.y_offset, self.z_offset

  def _ensure_homed(self):
    toolhead = self.printer.lookup_object('toolhead')
    curtime = self.printer.get_reactor().monotonic()
    if 'z' not in toolhead.get_status(curtime)['homed_axes']:
      raise self.printer.command_error("Must home before offset probing")

  # Probe the bed at the current position using the given speed, and optionally use the original
  # probe instead of the offset probe
  def _probe(self, speed, use_probe=False):
    self._ensure_homed()

    toolhead = self.printer.lookup_object('toolhead')
    phoming = self.printer.lookup_object('homing')

    pos = toolhead.get_position()
    pos[2] = self.z_position

    mcu_probe = self.mcu_probe
    if use_probe:
      mcu_probe = self.printer.lookup_object('probe').mcu_probe

    try:
      epos = phoming.probing_move(mcu_probe, pos, speed)
    except self.printer.command_error as e:
      reason = str(e)
      if "Timeout during endstop homing" in reason:
        reason += HINT_TIMEOUT
      raise self.printer.command_error(reason)
    return epos[2]
  
  # Probe, then retract and re-probe at 1/2 speed
  def _accurate_probe(self, speed, use_probe=False):
    toolhead = self.printer.lookup_object('toolhead')
    start_z = self._probe(speed, use_probe)
    reprobe_speed = round(speed / 2)

    self._lift_between_probes(2)
    accurate_z = self._probe(reprobe_speed, use_probe)
    return accurate_z
    
  def _get_gcode_position(self, x=None, y=None, z=None):
    offsets = self.gcode_move.base_position

    if x is not None:
      x += offsets[0]
    if y is not None:
      y += offsets[1]
    if z is not None:
      z += offsets[2]
    return x, y, z
  
  def _lift_between_probes(self, dist=None):
    if dist is None:
      dist = self.lift_distance
    toolhead = self.printer.lookup_object('toolhead')
    liftpos = toolhead.get_position()
    liftpos[2] += dist
    toolhead.manual_move(liftpos, self.lift_speed)

  cmd_OFFSET_PROBE_help = "Calculate the offsets for all defined tools"
  def cmd_OFFSET_PROBE(self, gcmd):
    # Run the start gcode which hopefully undocks any tools
    self.start_gcode.run_gcode_from_command()

    # Move to the probe point, first offsetting the target by the probe offset amount
    toolhead = self.printer.lookup_object('toolhead')
    coord = [i for i in self._get_gcode_position(x=self.probe_x, y=self.probe_y)][:2] + toolhead.get_position()[2:]
    offset_x, offset_y, _ = self.get_offsets()
    coord[0] += offset_x
    coord[1] += offset_y

    toolhead.manual_move(coord, self.move_speed)

    base_z = self._accurate_probe(self.speed, True)
    self._lift_between_probes()

    # For each extruder, run T<extruder num> and then probe
    offsets = []
    for i in range(len(self.toolchange_gcode)):
      # Execute the toolchange script for this extruder
      toolchange_script = self.toolchange_gcode[i]
      toolchange_script.run_gcode_from_command()
      # Generate new offset coordinates based on the absolute probe pos, and the re-probe height
      curr_pos = toolhead.get_position()
      coord = [i for i in self._get_gcode_position(x=self.probe_x, y=self.probe_y, z=curr_pos[2])] + curr_pos[3:]

      # Move to the absolute probe point
      toolhead.manual_move(coord, self.move_speed)
      # Probe and get the new offset
      z = self._accurate_probe(self.speed)
      offsets.append(z - base_z + self.switch_offset)
      # gcmd.respond_info('Tool %d: %.6f' % (i, z))
      self._lift_between_probes()
    
    self.end_gcode.run_gcode_from_command()

    offset_str = []
    for i in range(len(offsets)):
      offset_str.append('T%d=%.6f' % (i, offsets[i]))
    gcmd.respond_info('Offsets: %s' % (', '.join(offset_str)))

    return offsets

def load_config(config):
  # Piggyback on the probe.ProbeEndstopWrapper which gives us z-endstop-registration
  return OffsetProbe(config, probe.ProbeEndstopWrapper(config))


