#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""External-game transcript for the bilateral protocol.

The point of this module is to make the game of Section 4.6 match the
protocol: when the owner's directional bit is zero the owner aborts and
CT_O is never produced, so the adversary must not receive a full transcript.
An earlier draft returned (CT_O, CT_R, tau, N) unconditionally, which
proves security for a distribution the protocol never produces.

The module is deliberately crypto-agnostic: it takes the encapsulation
callables as arguments so that it can be unit-tested with opaque tokens and
reused with the real PB-KEM.
"""

class HonestParties(object):
    """Attribute sets of the two honest parties (never empty by default)."""

    def __init__(self, attrs_owner, attrs_requester):
        self.attrs_owner = attrs_owner
        self.attrs_requester = attrs_requester

    def __repr__(self):
        return ("HonestParties(attrs_owner=%r, attrs_requester=%r)"
                % (self.attrs_owner, self.attrs_requester))

    def __eq__(self, other):
        return (isinstance(other, HonestParties)
                and self.attrs_owner == other.attrs_owner
                and self.attrs_requester == other.attrs_requester)


class SessionOutcome(object):
    """Result of one honest bilateral session."""

    def __init__(self, ct_owner, ct_requester, tau, nonce, b_R, aborted):
        self.ct_owner = ct_owner
        self.ct_requester = ct_requester
        self.tau = tau
        self.nonce = nonce
        self.b_R = b_R
        self.aborted = aborted

    def __repr__(self):
        return ("SessionOutcome(ct_owner=%r, ct_requester=%r, tau=%r, "
                "nonce=%r, b_R=%r, aborted=%r)"
                % (self.ct_owner, self.ct_requester, self.tau, self.nonce,
                   self.b_R, self.aborted))

    def __eq__(self, other):
        return (isinstance(other, SessionOutcome)
                and self.ct_owner == other.ct_owner
                and self.ct_requester == other.ct_requester
                and self.tau == other.tau
                and self.nonce == other.nonce
                and self.b_R == other.b_R
                and self.aborted == other.aborted)


def directional_bit(attrs, policy, d):
    """b = 1[ |attrs ∩ policy| >= d ]."""
    return int(len(set(attrs) & set(policy)) >= d)


def run_session(parties, policy_owner, policy_requester, d,
                encap_owner, encap_requester, confirm=None):
    """Execute the honest session and return what each side produces.

    b_R is the owner's decision about the requester (policy_requester).
    On b_R = 0 the owner aborts after receiving CT_R: no CT_O, no tau.
    """
    b_R = directional_bit(parties.attrs_owner, policy_requester, d)
    ct_requester, key_requester = encap_requester(policy_requester)

    if b_R == 0:
        return SessionOutcome(
            ct_owner=None, ct_requester=ct_requester,
            tau=None, nonce=None, b_R=0, aborted=True,
        )

    ct_owner, key_owner = encap_owner(policy_owner)
    tau, nonce = (None, None)
    if confirm is not None:
        tau, nonce = confirm(key_owner, key_requester, ct_owner, ct_requester)
    return SessionOutcome(
        ct_owner=ct_owner, ct_requester=ct_requester,
        tau=tau, nonce=nonce, b_R=1, aborted=False,
    )


def observable_transcript(outcome):
    """What an external observer sees.

    Returns None on abort: the protocol sends nothing beyond CT_R, so a
    transcript tuple must not be fabricated for the b_R = 0 branch.
    """
    if outcome.aborted or outcome.b_R == 0:
        return None
    return (outcome.ct_owner, outcome.ct_requester, outcome.tau, outcome.nonce)


def challenge_is_valid(attrs_adversary, policy_owner, policy_requester, d):
    """The external experiment is only meaningful if at least one side fails."""
    both = (directional_bit(attrs_adversary, policy_owner, d) == 1 and
            directional_bit(attrs_adversary, policy_requester, d) == 1)
    return not both
