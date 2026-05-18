import traceback
import os

from BaptPreferences import BaptPreferences


class GcodeWriter:
    current_position = {'X': None, 'Y': None, 'Z': None}
    current_feed = None

    def __init__(self):
        self.lines = []
        self.current_position = {'X': None, 'Y': None, 'Z': None}
        self.current_feed = None
        prefs = BaptPreferences()
        self.DEBUG = prefs.debugGcode

    def _caller():
        """internal function to determine the calling module."""
        filename, line, func, text = traceback.extract_stack(limit=3)[0]
        return os.path.splitext(os.path.basename(filename))[0], line, func

    def linearMove(self, arg, feed: float = None, rapid=False):
        line = 'G0' if rapid else 'G1'

        if 'comp' in arg:
            line += f" {arg['comp']}"

        for axis in ['X', 'Y', 'Z']:
            if axis in arg:
                if self.current_position[axis] is None or arg[axis] != self.current_position[axis]:
                    line += f" {axis}{arg[axis]:.3f}"
                self.current_position[axis] = arg[axis]

        if feed is not None and feed != self.current_feed:
            line += f" F{feed:.1f}"
            self.current_feed = feed

        if self.DEBUG:
            module, line_num, func = GcodeWriter._caller()
            line += f" ; (at {module}:{line_num} in {func})"

        self.lines.append(line)

    def arcMove(self, arg, feed: float = None):
        cmd = 'G3' if arg.get('CCW', False) else 'G2'
        line = cmd
        for axis in ['X', 'Y', 'Z']:
            if axis in arg:
                if True:  # arg[axis] != self.current_position[axis]:
                    line += f" {axis}{arg[axis]:.3f}"
                self.current_position[axis] = arg[axis]
        if 'I' in arg and 'J' in arg:
            line += f" I{arg['I']:.3f} J{arg['J']:.3f}"
        elif 'R' in arg:
            line += f" R{arg['R']:.3f}"
        else:
            raise ValueError("Arc move requires either I/J or R parameters.")

        if feed is not None and feed != self.current_feed:
            line += f" F{feed:.1f}"
            self.current_feed = feed

        if self.DEBUG:
            module, line_num, func = GcodeWriter._caller()
            line += f" ; (at {module}:{line_num} in {func})"
        self.lines.append(line)

    def comment(self, text):
        self.lines.append(f"; {text}")
        if self.DEBUG:
            module, line_num, func = GcodeWriter._caller()
            self.lines[-1] += f" (at {module}:{line_num} in {func})"
