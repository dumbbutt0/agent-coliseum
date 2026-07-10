# Release blockers (recorded 2026-07-10, full-audit item 12 — notes only, no release)

Repository verdict at the audit: **research-use only.** These are the known gaps between
that and a releasable artifact. None are scheduled; recording them is the deliverable.

1. **Immutable evidence bundle + checksums.** All primary evidence (`logs/runs/` — decisions,
   captures, snapshots, run.json) is gitignored; only derived summaries are committed. A
   release needs a content-addressed evidence bundle with a checksum manifest, or a published
   archive the repo pins by hash.
2. **No LICENSE.** Undistributable as-is.
3. **No dependency lock or packaging.** `requirements.txt` is loose (`numpy>=1.26`,
   `pyyaml>=6.0`, `pytest>=8.0`); no `pyproject.toml`, no lockfile, not pip-installable.
4. **LAN address in docs/examples.** `10.0.0.8` appears in docstrings/docs/reports only
   (never in code logic — the code reads `$OLLAMA_HOST`). Examples should be normalized to
   `$OLLAMA_HOST` placeholders before any publication.
5. **Clean-clone offline reproduction untested.** The offline replay gate runs from the
   working tree; nobody has verified a fresh clone + evidence bundle reproduces byte-identical
   derived outputs on another machine.
6. **TextLab vs legacy arena scaffold separation unvalidated.** The repo still carries the
   pre-textlab duel/Elo scaffold; a release must either separate or explicitly scope it.
7. **Legacy evidence compatibility statement.** Sweep-v2 (and older) evidence is not
   replayable under the current runner (CONFIG DRIFT by construction — no stored
   behavioral_config/snapshots). A release must state exactly which evidence generations the
   shipped code can replay: currently exp-1/exp-2 and anything produced at schema v2+.
