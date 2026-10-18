"""Play two strength settings against each other to sanity-check the Elo dial.

    python -m reachy_mini_chess.ladder 800 1200 --games 20

The stronger setting should score well above half. A 400-point gap predicts
about 91% if the labels were real Elo. Our labels are design targets, so this
checks the order and rough spacing, not the absolute rating.
"""

from __future__ import annotations

import argparse
import random

import chess

from .engine import MovePicker, make_analyzer

MAX_PLIES = 300


def play(picker: MovePicker, white_elo: int, black_elo: int) -> chess.Board:
    board = chess.Board()
    while not board.is_game_over(claim_draw=True) and len(board.move_stack) < MAX_PLIES:
        elo = white_elo if board.turn == chess.WHITE else black_elo
        board.push(picker.choose(board, elo).move)
    return board


def expected_score(elo_a: int, elo_b: int) -> float:
    return 1 / (1 + 10 ** ((elo_b - elo_a) / 400))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("elo_a", type=int)
    parser.add_argument("elo_b", type=int)
    parser.add_argument("--games", type=int, default=20)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    picker = MovePicker(make_analyzer(), random.Random(args.seed))
    score_b = 0.0
    try:
        for i in range(args.games):
            b_is_white = i % 2 == 1
            white, black = (args.elo_b, args.elo_a) if b_is_white else (args.elo_a, args.elo_b)
            board = play(picker, white, black)
            outcome = board.outcome(claim_draw=True)
            if outcome is None or outcome.winner is None:
                points = 0.5
            else:
                points = 1.0 if (outcome.winner == chess.WHITE) == b_is_white else 0.0
            score_b += points
            print(f"game {i + 1:2d}: {white} (W) vs {black} (B)  {board.result(claim_draw=True):7s} "
                  f"{len(board.move_stack)} plies")
    finally:
        picker.analyzer.close()

    print(f"\n{args.elo_b} scored {score_b}/{args.games} = {score_b / args.games:.0%} against {args.elo_a}"
          f" (engine: {picker.analyzer.name}; real Elo gap would predict "
          f"{expected_score(args.elo_b, args.elo_a):.0%})")


if __name__ == "__main__":
    main()
