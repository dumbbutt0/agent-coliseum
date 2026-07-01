"""A Gladiator = identity + append-only memory + a policy (its 'body').

The default body is random (with a couple of hand-set styles so 'technique diversity' is visible in the
smoke test). Later:
  - the BODY becomes a trained RL policy (swap `act`),
  - the MIND becomes an LLM reading `memory` (rival ledger, outcomes) to reflect / negotiate / trash-talk.
`memory` is the append-only substrate for that mind — it already records who beat whom (the 'grudge' seed).
"""
from __future__ import annotations
import random
from dataclasses import dataclass, field


@dataclass
class Gladiator:
    id: str
    name: str
    seed: int = 0
    style: str = "random"                     # placeholder for LEARNED tendencies
    memory: list = field(default_factory=list)  # append-only fight memory (the mind's substrate)

    def __post_init__(self):
        self._rng = random.Random(self.seed)

    def act(self, obs, n_actions: int = 3) -> int:
        """Return an action index. Random body for now — replace with a trained policy in Phase 1."""
        if self.style == "aggressive":
            return self._rng.choices([0, 1, 2], weights=[6, 1, 3])[0]
        if self.style == "defensive":
            return self._rng.choices([0, 1, 2], weights=[1, 6, 3])[0]
        return self._rng.randrange(n_actions)

    def remember(self, entry: dict):
        """Append an outcome vs a specific rival — the raw material an LLM 'mind' will reflect over."""
        self.memory.append(entry)

    def record_vs(self, rival_id: str):
        """Convenience: win/loss/draw tally against one rival, read straight from memory."""
        from collections import Counter
        c = Counter(m["result"] for m in self.memory if m["rival"] == rival_id)
        return dict(c)
