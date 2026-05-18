"""Backend factory — selects Live or Mock based on environment.

Import this module to get the appropriate backend without caring
which platform you're on.

Usage:
    from hal.factory import get_backend
    backend = get_backend()
"""

import logging
from hal.interface import HALBackend

logger = logging.getLogger(__name__)

_backend_instance: HALBackend | None = None


def get_backend(force_mock: bool = False) -> HALBackend:
    """Get or create the singleton HAL backend.

    Tries to import linuxcnc. If available and connected, returns LiveBackend.
    Otherwise falls back to MockBackend for offline development.

    Args:
        force_mock: If True, always use MockBackend (for testing).

    Returns:
        HALBackend instance (singleton — same instance on repeated calls).
    """
    global _backend_instance

    if _backend_instance is not None:
        return _backend_instance

    if force_mock:
        logger.info("HAL: Using MockBackend (forced)")
        from hal.mock_backend import MockBackend
        _backend_instance = MockBackend()
        return _backend_instance

    try:
        import linuxcnc  # noqa: F401
        from hal.live_backend import LiveBackend
        backend = LiveBackend()
        if backend.connected:
            logger.info("HAL: Connected to LinuxCNC (LiveBackend)")
            _backend_instance = backend
            return _backend_instance
        else:
            logger.warning("HAL: linuxcnc module found but not connected, falling back to MockBackend")
    except ImportError:
        logger.info("HAL: linuxcnc module not available (Windows?), using MockBackend")
    except Exception as e:
        logger.warning("HAL: Failed to connect to LinuxCNC (%s), using MockBackend", e)

    from hal.mock_backend import MockBackend
    _backend_instance = MockBackend()
    return _backend_instance


def reset_backend() -> None:
    """Reset the singleton (for testing only)."""
    global _backend_instance
    _backend_instance = None
