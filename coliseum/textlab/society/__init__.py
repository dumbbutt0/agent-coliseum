"""Minimal Society Seed (OWNER SC-LC 2026-07-14) — the bounded scripted slice.

Everything here layers ABOVE the integrated spatial substrate without touching
it: the institutional legality filter, perception-scoped trust bookkeeping,
the derived society tick chain, and the actor-safe/privileged/outcome reports.
"""
from coliseum.textlab.society.rules import (INSTITUTION_TOKEN_STAYS_IN_A,
                                            institutional_filter,
                                            institutionally_blocked)
from coliseum.textlab.society.seed import (SocietyRunManifest, SocietyTickState,
                                          derive_society, assert_script_rule_clean)
from coliseum.textlab.society.run import (SOCIETY_EVIDENCE_FILES,
                                          actor_safe_report,
                                          assert_actor_report_schema,
                                          execute_society_seed,
                                          privileged_report, replay_society_seed)
