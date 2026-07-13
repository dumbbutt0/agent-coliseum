"""LegalActionSet — the ordered action universe + mask (profile §4.3).

A bare bit-mask is meaningless without an ordered universe; the mask is bound to
the exact order of the action-id universe. Appendix A:
`_domain = trs.legal_action_set.v1`, id `legal_action_set_id`.
"""
from __future__ import annotations

from coliseum.textlab._content_record import ContentRecord, ContentRecordError

LEGAL_ACTION_SET_SCHEMA_VERSION = "1"


class LegalActionSet(ContentRecord):
    __slots__ = ()
    DOMAIN = "trs.legal_action_set.v1"
    ID_FIELD = "legal_action_set_id"

    def __init__(self, ordered_action_ids: list, mask: list | None = None):
        if not isinstance(ordered_action_ids, list) or len(ordered_action_ids) < 1:
            raise ContentRecordError("ordered_action_ids must be a non-empty list")
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
