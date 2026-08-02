"""Data-source seam — the generic background-producer contract.

A DataSource runs OFF the 60fps render tick on its own daemon thread (the
pattern proven by the two LOL pollers and ScreenCapture) so a slow/blocking
fetch can never stall rendering. It writes state where the tick loop can read
it; the tick loop never touches the network.

`PollingDataSource` extracts the byte-for-byte-identical lifecycle the two LOL
pollers shared (start/stop/_loop + interval sleep + try/except). Their only
real differences — how they degrade on error and whether stop() closes an open
game — are the `_on_error`/`_on_stop` hooks.

Games whose signal is push/event-driven (not interval-polled) implement the
`DataSource` Protocol directly instead of subclassing `PollingDataSource`.
"""

import threading
import time
from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable


@runtime_checkable
class DataSource(Protocol):
    name: str

    def start(self) -> bool: ...
    def stop(self) -> None: ...


class PollingDataSource(ABC):
    """Interval-driven daemon-thread producer. Subclasses implement `_poll_once`."""

    def __init__(self, name: str, interval: float = 1.5):
        self.name = name
        self.interval = interval
        self.running = False
        self._thread = None

    # ── lifecycle ───────────────────────────────────────────────────────────

    def start(self) -> bool:
        if self.running:
            return False
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print(f"{self.name} started.")
        return True

    def stop(self) -> None:
        self.running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._on_stop()
        print(f"{self.name} stopped.")

    # ── loop ────────────────────────────────────────────────────────────────

    def _loop(self) -> None:
        while self.running:
            try:
                self._poll_once()
            except Exception as e:
                self._on_error(e)
            time.sleep(self.interval)

    @abstractmethod
    def _poll_once(self) -> None:
        ...

    # ── hooks (override to degrade / clean up) ───────────────────────────────

    def _on_error(self, e: Exception) -> None:
        """Handle a poll failure. Default: log and keep polling."""
        print(f"{self.name} error: {e}")

    def _on_stop(self) -> None:
        """Called after the thread joins in stop(). Default: nothing."""
        pass
