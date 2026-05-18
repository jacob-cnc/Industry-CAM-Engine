"""Machine constants derived from INI configuration.

Single source of truth for hardware limits, velocities, and encoder parameters.
These values match industry-cam.ini and the physical wiring map.

All X values are in DIAMETER (inches). Z values in inches.
"""

# =============================================================================
# Axis Travel Limits (machine coordinates)
# =============================================================================

X_MIN_LIMIT = -0.01       # inches (diameter) — soft limit
X_MAX_LIMIT = 4.25        # inches (diameter) — full retract / home position
X_HOME = 4.25             # inches (diameter)

Z_MIN_LIMIT = -0.01       # inches — soft limit
Z_MAX_LIMIT = 23.5        # inches — full travel
Z_HOME = 0.0              # inches — near headstock

# =============================================================================
# Axis Velocities & Acceleration
# =============================================================================

X_MAX_VELOCITY = 2.0      # inches/sec
Z_MAX_VELOCITY = 2.0      # inches/sec
MAX_ACCELERATION = 10.0   # inches/sec²

# Jog defaults
DEFAULT_JOG_VELOCITY = 1.0    # inches/sec
MAX_JOG_VELOCITY = 2.0        # inches/sec

# MPG jog increments (inches, diameter for X)
JOG_INCREMENTS = [0.0001, 0.001, 0.01, 0.1]
DEFAULT_JOG_INCREMENT_INDEX = 1  # 0.001"

# =============================================================================
# Spindle
# =============================================================================

SPINDLE_MAX_RPM = 3000
SPINDLE_MIN_RPM = 100
SPINDLE_DEFAULT_RPM = 500
SPINDLE_ENCODER_PPR = 1000     # Pulses per revolution
SPINDLE_ENCODER_SCALE = 4000   # PPR × 4 quadrature

# =============================================================================
# Steppers (UIRobot UIM8696PM)
# =============================================================================

X_STEP_SCALE = 54186.667      # steps/inch (diameter)
Z_STEP_SCALE = 27093.333      # steps/inch

# Step timing (nanoseconds)
DIRSETUP = 20000
DIRHOLD = 20000
STEPLEN = 5000
STEPSPACE = 5000

# =============================================================================
# Linear Encoders (Sino KA300/KA500)
# =============================================================================

ENCODER_SCALE = 5080           # counts/inch (5µm resolution)
ENCODER_RESOLUTION = 0.000197  # inches (5µm)

# =============================================================================
# PID Tuning (closed-loop stepper correction)
# =============================================================================

PID_P = 1000.0
PID_I = 0.0
PID_D = 0.0
PID_FF0 = 0.0
PID_FF1 = 1.0
PID_FF2 = 0.0
PID_DEADBAND = 0.000050        # inches
PID_MAX_OUTPUT = 2.5           # inches/sec (velocity command limit)
PID_MAX_ERROR = 0.0005         # inches

# Following error limits
FERROR = 0.005                 # inches — max following error at speed
MIN_FERROR = 0.001             # inches — max following error at rest

# =============================================================================
# Homing
# =============================================================================

# Homing strategy: manual jog to switch, then trigger homing
# HOME_SEARCH_VEL = 0 means no automatic search
X_HOME_SEQUENCE = 0            # X homes first
Z_HOME_SEQUENCE = 1            # Z homes second

# =============================================================================
# Mesa Hardware
# =============================================================================

MESA_IP = "192.168.1.121"
MESA_FIRMWARE = "7i96s_7i85sd.bin"

# Encoder channel assignments
ENCODER_X_LINEAR = 0           # 7i85S TB1 (not yet wired)
ENCODER_Z_LINEAR = 1           # 7i85S TB1 (not yet wired)
ENCODER_SPINDLE = 2            # 7i96S TB2
ENCODER_MPG_X = 3              # 7i85S TB2
ENCODER_MPG_Z = 4              # 7i85S TB3

# Stepgen channel assignments (NOTE: swapped from joint numbering!)
STEPGEN_Z = 0                  # TB1 Step/Dir 0 = Z axis (Joint 1)
STEPGEN_X = 1                  # TB1 Step/Dir 1 = X axis (Joint 0)

# GPIO assignments (7i96S TB3)
GPIO_HOME_Z = 0                # TB3 P1
GPIO_FREE_1 = 1                # TB3 P2 (formerly Limit Z+, now free)
GPIO_FREE_2 = 2                # TB3 P3 (formerly Limit X-, now free)
GPIO_HOME_X = 3                # TB3 P4
GPIO_ESTOP = 4                 # TB3 P5
GPIO_JOG_Z_MINUS = 5          # TB3 P6
GPIO_JOG_Z_PLUS = 6           # TB3 P7
GPIO_JOG_X_MINUS = 7          # TB3 P8
GPIO_JOG_X_PLUS = 8           # TB3 P9
GPIO_CYCLE_START = 9           # TB3 P10
GPIO_CYCLE_STOP = 10           # TB3 P11

# 7i85S GPIO (accent pins)
GPIO_CYCLE_PAUSE = 11          # Placeholder — confirm after firmware load
GPIO_JOG_SCALE_SEL0 = 12      # Rotary switch bit 0
GPIO_JOG_SCALE_SEL1 = 13      # Rotary switch bit 1

# =============================================================================
# Tool
# =============================================================================

MAX_TOOLS = 6                  # Quick change tool post positions
