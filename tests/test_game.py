import random
from dataclasses import replace

import chess
import pytest
from fastapi.testclient import TestClient

from reachy_mini_chess.engine import MovePicker, SimpleAnalyzer
from reachy_mini_chess.game import Game, move_motion
from reachy_mini_chess.web import create_standalone_app


@pytest.fixture
def events():
    return []


@pytest.fixture
def game(events):
    return Game(
        MovePicker(SimpleAnalyzer(), random.Random(0)),
        elo=800,
        on_event=lambda name, data: events.append(name),
    )


def test_kid_move_gets_a_robot_reply(game, events):
    rec = game.play_kid_move("e2e4")
    assert rec is not None
    assert len(game.board.move_stack) == 2
    assert game.kid_to_move
    assert events == ["kid_moved", "thinking", "robot_moved"]
    assert game.state()["message"] == rec.words


def test_illegal_and_out_of_turn_moves_are_rejected(game):
    with pytest.raises(ValueError, match="illegal"):
        game.play_kid_move("e2e5")
    with pytest.raises(ValueError, match="not a move"):
        game.play_kid_move("hello")
    game.new_game(robot_color=chess.WHITE)
    with pytest.raises(ValueError, match="robot's turn"):
        game.play_kid_move("e7e5")


def test_take_back_returns_to_the_kids_turn(game):
    game.play_kid_move("e2e4")
    game.play_kid_move("d2d4")
    game.take_back()
    assert len(game.board.move_stack) == 2
    assert game.kid_to_move


def test_set_position_then_recommend(game):
    game.set_position("4k3/8/8/3q4/8/2N5/8/4K3 w - - 0 1")
    assert game.recommend().move in game.board.legal_moves
    assert game.hint().san == "Nxd5"
    with pytest.raises(ValueError):
        game.set_position("not a fen")
    with pytest.raises(ValueError, match="legal"):
        game.set_position("8/8/8/8/8/8/8/8 w - - 0 1")  # no kings


@pytest.mark.parametrize("uci, san", [("a7a8q", "a8=Q+"), ("a7a8r", "a8=R+"), ("a7a8b", "a8=B"), ("a7a8n", "a8=N")])
def test_kid_can_promote_to_any_piece(game, uci, san):
    client = TestClient(create_standalone_app(game))
    client.post("/api/position", json={"fen": "4k3/P7/8/8/8/8/8/4K3 w - - 0 1"})
    state = client.post("/api/move", json={"uci": uci}).json()
    assert state["history"][0] == san


def test_knight_promotion_into_a_draw_reads_cleanly(game):
    game.set_position("4k3/P7/8/8/8/8/8/4K3 w - - 0 1")
    assert game.play_kid_move("a7a8n") is None  # K+N vs K: insufficient material
    assert game.state()["message"] == (
        "Pawn to a8, and becomes a knight. It's a draw by insufficient material. Good game!"
    )


def test_kid_checkmate_ends_the_game(game, events):
    game.set_position("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1")
    assert game.play_kid_move("a1a8") is None
    state = game.state()
    assert state["game_over"] and state["result"] == "1-0"
    assert state["message"] == "Rook to a8. Checkmate! You beat me. Great game!"
    assert events[-1] == "game_over"


def test_web_api_round_trip(game):
    client = TestClient(create_standalone_app(game))
    assert client.get("/").status_code == 200
    state = client.post("/api/new", json={"elo": 1000, "robot_color": "black"}).json()
    assert state["elo"] == 1000 and state["kid_to_move"]

    state = client.post("/api/move", json={"uci": "d2d4"}).json()
    assert len(state["history"]) == 2 and state["last_robot_move"]["words"]

    assert client.post("/api/move", json={"uci": "d4d6"}).status_code == 400

    rec = client.post("/api/recommend").json()["recommendation"]
    assert rec["kind"] == "suggestion" and rec["uci"] in state["legal"]

    state = client.post("/api/new", json={"elo": 800, "robot_color": "white"}).json()
    assert state["history"] == [] and not state["kid_to_move"]  # the page asks the robot to open
    state = client.post("/api/robot-move").json()
    assert len(state["history"]) == 1 and state["kid_to_move"]


def test_page_flow_shows_kid_move_before_robot_reply(game, events):
    client = TestClient(create_standalone_app(game))
    state = client.post("/api/move", json={"uci": "e2e4", "reply": False}).json()
    assert state["history"] == ["e4"] and not state["kid_to_move"]
    assert state["last_move"] == {"uci": "e2e4", "slides": [["e2", "e4"]], "captured": None}
    assert "thinking" not in events

    state = client.post("/api/robot-move").json()
    assert len(state["history"]) == 2 and state["kid_to_move"]
    assert state["last_move"]["uci"] == state["last_robot_move"]["uci"]


def test_strong_kid_move_is_noticed_when_reply_is_asked_separately(game, events):
    game.play_kid_move("e2e4")
    # Pretend the robot thought it was winning big, so any kid reply looks strong.
    game.last = replace(game.last, score_cp=game.last.score_cp + 1000)
    game.play_kid_move("d2d4", reply=False)
    events.clear()
    game.play_robot_move()
    assert events[:2] == ["thinking", "kid_strong_move"]


@pytest.mark.parametrize(
    "fen, uci, slides, captured",
    [
        ("4k3/8/8/3q4/8/2N5/8/4K3 w - - 0 1", "c3d5", [["c3", "d5"]], "d5"),
        ("4k3/8/8/8/8/8/8/4K2R w K - 0 1", "e1g1", [["e1", "g1"], ["h1", "f1"]], None),
        ("r3k3/8/8/8/8/8/8/4K3 b q - 0 1", "e8c8", [["e8", "c8"], ["a8", "d8"]], None),
        ("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1", "e5d6", [["e5", "d6"]], "d5"),
    ],
)
def test_last_move_describes_what_to_animate(fen, uci, slides, captured):
    board = chess.Board(fen)
    assert move_motion(board, chess.Move.from_uci(uci)) == {
        "uci": uci, "slides": slides, "captured": captured,
    }


@pytest.mark.parametrize(
    "fen, uci, taken",
    [
        ("4k3/8/8/3q4/8/2N5/8/4K3 w - - 0 1", "c3d5", ["q"]),
        ("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1", "e5d6", ["p"]),  # en passant
    ],
)
def test_capture_trays_count_this_games_captures_only(game, fen, uci, taken):
    game.set_position(fen)  # a sparse position: missing pieces were never captured
    game.play_kid_move(uci, reply=False)
    state = game.state()
    assert state["captured_by_kid"] == taken
    assert state["captured_by_robot"] == []
