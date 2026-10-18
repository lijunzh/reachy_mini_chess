"""One game between the kid and the robot: the digital board and whose turn it is.

The game knows nothing about the robot body or the web page. It reports what
happened through ``on_event(name, data)`` so the robot can react, and it stays
fully playable with no robot attached.

Events: ``new_game``, ``thinking``, ``robot_moved``, ``kid_moved``, ``game_over``.
"""

from __future__ import annotations

import threading
import time
from typing import Callable

import chess

from .engine import MovePicker, Recommendation
from .levels import level_for
from .narration import move_to_words, result_words

EventHandler = Callable[[str, dict], None]

# A kid move that swings the robot's evaluation by this much is worth noticing.
STRONG_MOVE_CP = 150


class Game:
    def __init__(
        self,
        picker: MovePicker,
        elo: int = 800,
        robot_color: chess.Color = chess.BLACK,
        on_event: EventHandler | None = None,
        min_think_s: float = 0.0,
    ) -> None:
        self.picker = picker
        self.on_event = on_event or (lambda name, data: None)
        self.min_think_s = min_think_s
        self.lock = threading.RLock()
        self.board = chess.Board()
        self.elo = level_for(elo).elo
        self.robot_color = robot_color
        self.last: Recommendation | None = None
        self.expected_cp: int | None = None
        self.message = "Ready when you are!"

    # --- setup -------------------------------------------------------------

    def new_game(self, elo: int | None = None, robot_color: chess.Color | None = None) -> None:
        with self.lock:
            if elo is not None:
                self.elo = level_for(elo).elo
            if robot_color is not None:
                self.robot_color = robot_color
            self.board.reset()
            self.last = None
            self.expected_cp = None
            self.message = "New game. Your move!" if self.kid_to_move else "New game. My move first."
            self.on_event("new_game", {"elo": self.elo})

    def set_elo(self, elo: int) -> None:
        with self.lock:
            self.elo = level_for(elo).elo

    def set_position(self, fen: str) -> None:
        """Load a board from FEN. This is where part 1 (camera) will plug in."""
        with self.lock:
            board = chess.Board(fen)  # raises ValueError on malformed FEN
            if not board.is_valid():
                raise ValueError(f"not a legal chess position: {board.status()!r}")
            self.board = board
            self.last = None
            self.expected_cp = None
            self.message = "Position loaded."

    # --- turns -------------------------------------------------------------

    @property
    def kid_to_move(self) -> bool:
        return self.board.turn != self.robot_color

    def play_kid_move(self, uci: str, reply: bool = True) -> Recommendation | None:
        """Apply the kid's move. With ``reply``, the robot answers straight away.

        The board page passes ``reply=False`` so it can show the kid's move
        first, then ask for the robot's move separately.
        """
        with self.lock:
            if self.board.is_game_over(claim_draw=True):
                raise ValueError("the game is over")
            if not self.kid_to_move:
                raise ValueError("it is the robot's turn")
            move = self._parse(uci)
            words = move_to_words(self.board, move)
            self.expected_cp = self.last.score_cp if self.last else None
            self.board.push(move)
            self.message = "Hmm, let me think..."
            self.on_event("kid_moved", {"uci": uci, "words": words})
            if self._finish_if_over(words):
                return None
            return self.play_robot_move() if reply else None

    def play_robot_move(self) -> Recommendation:
        """Robot chooses a move at the preset Elo and plays it on the digital board."""
        with self.lock:
            if self.board.is_game_over(claim_draw=True):
                raise ValueError("the game is over")
            self.on_event("thinking", {})
            started = time.monotonic()
            rec = self.picker.choose(self.board, self.elo)
            # The robot's evaluation after its previous move. If the kid's reply
            # made things much worse for the robot, that was a strong move.
            expected, self.expected_cp = self.expected_cp, None
            if expected is not None and rec.best_score_cp < expected - STRONG_MOVE_CP:
                self.on_event("kid_strong_move", {"swing_cp": expected - rec.best_score_cp})
            # Let the robot finish looking like it is thinking.
            time.sleep(max(0.0, self.min_think_s - (time.monotonic() - started)))
            self.board.push(rec.move)
            self.last = rec
            self.message = rec.words
            self.on_event("robot_moved", rec.to_dict())
            self._finish_if_over(rec.words)
            return rec

    def recommend(self) -> Recommendation:
        """Propose a move for whoever is to move, at the preset Elo. Does not play it."""
        with self.lock:
            return self.picker.choose(self.board, self.elo)

    def hint(self) -> Recommendation:
        """The strongest move for whoever is to move."""
        with self.lock:
            if self.board.is_game_over(claim_draw=True):
                raise ValueError("the game is over")
            return self.picker.best(self.board)

    def take_back(self) -> None:
        """Undo back to the kid's previous turn."""
        with self.lock:
            if not self.board.move_stack:
                raise ValueError("nothing to take back")
            self.board.pop()
            while self.board.move_stack and not self.kid_to_move:
                self.board.pop()
            self.last = None
            self.expected_cp = None
            self.message = "Okay, take two."

    # --- reporting ---------------------------------------------------------

    def state(self) -> dict:
        with self.lock:
            board = self.board
            replay = board.root()  # the loaded position, not necessarily the usual start
            history, last_move = [], None
            took = {chess.WHITE: [], chess.BLACK: []}  # pieces each side captured this game
            for move in board.move_stack:
                history.append(replay.san(move))
                last_move = move_motion(replay, move)
                if last_move["captured"]:
                    victim = replay.piece_at(chess.parse_square(last_move["captured"]))
                    took[replay.turn].append(victim.symbol().lower())
                replay.push(move)
            outcome = board.outcome(claim_draw=True)
            return {
                "fen": board.fen(),
                "turn": "white" if board.turn == chess.WHITE else "black",
                "robot_color": "white" if self.robot_color == chess.WHITE else "black",
                "kid_to_move": self.kid_to_move,
                "elo": self.elo,
                "legal": [m.uci() for m in board.legal_moves] if outcome is None else [],
                "history": history,
                "in_check": board.is_check(),
                "game_over": outcome is not None,
                "result": outcome.result() if outcome else None,
                "message": self.message,
                "last_move": last_move,
                "captured_by_robot": took[self.robot_color],
                "captured_by_kid": took[not self.robot_color],
                "last_robot_move": self.last.to_dict() if self.last else None,
                "analyzer": self.picker.analyzer.name,
            }

    def close(self) -> None:
        self.picker.analyzer.close()

    # --- helpers -----------------------------------------------------------

    def _parse(self, uci: str) -> chess.Move:
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            raise ValueError(f"not a move: {uci!r}") from None
        if move not in self.board.legal_moves:
            raise ValueError(f"illegal move: {uci}")
        return move

    def _finish_if_over(self, last_move_words: str) -> bool:
        words = result_words(self.board, self.robot_color)
        if words is None:
            return False
        outcome = self.board.outcome(claim_draw=True)
        winner = None if outcome.winner is None else (
            "robot" if outcome.winner == self.robot_color else "kid"
        )
        stop = "" if last_move_words.endswith(("!", ".")) else "."
        self.message = f"{last_move_words}{stop} {words}"
        self.on_event("game_over", {"winner": winner, "words": words})
        return True


def move_motion(board: chess.Board, move: chess.Move) -> dict:
    """What the page should animate for ``move``, which is legal in ``board``.

    ``slides`` lists every piece that travels (two when castling); ``captured`` is
    the square whose piece is taken, which is not the arrival square en passant.
    """
    slides = [(move.from_square, move.to_square)]
    captured = None
    if board.is_castling(move):
        rank = chess.square_rank(move.from_square)
        if board.is_kingside_castling(move):
            slides.append((chess.square(7, rank), chess.square(5, rank)))
        else:
            slides.append((chess.square(0, rank), chess.square(3, rank)))
    elif board.is_en_passant(move):
        captured = chess.square(chess.square_file(move.to_square), chess.square_rank(move.from_square))
    elif board.is_capture(move):
        captured = move.to_square
    return {
        "uci": move.uci(),
        "slides": [[chess.square_name(a), chess.square_name(b)] for a, b in slides],
        "captured": chess.square_name(captured) if captured is not None else None,
    }
