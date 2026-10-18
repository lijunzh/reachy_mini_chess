import random
from collections import Counter

import chess
import pytest

from reachy_mini_chess.engine import (
    MovePicker,
    SimpleAnalyzer,
    StockfishAnalyzer,
    find_stockfish,
)
from reachy_mini_chess.levels import MAX_ELO, MIN_ELO, level_for

MATE_IN_ONE = "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1"  # Ra8#

analyzers = [SimpleAnalyzer]
if find_stockfish():
    analyzers.append(StockfishAnalyzer)


@pytest.fixture(params=analyzers, ids=lambda cls: cls.name)
def analyzer(request):
    a = request.param()
    yield a
    a.close()


def test_levels_get_stronger_with_elo():
    levels = [level_for(e) for e in range(MIN_ELO, MAX_ELO + 1, 100)]
    for weaker, stronger in zip(levels, levels[1:]):
        assert stronger.depth >= weaker.depth
        assert stronger.temperature_cp <= weaker.temperature_cp
        assert stronger.blunder_rate <= weaker.blunder_rate


def test_levels_clamp_out_of_range():
    assert level_for(0).elo == MIN_ELO
    assert level_for(9999).elo == MAX_ELO


def test_strong_level_finds_mate_in_one(analyzer):
    picker = MovePicker(analyzer, random.Random(0))
    rec = picker.choose(chess.Board(MATE_IN_ONE), elo=2400)
    assert rec.san == "Ra8#"
    assert rec.words == "Rook to a8. Checkmate!"


def test_takes_a_free_queen(analyzer):
    board = chess.Board("4k3/8/8/3q4/8/2N5/8/4K3 w - - 0 1")  # Nxd5 wins the queen
    rec = MovePicker(analyzer, random.Random(0)).choose(board, elo=1600)
    assert rec.san == "Nxd5"


def test_always_proposes_a_legal_move(analyzer):
    picker = MovePicker(analyzer, random.Random(3))
    board = chess.Board()
    for _ in range(20):
        if board.is_game_over():
            break
        rec = picker.choose(board, elo=800)
        assert rec.move in board.legal_moves
        assert 1 <= rec.rank <= len(rec.candidates)
        board.push(rec.move)


def test_low_elo_plays_varied_moves_high_elo_plays_the_top_move():
    if not find_stockfish():
        pytest.skip("needs stockfish for stable rankings")
    board = chess.Board()
    analyzer = StockfishAnalyzer()
    try:
        picker = MovePicker(analyzer, random.Random(7))
        low = Counter(picker.choose(board, 400).rank for _ in range(40))
        high = Counter(picker.choose(board, 2400).rank for _ in range(40))
    finally:
        analyzer.close()
    assert len(low) >= 4  # spreads its choices around
    assert high[1] >= 25  # mostly the engine's first choice


def test_no_move_when_game_over():
    board = chess.Board("R5k1/5ppp/8/8/8/8/5PPP/6K1 b - - 0 1")  # black is mated
    with pytest.raises(ValueError):
        MovePicker(SimpleAnalyzer()).choose(board, 800)
