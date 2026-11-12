#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for the b_R-aware external session (C6)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from sim.external_game import (HonestParties, challenge_is_valid,
                               directional_bit, observable_transcript,
                               run_session)


def fake_encap(tag):
    def _encap(policy):
        return ("CT-" + tag, "K-" + tag)
    return _encap


def test_directional_bit():
    assert directional_bit({"a", "b", "c"}, {"a", "b"}, 2) == 1
    assert directional_bit({"a"}, {"a", "b"}, 2) == 0


def test_abort_transcript_has_no_owner_ciphertext():
    parties = HonestParties(attrs_owner={"x"}, attrs_requester={"a", "b"})
    outcome = run_session(
        parties,
        policy_owner={"a", "b"},       # owner asks for a,b
        policy_requester={"q1", "q2"},  # requester asks for q1,q2
        d=2,
        encap_owner=fake_encap("O"),
        encap_requester=fake_encap("R"),
    )
    assert outcome.b_R == 0 and outcome.aborted
    assert outcome.ct_owner is None and outcome.tau is None
    assert observable_transcript(outcome) is None


def test_full_transcript_when_both_directions_pass():
    parties = HonestParties(attrs_owner={"q1", "q2"}, attrs_requester={"a", "b"})
    calls = {}

    def confirm(k_owner, k_requester, ct_owner, ct_requester):
        calls["keys"] = (k_owner, k_requester)
        return ("tau", "nonce")

    outcome = run_session(
        parties,
        policy_owner={"a", "b"},
        policy_requester={"q1", "q2"},
        d=2,
        encap_owner=fake_encap("O"),
        encap_requester=fake_encap("R"),
        confirm=confirm,
    )
    assert outcome.b_R == 1 and not outcome.aborted
    assert observable_transcript(outcome) == ("CT-O", "CT-R", "tau", "nonce")
    assert calls["keys"] == ("K-O", "K-R")


def test_challenge_validity_excludes_double_success():
    assert challenge_is_valid({"a", "b", "q1", "q2"}, {"a", "b"}, {"q1", "q2"}, 2) is False
    assert challenge_is_valid({"a", "q1"}, {"a", "b"}, {"q1", "q2"}, 2) is True
