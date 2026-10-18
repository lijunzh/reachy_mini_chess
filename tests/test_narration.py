import chess
import pytest

from reachy_mini_chess.narration import move_to_words, result_words


def words(fen: str, san: str) -> str:
    board = chess.Board(fen)
    return move_to_words(board, board.parse_san(san))


START = chess.STARTING_FEN


@pytest.mark.parametrize(
    "fen, san, expected",
    [
        (START, "e4", "Pawn to e4"),
        (START, "Nf3", "Knight to f3"),
        ("rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2", "exd5", "Pawn takes pawn on d5"),
        ("r1bqkbnr/pppp1ppp/2n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 4", "Bxc6", "Bishop takes knight on c6"),
        ("r1bqkbnr/pppp1ppp/2n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 4", "O-O", "Castle kingside"),
        ("4k3/8/8/8/8/8/8/R3K2R w KQ - 0 1", "O-O-O", "Castle queenside"),
        ("4k3/P7/8/8/8/8/8/4K3 w - - 0 1", "a8=Q+", "Pawn to a8, and becomes a queen, check!"),
        ("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1", "exd6", "Pawn takes pawn on d6, en passant"),
        ("4k3/8/8/8/8/8/4K3/R6R w - - 0 1", "Rad1", "Rook from a1 to d1"),
        ("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1", "Ra8#", "Rook to a8. Checkmate!"),
    ],
)
def test_move_to_words(fen, san, expected):
    assert words(fen, san) == expected


def test_move_to_words_leaves_board_unchanged():
    board = chess.Board()
    move_to_words(board, chess.Move.from_uci("e2e4"))
    assert board.fen() == chess.STARTING_FEN


def test_result_words():
    mated_black = chess.Board("R5k1/5ppp/8/8/8/8/5PPP/6K1 b - - 0 1")
    assert result_words(mated_black, robot_color=chess.WHITE).startswith("I win")
    assert result_words(mated_black, robot_color=chess.BLACK).startswith("You beat me")
    assert result_words(chess.Board(), chess.BLACK) is None
    stalemate = chess.Board("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
    assert "draw by stalemate" in result_words(stalemate, chess.BLACK)
