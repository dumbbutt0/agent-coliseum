# H7 activation sequence — gate artifacts

Produced by `scripts/council_staging.py` (hardening directive item 15).
Each JSON artifact records one ordered activation gate. Gates 1–4 are
automated and ran green; gates 5–7 are OWNER-ATTENDED (sudo / live review /
enablement) and their artifacts carry the exact commands.

| gate | what it proves | mode |
|------|----------------|------|
| 1 `gate1-suite` | full test suite green at the isolated commit | automated |
| 2 `gate2-e2e` | fake-Codex end-to-end on a fresh staging council through the REAL `codex_launcher`/`codex_watch`/`runner`: source round → GO; auto-approved mock experiment → REAL evidence manifest → result round → APPROVED. No human token anywhere. | automated |
| 3 `gate3-drills` | torn-tail detection + append refusal on a scratch COPY of the live chain; STOP-mid-claim rollback; kill-between-journal-steps recovery (both directions, idempotent) | automated |
| 4 `gate4-noservice` | no coliseum systemd unit or cron entry exists anywhere before activation | automated |
| 5 `gate5-install-without-enable` | unit exists in-repo, NOT enabled; exact `sudo cp` install commands (install ≠ enable) | owner |
| 6 `gate6-owner-foreground-review` | owner runs ONE foreground `--once` pass on live and reviews it | owner |
| 7 `gate7-owner-enable` | owner enables ONLY the codex launcher | owner |

Notes:

- Artifacts record the tree they ran against (the audited commit's parent —
  the artifacts themselves are part of the audited commit, so their hash
  cannot appear inside them). Re-running
  `PYTHONPATH=. python3 scripts/council_staging.py` at the audited commit
  reproduces every automated gate.
- The staging harness NEVER writes to the live council: gate 3 copies the
  live chain into scratch; gates 2/3 bootstrap fresh staging councils whose
  identity anchors live only under the scratch dir (the live root-owned
  enrollment anchor refuses them, so staging can never mint live authority).
- Builder / experiment / society automation stay disabled; each later
  capability requires its own dedicated audit before activation.
