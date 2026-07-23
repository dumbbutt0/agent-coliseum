"""The killable child (audit blocker 2): executes exactly ONE driver and
writes its outcome to --result-file as JSON. The parent runner owns every
limit — it kills this process on wall/compute deadline or storage overrun —
so nothing here may spawn further work or write outside the driver's
documented outputs. This child never touches the council.

    python3 -m tools.autonomy.child_runner --repo R --config C --driver D \
        --deadline-seconds N --result-file F
"""
from __future__ import annotations

import argparse
import json
import sys
import time


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="child_runner")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--driver", required=True)
    parser.add_argument("--deadline-seconds", type=float, required=True)
    parser.add_argument("--result-file", required=True)
    parser.add_argument("--execution-context-file", default=None)
    args = parser.parse_args(argv)

    from tools.autonomy.drivers import DRIVERS
    driver = DRIVERS.get(args.driver)
    if driver is None:
        result = {"ok": False, "error": f"no driver {args.driver!r}"}
    else:
        try:
            from tools.council.strictjson import loads_strict
            with open(args.config, "rb") as fh:
                config = loads_strict(fh.read(), max_bytes=1_048_576)
            execution_context = None
            if args.execution_context_file:
                with open(args.execution_context_file, "rb") as fh:
                    execution_context = loads_strict(
                        fh.read(), max_bytes=1_048_576)
            deadline = time.monotonic() + args.deadline_seconds
            outcome = driver(args.repo, config, deadline,
                             execution_context=execution_context)
            result = {"ok": True, "outcome": outcome}
        except Exception as exc:  # the parent decides what a failure means
            result = {"ok": False,
                      "error": f"{exc.__class__.__name__}: {exc}"}
    with open(args.result_file, "w", encoding="utf-8") as fh:
        json.dump(result, fh)
    return 0


if __name__ == "__main__":
    sys.exit(main())
