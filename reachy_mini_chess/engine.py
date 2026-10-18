"""Part 2 of the system: take a board, propose the next move at a target Elo.

Two analysers rank the candidate moves:

- ``StockfishAnalyzer`` when the ``stockfish`` binary is installed (best).
- ``SimpleAnalyzer``, a small pure-Python search, so the app still works on a
  machine without Stockfish.

``MovePicker`` then chooses among the ranked moves the way a player of the
target Elo might: usually a good move, sometimes a sloppy one, occasionally a
blunder. See ``levels.py`` for the dials.
"""

from __future__ import annotations

import math
import random
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import chess
import chess.engine

from .levels import MAX_ELO, Level, level_for
from .narration import move_to_words

MATE_CP = 100_000

_STOCKFISH_PATHS = [
    "/opt/homebrew/bin/stockfish",
    "/usr/local/bin/stockfish",
    "/usr/games/stockfish",
    "/usr/bin/stockfish",
]


@dataclass(frozen=True)
class Candidate:
    move: chess.Move
    score_cp: int  # from the point of view of the side to move


class Analyzer(Protocol):
    name: str

    def analyse(self, board: chess.Board, depth: int, multipv: int) -> list[Candidate]:
        """Return up to ``multipv`` moves, best first."""
        ...

    def close(self) -> None: ...


def find_stockfish() -> str | None:
    # Apps launched from the desktop app get a minimal PATH, so check the
    # usual install locations as well.
    found = shutil.which("stockfish")
    if found:
        return found
    return next((p for p in _STOCKFISH_PATHS if Path(p).exists()), None)


class StockfishAnalyzer:
    name = "stockfish"

    def __init__(self, path: str | None = None) -> None:
        path = path or find_stockfish()
        if path is None:
            raise FileNotFoundError("stockfish not found")
        self._engine = chess.engine.SimpleEngine.popen_uci(path)
        self._lock = threading.Lock()

    def analyse(self, board: chess.Board, depth: int, multipv: int) -> list[Candidate]:
        with self._lock:
            infos = self._engine.analyse(
                board, chess.engine.Limit(depth=depth), multipv=multipv
            )
        return [
            Candidate(info["pv"][0], info["score"].pov(board.turn).score(mate_score=MATE_CP))
            for info in infos
            if info.get("pv")
        ]

    def close(self) -> None:
        self._engine.quit()


_PIECE_CP = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}


class SimpleAnalyzer:
    """Material, centralisation and pawn advancement; alpha-beta plus captures.

    Roughly beginner-to-club strength. Depth is capped because pure Python is
    slow; the Elo dials still apply on top.
    """

    name = "simple"
    max_depth = 2

    def analyse(self, board: chess.Board, depth: int, multipv: int) -> list[Candidate]:
        depth = max(1, min(depth, self.max_depth))
        scored = []
        for move in board.legal_moves:
            board.push(move)
            score = -self._search(board, depth - 1, -MATE_CP, MATE_CP, 1)
            board.pop()
            scored.append(Candidate(move, score))
        scored.sort(key=lambda c: c.score_cp, reverse=True)
        return scored[:multipv]

    def close(self) -> None:
        pass

    def _search(self, board: chess.Board, depth: int, alpha: int, beta: int, ply: int) -> int:
        if board.is_checkmate():
            return -MATE_CP + ply
        if board.is_stalemate() or board.is_insufficient_material():
            return 0
        if depth <= 0:
            return self._quiesce(board, alpha, beta, 0)
        for move in self._ordered(board, board.legal_moves):
            board.push(move)
            score = -self._search(board, depth - 1, -beta, -alpha, ply + 1)
            board.pop()
            if score >= beta:
                return score
            alpha = max(alpha, score)
        return alpha

    def _quiesce(self, board: chess.Board, alpha: int, beta: int, qply: int) -> int:
        stand_pat = _evaluate(board)
        if stand_pat >= beta or qply >= 4:
            return stand_pat
        alpha = max(alpha, stand_pat)
        for move in self._ordered(board, board.generate_legal_captures()):
            board.push(move)
            score = -self._quiesce(board, -beta, -alpha, qply + 1)
            board.pop()
            if score >= beta:
                return score
            alpha = max(alpha, score)
        return alpha

    @staticmethod
    def _ordered(board: chess.Board, moves) -> list[chess.Move]:
        def victim(move: chess.Move) -> int:
            piece = board.piece_at(move.to_square)
            return _PIECE_CP[piece.piece_type] if piece else 0

        return sorted(moves, key=victim, reverse=True)


def _evaluate(board: chess.Board) -> int:
    """Static score from the side to move's point of view."""
    score = 0
    for square, piece in board.piece_map().items():
        value = _PIECE_CP[piece.piece_type]
        file, rank = chess.square_file(square), chess.square_rank(square)
        if piece.piece_type in (chess.KNIGHT, chess.BISHOP):
            distance = max(abs(file - 3.5), abs(rank - 3.5))
            value += int(10 * (3.5 - distance))
        elif piece.piece_type == chess.PAWN:
            value += 5 * (rank if piece.color == chess.WHITE else 7 - rank)
        score += value if piece.color == board.turn else -value
    return score


def make_analyzer() -> Analyzer:
    try:
        return StockfishAnalyzer()
    except FileNotFoundError:
        return SimpleAnalyzer()


@dataclass(frozen=True)
class Recommendation:
    move: chess.Move
    san: str
    words: str
    rank: int  # 1 = the analyser's top choice
    score_cp: int
    best_san: str
    best_score_cp: int
    blunder: bool
    level: Level
    analyzer: str
    candidates: list[tuple[str, int]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "uci": self.move.uci(),
            "san": self.san,
            "words": self.words,
            "rank": self.rank,
            "score_cp": self.score_cp,
            "best_san": self.best_san,
            "best_score_cp": self.best_score_cp,
            "blunder": self.blunder,
            "level": self.level.__dict__,
            "analyzer": self.analyzer,
            "candidates": [{"san": s, "score_cp": c} for s, c in self.candidates],
        }


class MovePicker:
    """Choose a move the way a player of a given Elo might."""

    def __init__(self, analyzer: Analyzer, rng: random.Random | None = None) -> None:
        self.analyzer = analyzer
        self.rng = rng or random.Random()

    def choose(self, board: chess.Board, elo: int) -> Recommendation:
        if board.is_game_over():
            raise ValueError("the game is over; there is no move to propose")
        level = level_for(elo)
        candidates = self.analyzer.analyse(board, level.depth, level.multipv)
        best = candidates[0]

        blunder = len(candidates) > 1 and self.rng.random() < level.blunder_rate
        if blunder:
            index = self.rng.randrange(1, len(candidates))
        else:
            # Softmax over how much worse each move is than the best one.
            weights = [
                math.exp(-(best.score_cp - c.score_cp) / level.temperature_cp)
                for c in candidates
            ]
            index = self.rng.choices(range(len(candidates)), weights=weights)[0]
        return self._recommendation(board, candidates, index, blunder, level)

    def best(self, board: chess.Board, depth: int = 12) -> Recommendation:
        """The strongest move we can find, for hints."""
        candidates = self.analyzer.analyse(board, depth, 1)
        full_strength = Level(MAX_ELO, depth, 1, temperature_cp=0.0, blunder_rate=0.0)
        return self._recommendation(board, candidates, 0, False, full_strength)

    def _recommendation(
        self,
        board: chess.Board,
        candidates: list[Candidate],
        index: int,
        blunder: bool,
        level: Level,
    ) -> Recommendation:
        chosen, best = candidates[index], candidates[0]
        return Recommendation(
            move=chosen.move,
            san=board.san(chosen.move),
            words=move_to_words(board, chosen.move),
            rank=index + 1,
            score_cp=chosen.score_cp,
            best_san=board.san(best.move),
            best_score_cp=best.score_cp,
            blunder=blunder,
            level=level,
            analyzer=self.analyzer.name,
            candidates=[(board.san(c.move), c.score_cp) for c in candidates],
        )
