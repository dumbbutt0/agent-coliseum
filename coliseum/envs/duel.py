"""A tiny, seedable duel env — the placeholder combat the RL policies will later plug into.

Interface mirrors a 2-agent turn-based game (`reset() -> obs`; `step(actions) -> obs, rewards, done, info`),
so replacing it with a PettingZoo combat env in Phase 1 doesn't touch the arena/logging code.

Actions: 0=attack 1=defend 2=feint. Resolution is a rock-paper-scissors-with-damage table, so
distinct action distributions = distinct 'techniques' and matchups are NON-TRANSITIVE (attack > feint >
defend > attack) — the same property that makes real self-play interesting.
"""
from __future__ import annotations
import random

ACTIONS = ["attack", "defend", "feint"]

# _DMG[mine][theirs] = damage I deal to my opponent this round.
_DMG = {
    "attack": {"attack": 2, "defend": 0, "feint": 3},
    "defend": {"attack": 1, "defend": 0, "feint": 0},
    "feint":  {"attack": 0, "defend": 2, "feint": 0},
}


class DuelEnv:
    def __init__(self, start_hp: int = 15, max_rounds: int = 50, seed: int | None = None):
        self.start_hp = start_hp
        self.max_rounds = max_rounds
        self.rng = random.Random(seed)   # available for stochastic dynamics later; resolution is deterministic
        self.hp = {0: start_hp, 1: start_hp}
        self.round = 0

    def reset(self, seed: int | None = None):
        if seed is not None:
            self.rng = random.Random(seed)
        self.hp = {0: self.start_hp, 1: self.start_hp}
        self.round = 0
        return self._obs()

    def _obs(self):
        # each agent sees (own_hp, opp_hp, round)
        return {0: (self.hp[0], self.hp[1], self.round),
                1: (self.hp[1], self.hp[0], self.round)}

    def step(self, actions: dict):
        a0, a1 = ACTIONS[actions[0]], ACTIONS[actions[1]]
        self.hp[1] -= _DMG[a0][a1]      # agent 0 hits agent 1
        self.hp[0] -= _DMG[a1][a0]      # agent 1 hits agent 0
        self.round += 1
        done = self.hp[0] <= 0 or self.hp[1] <= 0 or self.round >= self.max_rounds

        winner = None
        if done:
            if self.hp[0] <= 0 and self.hp[1] <= 0:
                winner = None                      # double KO -> draw
            elif self.hp[1] <= 0:
                winner = 0
            elif self.hp[0] <= 0:
                winner = 1
            elif self.hp[0] != self.hp[1]:
                winner = 0 if self.hp[0] > self.hp[1] else 1   # timeout -> higher HP wins
        rewards = {0: 0.0, 1: 0.0}
        if done and winner is not None:
            rewards = {winner: 1.0, 1 - winner: -1.0}
        return self._obs(), rewards, done, {"winner": winner, "actions": (a0, a1)}
