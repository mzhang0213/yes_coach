"""Template data source — a background producer on its own thread.

Subclass PollingDataSource for interval-polled signals (an HTTP API, screen
frames, a log tail read on a timer). For push/event-driven games, implement the
DataSource Protocol (start/stop) directly instead.
"""

from server.core.datasource import PollingDataSource


class TemplateSource(PollingDataSource):
    def __init__(self, session, store=None, coach=None, interval: float = 1.5):
        super().__init__(name="Template source", interval=interval)
        self.session = session
        self.store = store
        self.coach = coach

    def _poll_once(self):
        # 1) Fetch a raw frame. Pick your signal type:
        #      HTTP API:    raw = requests.get(...).json()
        #      vision-only: from server.utils import SCREEN_CAP; raw = SCREEN_CAP.last_frame
        #      log/event:   raw = read_next_line(...)
        raw = {}
        self.session.game.latest = raw
        self.session.model.in_game = True
        # 2) (optional) persist / trend / checkpoint → advise, e.g.:
        #      state = self.session.game.compressed_state()
        #      if self.coach:
        #          self.session.ui.pending_suggestion = {
        #              "title": "tip",
        #              "advice": self.coach.get_advice(schema_key="situation", state=state)}

    def _on_error(self, e):
        # Degrade when the signal is unavailable (game not running).
        self.session.model.in_game = False
