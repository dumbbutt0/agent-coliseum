# Decisions — session 2026-07-10-5

1. Moral-tag differences between twins are semantic NOTES in the lint, not structural violations — a tag can BE the manipulated variable (water_bearer harm tag).
2. run_id stays the CONFIG identity; the directory is the EVIDENCE identity — metrics report_id follows the directory.
3. Replay reproduces the STORED spec verbatim rather than re-deriving from code constants — code drift surfaces as run_id drift, which is the honest signal.
4. Pre-hardening runs cannot be replayed under new code (no stored agent_config) — refused with a clear message rather than faking lineage.
