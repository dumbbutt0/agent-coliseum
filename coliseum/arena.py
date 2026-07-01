"""The arena: run one match (logging every step) and a round-robin season (updating the ladder).

Every match emits structured events to the RunLogger — the source of truth everything derives from.
This module is body-agnostic: it calls `gladiator.act(obs)`, so random policies today and trained RL
policies tomorrow run through the exact same path.
"""
from __future__ import annotations
import itertools

from .envs.duel import DuelEnv, ACTIONS


def run_match(g0, g1, logger, seed: int, start_hp: int = 15, max_rounds: int = 50):
    """Run a single duel, log every step + the result, update both gladiators' memory. Returns winner id or None."""
    env = DuelEnv(start_hp=start_hp, max_rounds=max_rounds, seed=seed)
    obs = env.reset(seed=seed)
    logger.log("match_start", a=g0.id, b=g1.id, seed=seed)

    done, info = False, {"winner": None}
    while not done:
        acts = {0: g0.act(obs[0]), 1: g1.act(obs[1])}
        obs, rewards, done, info = env.step(acts)
        logger.log("step", a=g0.id, b=g1.id,
                   a_action=ACTIONS[acts[0]], b_action=ACTIONS[acts[1]],
                   a_hp=env.hp[0], b_hp=env.hp[1])

    winner = info["winner"]
    win_id = None if winner is None else (g0.id if winner == 0 else g1.id)
    logger.log("match_end", a=g0.id, b=g1.id, winner=win_id, a_hp=env.hp[0], b_hp=env.hp[1])

    # each gladiator remembers the outcome vs THIS specific rival (the grudge/alliance substrate)
    g0.remember({"rival": g1.id, "result": _result_for(win_id, g0.id, win_id is None)})
    g1.remember({"rival": g0.id, "result": _result_for(win_id, g1.id, win_id is None)})
    return win_id


def _result_for(win_id, me, draw):
    if draw:
        return "draw"
    return "win" if win_id == me else "loss"


def round_robin(roster, logger, ladder, base_seed: int = 0):
    """Every pairing fights once; the ladder absorbs each result."""
    for i, (g0, g1) in enumerate(itertools.combinations(roster, 2)):
        win_id = run_match(g0, g1, logger, seed=base_seed + i)
        score0 = 0.5 if win_id is None else (1.0 if win_id == g0.id else 0.0)
        ladder.record(g0.id, g1.id, score0)
