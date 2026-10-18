---
title: Reachy Mini Chess
emoji: ♟️
colorFrom: yellow
colorTo: blue
sdk: static
pinned: false
short_description: A chess buddy for kids that plays at the strength you pick
tags:
 - reachy_mini
 - reachy_mini_python_app
---

# Reachy Mini Chess

Reachy Mini plays chess with a kid at a chosen strength (say 800 Elo). Reachy
has no arms, so it thinks, calls its move, and the kid moves the pieces on a
real board.

Built by Lijun and James for the GenAI4Kidz Reachy Mini Winter Coding Challenge.

## The three parts

| Part | Job | Status |
|---|---|---|
| 1. See | Camera reads the physical board and turns it into a FEN | Not started. `POST /api/position` is where it will plug in |
| **2. Think** | **Take a board and propose a move at a target Elo** | **Prototype done** |
| 3. Talk | Say the move out loud and react to the kid | Body language done; voice not started |

## Run it

The Reachy Mini desktop app (or a real robot) must be running.

**From the desktop app:** this package is installed in the app's environment, so
it shows up as `reachy_mini_chess` in the app list. Press start, then open
<http://localhost:8042>.

**From a terminal**, with the desktop app's Python:

```bash
APP="$HOME/Library/Application Support/com.pollen-robotics.reachy-mini"
"$APP/apps_venv/bin/python" -m reachy_mini_chess.main
```

**Without a robot** (just the board, e.g. on a laptop):

```bash
"$APP/apps_venv/bin/python" -m reachy_mini_chess.web
```

Stockfish makes Reachy much better at judging moves (`brew install stockfish`).
Without it, the app falls back to a small built-in engine.

## How Reachy picks a move at a given Elo

1. Stockfish ranks the best few moves (`levels.py` says how many, and how deep it looks).
2. Reachy usually picks a good one, but the lower the Elo, the more often it
   picks a worse one on purpose (a softmax over how much each move loses).
3. Sometimes it blunders on purpose, more often at low Elo.

Open **Peek inside Reachy's brain** on the page to see the ranked moves and which
one it chose.

The Elo numbers are targets, not measured ratings. Check the order of the
levels with:

```bash
"$APP/apps_venv/bin/python" -m reachy_mini_chess.ladder 800 1200 --games 20
```

## Code map

| File | What it does |
|---|---|
| `levels.py` | Elo → depth, number of candidates, sloppiness, blunder rate |
| `engine.py` | Ranks moves (Stockfish or built-in) and picks one for the Elo |
| `game.py` | The digital board, turns, take-backs, game over |
| `narration.py` | "Knight takes bishop on f6, check!" |
| `robot.py` | Head and antenna gestures: think, announce, celebrate |
| `web.py` | HTTP API for the board page |
| `main.py` | The Reachy Mini app that ties it together |
| `static/` | The board page |

**James, start here:** `robot.py` (make Reachy dance differently) and
`narration.py` (change what Reachy says).

## Tests

```bash
"$APP/uv" pip install --python "$APP/apps_venv/bin/python" -e ".[dev]"
"$APP/apps_venv/bin/python" -m pytest
```
