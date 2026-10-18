"""Reachy Mini Chess: the robot app.

Serves the digital board at http://localhost:8042 and makes the robot react to
the game. Start it from the Reachy Mini desktop app, or run this file directly
with the app's Python while the daemon (or simulator) is running.
"""

import queue
import threading

from reachy_mini import ReachyMini, ReachyMiniApp

from reachy_mini_chess.engine import MovePicker, make_analyzer
from reachy_mini_chess.game import Game
from reachy_mini_chess.robot import Gestures
from reachy_mini_chess.web import register_routes


class ReachyMiniChess(ReachyMiniApp):
    custom_app_url: str | None = "http://0.0.0.0:8042"
    # No camera or microphone yet. Part 1 (vision) will need the camera.
    request_media_backend: str | None = "no_media"

    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event):
        events: queue.Queue[tuple[str, dict]] = queue.Queue()
        game = Game(
            MovePicker(make_analyzer()),
            on_event=lambda name, data: events.put((name, data)),
            min_think_s=2.2,  # about as long as the robot's thinking gesture
        )
        register_routes(self.settings_app, game)
        self.logger.info(f"Chess engine: {game.picker.analyzer.name}")

        gestures = Gestures(reachy_mini)
        gestures.hello()
        try:
            while not stop_event.is_set():
                try:
                    name, data = events.get(timeout=0.05)
                except queue.Empty:
                    gestures.idle()
                    continue
                gestures.perform(name, data)
        finally:
            gestures.neutral()
            game.close()


if __name__ == "__main__":
    app = ReachyMiniChess()
    try:
        app.wrapped_run()
    except KeyboardInterrupt:
        app.stop()
