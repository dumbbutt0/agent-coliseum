"""H6 fault matrix (directive item 14): a fault injector that counts and
interrupts the four durable-mutation primitives every council write funnels
through — os.rename, os.unlink, storage.append_line,
storage.atomic_write_json — so a test can simulate a process death or an
emergency STOP at ANY mutation boundary and then assert the council recovers
to a consistent state (no stranded lock, no half-move, no torn authority).

Two failure schedules:
  * fail_op(op, nth)   -> raise on the nth call of one primitive
  * fail_global(nth)   -> raise on the nth call across all primitives
Either way `.calls` records the ordered (op, path) trace, so a test can
first COUNT the boundaries a code path crosses (dry run, no failure), then
re-run failing at each one. The injected error is CrashInjected(OSError):
the code under test cannot tell it from a real disk/rename failure.
"""
from __future__ import annotations

import os
from contextlib import contextmanager

from tools.council import storage

OPS = ("rename", "unlink", "append_line", "atomic_write_json")


class CrashInjected(OSError):
    """Stand-in for a real OSError at a mutation boundary (simulated crash).
    Subclasses OSError so it flows through the same except paths a genuine
    filesystem failure would."""


class FaultInjector:
    def __init__(self):
        self.calls: list = []          # ordered (op, path) actually attempted
        self._per_op: dict = {}        # op -> 1-based index to fail
        self._global: int | None = None
        self._seen_op: dict = {op: 0 for op in OPS}
        self._seen_all = 0

    # ---- schedule --------------------------------------------------------
    def fail_op(self, op: str, nth: int) -> "FaultInjector":
        if op not in OPS:
            raise ValueError(f"unknown op {op!r}")
        self._per_op[op] = nth
        return self

    def fail_global(self, nth: int) -> "FaultInjector":
        self._global = nth
        return self

    # ---- accounting ------------------------------------------------------
    def count(self, op: str) -> int:
        return sum(1 for o, _ in self.calls if o == op)

    def total(self) -> int:
        return len(self.calls)

    def _tick(self, op: str, path: str) -> None:
        """Record the boundary and, if this call matches the schedule, raise
        BEFORE the real primitive runs (mid-op crash: the mutation never
        lands)."""
        self.calls.append((op, path))
        self._seen_op[op] += 1
        self._seen_all += 1
        if self._per_op.get(op) == self._seen_op[op]:
            raise CrashInjected(f"injected fault at {op} #{self._seen_op[op]}")
        if self._global is not None and self._seen_all == self._global:
            raise CrashInjected(f"injected fault at global #{self._seen_all}")


@contextmanager
def inject(injector: FaultInjector | None = None):
    """Patch the four primitives with counting wrappers for the duration of
    the block. With no schedule set it is a pure TRACER (records `.calls`,
    never raises) — use that to count the boundaries a code path crosses,
    then re-enter with a schedule that fails at one of them."""
    fi = injector or FaultInjector()
    real_rename, real_unlink = os.rename, os.unlink
    real_append, real_awj = storage.append_line, storage.atomic_write_json

    def w_rename(src, dst, *a, **k):
        fi._tick("rename", str(dst))
        return real_rename(src, dst, *a, **k)

    def w_unlink(path, *a, **k):
        fi._tick("unlink", str(path))
        return real_unlink(path, *a, **k)

    def w_append(path, line):
        fi._tick("append_line", str(path))
        return real_append(path, line)

    def w_awj(path, obj):
        fi._tick("atomic_write_json", str(path))
        return real_awj(path, obj)

    os.rename, os.unlink = w_rename, w_unlink
    storage.append_line, storage.atomic_write_json = w_append, w_awj
    try:
        yield fi
    finally:
        os.rename, os.unlink = real_rename, real_unlink
        storage.append_line, storage.atomic_write_json = real_append, real_awj


def count_boundaries(fn) -> list:
    """Dry-run fn() under a pure tracer and return its ordered (op, path)
    boundary trace — the failure points a fault-matrix row will iterate."""
    with inject() as fi:
        fn()
    return list(fi.calls)
