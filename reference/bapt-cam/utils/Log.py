import os
import traceback
import FreeCAD as App


class Level:
    RESET = -1
    CRITICAL = 0
    ERROR = 1
    WARNING = 2
    DEBUG = 3
    INFO = 4
    TRACE = 5
    ALL = 6

    def _names(level):
        return {
            Level.RESET: "RESET",
            Level.CRITICAL: "CRITICAL",
            Level.ERROR: "ERROR",
            Level.WARNING: "WARNING",
            Level.DEBUG: "DEBUG",
            Level.INFO: "INFO",
            Level.TRACE: "TRACE",
            Level.ALL: "ALL",
        }[level]


_module_levels = {}
_default_level = Level.INFO


def setLevel(level: Level, module=None) -> None:
    """
    Set the logging level. Messages with a level less than the set level will be ignored.
    Possible exceptions: (Exception).
    """
    global _current_level
    _current_level = level

    global _module_levels
    if module is not None:
        if level == Level.RESET:
            if module in _module_levels:
                del _module_levels[module]
        else:

            _module_levels[module] = level


def getLevel(module=None) -> Level:
    """
    Get the current logging level.
    Possible exceptions: (Exception).
    """
    global _module_levels

    if module is not None:
        return _module_levels.get(module, _default_level)
    return _current_level


def thisModule():
    """returns the module id of the caller, can be used for setLevel, getLevel and trackModule."""
    return _caller()[0]


def _caller():
    """internal function to determine the calling module."""
    filename, line, func, text = traceback.extract_stack(limit=3)[0]
    return os.path.splitext(os.path.basename(filename))[0], line, func


def _log(level: Level, module_line_func, message: str) -> None:
    """internal function to log a message."""
    module, line, func = module_line_func
    current_level = getLevel(module)
    if current_level >= level:
        message = f"{message} (at {module}:{line} in {func})\n"

        match level:
            case Level.CRITICAL | Level.ERROR:
                App.Console.PrintError(message)
            case Level.WARNING:
                App.Console.PrintWarning(message)
            case Level.DEBUG | Level.INFO:
                App.Console.PrintMessage(message)
            case Level.TRACE:
                App.Console.PrintLog(message)
            case _:
                App.Console.PrintMessage(message)
        return message
    return None


def baptDebug(message: str) -> None:
    """Log a debug message."""
    return _log(Level.DEBUG, _caller(), message)


def baptError(message: str) -> None:
    """Log an error message."""
    return _log(Level.CRITICAL, _caller(), message)
