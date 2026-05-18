"""Transitions module — Retract/approach/link logic between passes.

NOTE: This module does NOT import from geometry/.
ZoneQueryAPI is received as a parameter from pipeline/ (dependency injection).
This maintains the strict dependency chain: transitions/ imports only models/ and intervals/.

Imports from: models/, intervals/
"""

from transitions.transition_planner import TransitionPlanner
