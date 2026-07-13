"""Governance G3 — the Coliseum acceptance ADAPTER (accepted_transition). It performs
ONLY the `accepted` claim-ladder transition, and only when the GENERIC council core
authorizes the matter (mocked here to isolate the adapter's mutation logic) AND the
ladder prerequisites hold. Fail-closed; the input registry is never mutated."""
import pytest

from coliseum.textlab import acceptance
from coliseum.textlab.acceptance import accepted_transition
from tools.council.policy import AcceptanceAuthorization


def _claims(state="replicated", evidence=("e1", "e2"), extra=None):
    c = {"claim_id": "c1", "state": state, "statement": "X holds",
         "evidence": list(evidence)}
    claims = [c] + list(extra or [])
    return {"registry_version": "1", "claims": claims}


def _auth(authorized=True, resolution="accept", rid="000010-res"):
    return AcceptanceAuthorization(authorized, resolution, rid, "polhash", [])


def _patch(monkeypatch, auth):
    monkeypatch.setattr(acceptance, "acceptance_authorization",
                        lambda root, cfg, matter: auth)


def test_accepts_when_authorized_and_prereqs(monkeypatch):
    _patch(monkeypatch, _auth())
    claims = _claims()
    new, res = accepted_transition("root", "cfg", claims, "c1", "classc-m",
                                   {"e1", "e2"})
    assert res["accepted"] and res["resolved_event_id"] == "000010-res"
    tgt = new["claims"][0]
    assert tgt["state"] == "accepted" and tgt["finding_audit"] == "000010-res"
    assert claims["claims"][0]["state"] == "replicated"      # input untouched


def test_refuses_when_not_authorized(monkeypatch):
    _patch(monkeypatch, _auth(authorized=False))
    claims = _claims()
    new, res = accepted_transition("r", "c", claims, "c1", "classc-m", {"e1", "e2"})
    assert not res["accepted"] and new["claims"][0]["state"] == "replicated"
    assert "not authorized" in res["reason"]


def test_refuses_non_accept_resolution(monkeypatch):
    _patch(monkeypatch, _auth(resolution="reject"))
    new, res = accepted_transition("r", "c", _claims(), "c1", "classc-m",
                                   {"e1", "e2"})
    assert not res["accepted"] and "not 'accept'" in res["reason"]


def test_refuses_insufficient_citable_evidence(monkeypatch):
    _patch(monkeypatch, _auth())
    new, res = accepted_transition("r", "c", _claims(), "c1", "classc-m", {"e1"})
    assert not res["accepted"] and "≥2" in res["reason"] or ">=2" in res["reason"]


def test_refuses_non_promotable_state(monkeypatch):
    _patch(monkeypatch, _auth())
    new, res = accepted_transition("r", "c", _claims(state="speculation"), "c1",
                                   "classc-m", {"e1", "e2"})
    assert not res["accepted"] and "not promotable" in res["reason"]


def test_refuses_already_accepted(monkeypatch):
    _patch(monkeypatch, _auth())
    new, res = accepted_transition("r", "c", _claims(state="accepted"), "c1",
                                   "classc-m", {"e1", "e2"})
    assert not res["accepted"] and "already accepted" in res["reason"]


def test_refuses_empty_statement(monkeypatch):
    _patch(monkeypatch, _auth())
    claims = _claims()
    claims["claims"][0]["statement"] = "   "
    new, res = accepted_transition("r", "c", claims, "c1", "classc-m", {"e1", "e2"})
    assert not res["accepted"] and "empty statement" in res["reason"]


def test_only_the_accepted_transition_no_other_mutation(monkeypatch):
    _patch(monkeypatch, _auth())
    other = {"claim_id": "c2", "state": "generalized", "statement": "Y",
             "evidence": ["e3", "e4"]}
    claims = _claims(extra=[other])
    new, res = accepted_transition("r", "c", claims, "c1", "classc-m", {"e1", "e2"})
    assert res["accepted"]
    # only c1 changed; c2 is byte-identical
    assert new["claims"][1] == other
    assert new["claims"][0]["state"] == "accepted"


def test_claim_not_found(monkeypatch):
    _patch(monkeypatch, _auth())
    new, res = accepted_transition("r", "c", _claims(), "nope", "classc-m",
                                   {"e1", "e2"})
    assert not res["accepted"] and "not found" in res["reason"]


# ------------------------------------------- audit 000747: fail-closed on bad input

@pytest.mark.parametrize("bad", [None, {"nope": 1}, {"claims": "notalist"}, 42])
def test_malformed_registry_refuses_without_raising(monkeypatch, bad):
    _patch(monkeypatch, _auth())
    new, res = accepted_transition("r", "c", bad, "c1", "classc-m", {"e1", "e2"})
    assert new is bad and not res["accepted"]      # input returned unchanged
    assert "malformed" in res["reason"]


def test_authorization_error_refuses_without_raising(monkeypatch):
    def boom(root, cfg, matter):
        raise OSError("policy path is a directory")
    monkeypatch.setattr(acceptance, "acceptance_authorization", boom)
    claims = _claims()
    new, res = accepted_transition("r", "c", claims, "c1", "classc-m", {"e1", "e2"})
    assert not res["accepted"] and "authorization failed" in res["reason"]
    assert new["claims"][0]["state"] == "replicated"   # unchanged
