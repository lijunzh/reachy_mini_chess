"""HTTP API behind the digital board page.

The same routes run inside the Reachy Mini app (``main.py``) and on their own
with no robot: ``python -m reachy_mini_chess.web`` then open http://127.0.0.1:8042
"""

from __future__ import annotations

import argparse
from pathlib import Path

import chess
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .engine import MovePicker, make_analyzer
from .game import Game

STATIC_DIR = Path(__file__).parent / "static"


class NewGame(BaseModel):
    elo: int = 800
    robot_color: str = "black"


class Move(BaseModel):
    uci: str
    reply: bool = True  # the page sets False and asks for the robot's move separately


class Position(BaseModel):
    fen: str


class Elo(BaseModel):
    elo: int


def register_routes(api: FastAPI, game: Game) -> None:
    def guarded(action):
        try:
            return action()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    def state_with(rec=None, kind: str = "") -> dict:
        state = game.state()
        state["recommendation"] = {**rec.to_dict(), "kind": kind} if rec else None
        return state

    @api.get("/api/state")
    def get_state() -> dict:
        return state_with()

    @api.post("/api/new")
    def new_game(body: NewGame) -> dict:
        color = chess.WHITE if body.robot_color == "white" else chess.BLACK
        game.new_game(body.elo, color)
        return state_with()

    @api.post("/api/move")
    def kid_move(body: Move) -> dict:
        guarded(lambda: game.play_kid_move(body.uci, reply=body.reply))
        return state_with()

    @api.post("/api/robot-move")
    def robot_move() -> dict:
        guarded(game.play_robot_move)
        return state_with()

    @api.post("/api/position")
    def set_position(body: Position) -> dict:
        guarded(lambda: game.set_position(body.fen))
        return state_with()

    @api.post("/api/recommend")
    def recommend() -> dict:
        return state_with(guarded(game.recommend), "suggestion")

    @api.post("/api/hint")
    def hint() -> dict:
        return state_with(guarded(game.hint), "hint")

    @api.post("/api/take-back")
    def take_back() -> dict:
        guarded(game.take_back)
        return state_with()

    @api.post("/api/elo")
    def set_elo(body: Elo) -> dict:
        game.set_elo(body.elo)
        return state_with()


def create_standalone_app(game: Game) -> FastAPI:
    api = FastAPI()
    api.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @api.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    register_routes(api, game)
    return api


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="Digital chess board, no robot needed.")
    parser.add_argument("--elo", type=int, default=800)
    parser.add_argument("--port", type=int, default=8042)
    args = parser.parse_args()

    game = Game(MovePicker(make_analyzer()), elo=args.elo, min_think_s=1.0)
    print(f"Engine: {game.picker.analyzer.name}. Open http://127.0.0.1:{args.port}")
    try:
        uvicorn.run(create_standalone_app(game), host="127.0.0.1", port=args.port)
    finally:
        game.close()


if __name__ == "__main__":
    main()
