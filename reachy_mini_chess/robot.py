"""Reachy Mini's body language during a game.

Every gesture starts and ends at the neutral pose so they can be chained in any
order. Head pitch is positive when looking down; antennas are [right, left] in
radians, with right negative and left positive when they fold back.

Good first file for James to edit: change the angles, durations or order and
watch the simulator.
"""

from __future__ import annotations

import math
import time

import numpy as np
from reachy_mini import ReachyMini
from reachy_mini.utils import create_head_pose

NEUTRAL_HEAD = create_head_pose()
NEUTRAL_ANTENNAS = [-0.17, 0.17]


def _deg(right: float, left: float) -> list[float]:
    return [math.radians(right), math.radians(left)]


class Gestures:
    def __init__(self, mini: ReachyMini) -> None:
        self.mini = mini
        self.idle_since = time.monotonic()

    def perform(self, event: str, data: dict) -> None:
        action = {
            "new_game": self.hello,
            "thinking": self.think,
            "robot_moved": self.announce,
            "kid_strong_move": self.impressed,
            "game_over": lambda: self.game_over(data.get("winner")),
        }.get(event)
        if action is not None:
            action()
            self.idle_since = time.monotonic()

    def _go(self, duration: float, roll=0.0, pitch=0.0, yaw=0.0, z=0.0, antennas=None) -> None:
        head = create_head_pose(z=z, roll=roll, pitch=pitch, yaw=yaw, mm=True, degrees=True)
        self.mini.goto_target(head, antennas=antennas, duration=duration)

    def neutral(self, duration: float = 0.6) -> None:
        self.mini.goto_target(NEUTRAL_HEAD, antennas=NEUTRAL_ANTENNAS, duration=duration)

    def hello(self) -> None:
        """A wake-up nod with antennas up."""
        self._go(0.5, pitch=-10, antennas=_deg(0, 0))
        self._go(0.3, pitch=10)
        self._go(0.3, pitch=-5)
        self.neutral()

    def think(self) -> None:
        """Look down at the board and scan it."""
        self._go(0.6, pitch=22, z=-8, antennas=_deg(-35, 35))
        self._go(0.5, pitch=22, yaw=15, z=-8)
        self._go(0.6, pitch=22, yaw=-15, z=-8)
        self._go(0.4, pitch=22, z=-8)

    def announce(self) -> None:
        """Look up at the kid, perk up, and nod at the move."""
        self._go(0.5, pitch=-8, antennas=_deg(0, 0))
        self._go(0.25, pitch=6)
        self._go(0.25, pitch=-4)
        self.neutral(0.5)

    def impressed(self) -> None:
        """Tilt the head: "ooh, nice move"."""
        self._go(0.4, roll=15, antennas=_deg(20, -20))
        self._go(0.3, roll=15, antennas=_deg(-20, 20))
        self.neutral(0.5)

    def game_over(self, winner: str | None) -> None:
        if winner == "robot":
            for _ in range(3):  # little victory dance
                self._go(0.25, yaw=20, antennas=_deg(25, 25))
                self._go(0.25, yaw=-20, antennas=_deg(-25, -25))
        elif winner == "kid":
            # Droop, stay sad for a moment, then a sporting nod.
            self._go(1.2, pitch=25, z=-10, antennas=_deg(-150, 150))
            time.sleep(0.8)
            self._go(0.6, pitch=-5, antennas=_deg(0, 0))
        else:
            self._go(0.4, roll=12)  # shrug
            self._go(0.4, roll=-12)
        self.neutral()

    def idle(self) -> None:
        """Breathe gently while waiting for the kid to move."""
        t = time.monotonic() - self.idle_since
        breath = math.sin(2 * math.pi * 0.25 * t)
        sway = math.sin(2 * math.pi * 0.1 * t)
        head = create_head_pose(z=2 * breath, yaw=3 * sway, mm=True, degrees=True)
        antennas = np.array(NEUTRAL_ANTENNAS) + np.radians([-5 * breath, 5 * breath])
        self.mini.set_target(head=head, antennas=antennas)
