"""Append-only JSONL event log = the SOURCE OF TRUTH for every run.

Everything else (social graph, technique catalog, Elo, the live view) is DERIVED from these events and
regenerable. This is the `raw -> derived -> render` discipline: never let the pretty layer be the store.

Note on `t`: the wall-clock timestamp is metadata for humans/plots. Replay + derivation key on
(`seq`, `kind`, `data`) only, so a run is deterministic regardless of when it ran.
"""
from __future__ import annotations
import json
import os
import time
from dataclasses import dataclass, asdict


@dataclass
class Event:
    run_id: str
    seq: int
    kind: str      # "match_start" | "step" | "match_end" | "reflection" | ...
    t: float       # wall-clock metadata only (ignored on replay/derivation)
    data: dict


class RunLogger:
    """Append events to logs/<run_id>.jsonl, one JSON object per line."""

    def __init__(self, run_id: str, log_dir: str = "logs"):
        self.run_id = run_id
        os.makedirs(log_dir, exist_ok=True)
        self.path = os.path.join(log_dir, f"{run_id}.jsonl")
        self._seq = 0
        self._fh = open(self.path, "w", encoding="utf-8")  # fresh log per run (regenerable from seed)

    def log(self, kind: str, **data) -> Event:
        ev = Event(self.run_id, self._seq, kind, time.time(), data)
        self._fh.write(json.dumps(asdict(ev)) + "\n")
        self._fh.flush()
        self._seq += 1
        return ev

    def close(self):
        self._fh.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def read_events(path: str):
    """Yield events from a JSONL log — the only way anything reads a run."""
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)
