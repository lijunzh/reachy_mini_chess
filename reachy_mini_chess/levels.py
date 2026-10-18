"""Turn a target Elo into the knobs that make the engine play like that player.

A strong engine does not get weaker by thinking less hard; it gets weaker by
choosing differently. Each level sets four dials:

- depth: how far ahead it looks (short sight misses tactics)
- multipv: how many candidate moves it considers
- temperature_cp: how willing it is to play a worse move (bigger = sloppier)
- blunder_rate: how often it ignores its own analysis entirely

The Elo labels are design targets, not measured ratings. Use
``python -m reachy_mini_chess.ladder`` to check the dial is in the right order.
"""

from __future__ import annotations

from dataclasses import dataclass

MIN_ELO = 400
MAX_ELO = 2400

# elo, depth, multipv, temperature_cp, blunder_rate
_ANCHORS = [
    (400, 1, 12, 300.0, 0.20),
    (800, 3, 10, 150.0, 0.08),
    (1200, 6, 8, 70.0, 0.03),
    (1600, 9, 6, 35.0, 0.01),
    (2000, 12, 4, 15.0, 0.0),
    (2400, 16, 3, 5.0, 0.0),
]


@dataclass(frozen=True)
class Level:
    elo: int
    depth: int
    multipv: int
    temperature_cp: float
    blunder_rate: float


def level_for(elo: int) -> Level:
    """Interpolate the dials for any Elo between MIN_ELO and MAX_ELO."""
    elo = max(MIN_ELO, min(MAX_ELO, int(elo)))
    for lo, hi in zip(_ANCHORS, _ANCHORS[1:]):
        if lo[0] <= elo <= hi[0]:
            f = (elo - lo[0]) / (hi[0] - lo[0])
            mix = [a + f * (b - a) for a, b in zip(lo[1:], hi[1:])]
            return Level(
                elo=elo,
                depth=max(1, round(mix[0])),
                multipv=max(1, round(mix[1])),
                temperature_cp=mix[2],
                blunder_rate=mix[3],
            )
    raise AssertionError("unreachable: elo is clamped to the anchor range")
