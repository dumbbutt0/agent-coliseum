"""Elo ladder — a simple, dependency-free skill rating so a 'career' is measurable.

TrueSkill is the upgrade for >2 players / teams; Elo is enough to start. This gives you the maturity
curve and the ranking you can watch a gladiator climb.
"""
from __future__ import annotations


def expected(ra: float, rb: float) -> float:
    """Probability a beats b given ratings."""
    return 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))


def update(ra: float, rb: float, score_a: float, k: float = 32.0):
    """score_a: 1.0 win, 0.0 loss, 0.5 draw. Returns (new_ra, new_rb)."""
    ea = expected(ra, rb)
    ra2 = ra + k * (score_a - ea)
    rb2 = rb + k * ((1.0 - score_a) - (1.0 - ea))
    return ra2, rb2


class Ladder:
    def __init__(self, base: float = 1000.0, k: float = 32.0):
        self.base, self.k = base, k
        self.r: dict[str, float] = {}

    def rating(self, gid: str) -> float:
        return self.r.setdefault(gid, self.base)

    def record(self, a: str, b: str, score_a: float):
        ra, rb = self.rating(a), self.rating(b)
        self.r[a], self.r[b] = update(ra, rb, score_a, self.k)

    def table(self):
        """(gid, rating) sorted best-first."""
        return sorted(self.r.items(), key=lambda kv: -kv[1])
