"""Say a chess move the way you would say it to a kid across the board.

"Knight to f6", "Bishop takes knight on c6", "Castle kingside, check!"
Part 3 (voice) will speak these lines; for now the web page shows them.
"""

from __future__ import annotations

import chess

PIECE_NAMES = {
    chess.PAWN: "pawn",
    chess.KNIGHT: "knight",
    chess.BISHOP: "bishop",
    chess.ROOK: "rook",
    chess.QUEEN: "queen",
    chess.KING: "king",
}


def move_to_words(board: chess.Board, move: chess.Move) -> str:
    """Describe ``move``, which must be legal in ``board``, in plain English."""
    piece = board.piece_at(move.from_square)
    if piece is None:
        raise ValueError(f"no piece on {chess.square_name(move.from_square)}")
    name = PIECE_NAMES[piece.piece_type]
    to = chess.square_name(move.to_square)

    if board.is_castling(move):
        text = "Castle kingside" if board.is_kingside_castling(move) else "Castle queenside"
    else:
        mover = name.capitalize()
        if _is_ambiguous(board, move):
            mover += f" from {chess.square_name(move.from_square)}"
        if board.is_en_passant(move):
            text = f"{mover} takes pawn on {to}, en passant"
        elif board.is_capture(move):
            victim = board.piece_at(move.to_square)
            text = f"{mover} takes {PIECE_NAMES[victim.piece_type]} on {to}"
        else:
            text = f"{mover} to {to}"
        if move.promotion:
            text += f", and becomes a {PIECE_NAMES[move.promotion]}"

    board.push(move)
    try:
        if board.is_checkmate():
            text += ". Checkmate!"
        elif board.is_check():
            text += ", check!"
    finally:
        board.pop()
    return text


def _is_ambiguous(board: chess.Board, move: chess.Move) -> bool:
    """True when another piece of the same kind could also reach the square."""
    piece_type = board.piece_type_at(move.from_square)
    if piece_type == chess.PAWN:
        return False
    return any(
        other.to_square == move.to_square
        and other.from_square != move.from_square
        and board.piece_type_at(other.from_square) == piece_type
        for other in board.legal_moves
    )


def result_words(board: chess.Board, robot_color: chess.Color) -> str | None:
    """What the robot says when the game ends, or None while it is still on."""
    outcome = board.outcome(claim_draw=True)
    if outcome is None:
        return None
    if outcome.winner is None:
        reason = outcome.termination.name.replace("_", " ").lower()
        return f"It's a draw by {reason}. Good game!"
    if outcome.winner == robot_color:
        return "I win this one. Want a rematch?"
    return "You beat me. Great game!"
