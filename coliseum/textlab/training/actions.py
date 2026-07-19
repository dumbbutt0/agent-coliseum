"""LegalActionSet — the ordered action universe + mask (profile §4.3).

A bare bit-mask is meaningless without an ordered universe; the mask is bound to
the exact order of the action-id universe. Appendix A:
`_domain = trs.legal_action_set.v1`, id `legal_action_set_id`.
"""
from __future__ import annotations

from coliseum.textlab._content_record import ContentRecord, ContentRecordError
from coliseum.textlab.schema import POINT_KINDS

LEGAL_ACTION_SET_SCHEMA_VERSION = "1"


class LegalActionSet(ContentRecord):
    __slots__ = ()
    DOMAIN = "trs.legal_action_set.v1"
    ID_FIELD = "legal_action_set_id"

    def __init__(self, ordered_action_ids: list, mask: list | None = None):
        if not isinstance(ordered_action_ids, list) or len(ordered_action_ids) < 2:
            # bound to a DECISION point's available_actions, which enforces >= 2
            # (audit 000886). Exposure points carry no choice and therefore have no
            # legal-action universe to export at all — see
            # `legal_action_set_for_point`, which skips them rather than admitting a
            # degenerate singleton here.
            raise ContentRecordError(
                "ordered_action_ids must have at least two actions "
                "(bound to DecisionPoint.available_actions, cardinality >= 2)")
        if any(not isinstance(a, str) or not a for a in ordered_action_ids):
            raise ContentRecordError("action ids must be non-empty strings")
        if len(set(ordered_action_ids)) != len(ordered_action_ids):
            raise ContentRecordError("action ids must be unique")
        if mask is None:
            mask = [True] * len(ordered_action_ids)
        if (not isinstance(mask, list) or len(mask) != len(ordered_action_ids)
                or any(not isinstance(b, bool) for b in mask)):
            raise ContentRecordError(
                "mask must be a list of bools bound to the ordered id-space "
                "(same length as ordered_action_ids)")
        super().__init__({
            "schema_version": LEGAL_ACTION_SET_SCHEMA_VERSION,
            "ordered_action_ids": ordered_action_ids,
            "mask": mask,
        })

    def is_legal(self, action_id: str) -> bool:
        """True iff ``action_id`` is in the universe AND its mask bit is set."""
        c = self.content
        ids = c["ordered_action_ids"]
        if action_id not in ids:
            return False
        return bool(c["mask"][ids.index(action_id)])


def legal_action_set_for_point(ordered_action_ids: list, kind: str = "decision",
                               mask: list | None = None) -> "LegalActionSet | None":
    """The export seam for a scenario point (M8 Phase 2).

    A legal-action set records WHICH CHOICE the actor had. An exposure point had
    none, so it has nothing to record: this returns ``None`` and the caller must
    omit the point from the legal-action-set export rather than write a singleton
    universe. Decision points are unchanged — they go through the >= 2 bound that
    audit 000886 guards."""
    if kind not in POINT_KINDS:
        raise ContentRecordError(f"unknown point kind {kind!r} (want {POINT_KINDS})")
    if kind == "exposure":
        if len(ordered_action_ids) != 1:
            raise ContentRecordError(
                "an exposure point has exactly 1 action (a point offering a choice "
                "is a decision, and must be exported as one)")
        return None
    return LegalActionSet(ordered_action_ids, mask)
