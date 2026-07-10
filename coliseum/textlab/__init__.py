"""textlab — the text-scenario behavioral lab (Coliseum MVP).

Runs one agent at a time through archetypal moral dilemmas defined as YAML data,
logging every decision as a node in an append-only JSONL run log. Behavioral facts
(obedience, refusal, mercy...) are NEVER rewarded in-run — they are derived after
the fact from the logs (`raw -> derived -> render`, same discipline as the arena).

Design spec: the vault's `05_blueprints/coliseum-mvp-text-lab.md` +
`coliseum-codex-build-prompt.md` (the five rules live there).
"""

__version__ = "0.1.0"
