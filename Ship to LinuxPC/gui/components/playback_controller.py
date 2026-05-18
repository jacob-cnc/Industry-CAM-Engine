"""Playback controller for Industry CAM Engine.

QTimer-based frame stepper for toolpath animation.
Advances through PlaybackFrames at configurable speed.
"""

from pyqtgraph.Qt import QtCore
from typing import List

from outputs.graph_adapter import PlaybackFrame


class PlaybackController(QtCore.QObject):
    """QTimer-based frame stepper for toolpath animation.

    Signals:
        frame_changed(int, float, float, str, int): index, x_radius, z, pass_type, n_number
        playback_finished(): Emitted when last frame is reached
    """

    frame_changed = QtCore.pyqtSignal(int, float, float, str, int)
    playback_finished = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._frames: List[PlaybackFrame] = []
        self._current_index: int = 0
        self._speed: float = 1.0
        self._base_interval_ms: int = 100  # 10 fps at 1x (slower for readability)

    @property
    def is_playing(self) -> bool:
        return self._timer.isActive()

    @property
    def current_index(self) -> int:
        return self._current_index

    @property
    def frame_count(self) -> int:
        return len(self._frames)

    def load_frames(self, frames: List[PlaybackFrame]) -> None:
        """Load playback data from GraphData."""
        self._frames = frames
        self._current_index = 0

    def play(self) -> None:
        """Start or resume playback."""
        if not self._frames:
            return
        interval = int(self._base_interval_ms / self._speed)
        self._timer.start(max(10, interval))

    def pause(self) -> None:
        """Pause playback (preserves position)."""
        self._timer.stop()

    def stop(self) -> None:
        """Stop playback and reset to beginning."""
        self._timer.stop()
        self._current_index = 0

    def step_forward(self) -> None:
        """Advance one frame."""
        if self._current_index < len(self._frames) - 1:
            self._current_index += 1
            self._emit_current_frame()

    def step_backward(self) -> None:
        """Go back one frame."""
        if self._current_index > 0:
            self._current_index -= 1
            self._emit_current_frame()

    def set_speed(self, multiplier: float) -> None:
        """Set playback speed (0.5, 1.0, 2.0, 5.0)."""
        self._speed = max(0.1, min(10.0, multiplier))
        if self._timer.isActive():
            interval = int(self._base_interval_ms / self._speed)
            self._timer.setInterval(max(10, interval))

    def _advance(self) -> None:
        """Timer callback — emit next frame."""
        if self._current_index >= len(self._frames) - 1:
            self._timer.stop()
            self.playback_finished.emit()
            return

        self._current_index += 1
        self._emit_current_frame()

    def _emit_current_frame(self) -> None:
        """Emit the current frame's data."""
        if 0 <= self._current_index < len(self._frames):
            frame = self._frames[self._current_index]
            self.frame_changed.emit(
                frame.move_index,
                frame.x,
                frame.z,
                frame.pass_type.value,
                frame.n_number,
            )
