#!/usr/bin/env python3
"""M6 live-experiment pre-check: confirm the pinned model fleet is serving
BEFORE any SC-6 approval or paid run. Read-only (GET /api/tags), no
generation, writes nothing.

    OLLAMA_HOST=http://10.0.0.8:11434 PYTHONPATH=. python3 scripts/ollama_precheck.py

Exit 0 iff every pinned model is present at the endpoint; else prints the
gap and exits 1. The ratified fleet (DECISION-REGISTER, First Gladiator):
llama3.1, qwen3:8b, gemma3 on the LAN Mac — digests verified per-run by the
existing OllamaAgent, not here (this is a reachability + presence gate).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

PINNED = ("llama3.1", "qwen3:8b", "gemma3")


def main() -> int:
    host = os.environ.get("OLLAMA_HOST", "http://10.0.0.8:11434").rstrip("/")
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=8) as r:
            served = {m["name"] for m in json.load(r).get("models", [])}
    except Exception as exc:
        print(f"UNREACHABLE {host}: {exc}")
        print("action: bring the LAN Mac online and start ollama serving "
              "the pinned fleet (llama3.1, qwen3:8b, gemma3).")
        return 1
    missing = [m for m in PINNED
               if not any(s == m or s.startswith(m + ":") for s in served)]
    print(f"endpoint {host}: {len(served)} models served")
    if missing:
        print(f"MISSING pinned models: {missing}")
        print(f"served: {sorted(served)}")
        print("action: `ollama pull` the missing pinned models on the Mac; "
              "the localhost fleet (qwen-distilled/abliterate) is NOT the "
              "ratified fleet and must not be substituted.")
        return 1
    print(f"OK: all pinned models present ({', '.join(PINNED)}). "
          "SC-6 runs may proceed once approved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
