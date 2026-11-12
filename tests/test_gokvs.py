#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Dependency-free tests for the Sparse-GOKVS layer.

These tests exercise the combinatorial core (peeling, the two-pass
assignment, joint encoding, domain separation and the candidate order) with
a stub group, so they run without Charm/PBC.  Tests that need a real
pairing are marked `requires_charm` and skipped here.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import hashdom
from sparse_gokvs import SparseGOKVS

G2 = "G2"


class StubGroup:
    """Multiplicative group modulo a prime; enough of the Charm API."""

    P = (1 << 61) - 1

    def order(self):
        return self.P

    def random(self, kind=None):
        # Deterministic per call is not required; distinct values suffice.
        import random as _random

        return El(_random.randrange(2, self.P), self)

    def init(self, kind, value=1):
        return El(int(value), self)


class El:
    __slots__ = ("v", "g")

    def __init__(self, value, group):
        self.v = int(value) % group.P
        self.g = group

    def __mul__(self, other):
        return El((self.v * other.v) % self.g.P, self.g)

    def __pow__(self, exponent):
        return El(pow(self.v, int(exponent), self.g.P), self.g)

    def __eq__(self, other):
        return isinstance(other, El) and self.v == other.v

    def __hash__(self):
        return hash(self.v)

    def __repr__(self):
        return "El(%d)" % self.v


def values(n, base=3):
    return [El(base + i, StubGroup()) for i in range(n)]


def test_isolated_hyperedge_two_pass():
    """An edge whose other buckets are never pivots must still decode.

    Rows: a={0,1,2}, b={0,1,3}, c={0,1,4}.  Buckets 0 and 1 are never
    pivots (their degree drops to zero), so they are exactly the buckets a
    merged one-pass encoder would read while unset.
    """
    n, m, rho = 3, 5, 3
    gokvs = SparseGOKVS(StubGroup(), n, rho=rho, m=m, salt=0, max_attempts=1)
    gokvs._current_salt = 12345
    gokvs._row_cache = {
        "a": [0, 1, 2],
        "b": [0, 1, 3],
        "c": [0, 1, 4],
    }

    vals = values(n)
    vectors, order = gokvs._assign_multi(["a", "b", "c"], [vals])

    pivots = set(v for _, v in order)
    assert 0 not in pivots and 1 not in pivots, "test premise: 0 and 1 are non-pivots"
    D = vectors[0]
    assert all(x is not None for x in D), "every bucket must be initialised"
    for attr, expected in zip(["a", "b", "c"], vals):
        assert gokvs.decode(D, attr) == expected


def test_random_hypergraph_exactness():
    """Random 3-uniform hypergraphs decode exactly at alpha = 1.25."""
    for seed in range(8):
        n = 20 + 3 * seed
        m = int(-(-1.25 * n // 1))
        gokvs = SparseGOKVS(StubGroup(), n, rho=3, m=m, salt=seed, max_attempts=25)
        attrs = ["attr-%d-%d" % (seed, i) for i in range(n)]
        vals = values(n, base=5 + seed)
        D = gokvs.encode(list(zip(attrs, vals)))
        for attr, expected in zip(attrs, vals):
            assert gokvs.decode(D, attr) == expected


def test_joint_encode_shares_salt_and_order():
    """Both vectors use one hypergraph, one peel and one final salt."""
    n, m = 30, 40
    gokvs = SparseGOKVS(StubGroup(), n, rho=3, m=m, salt=7, max_attempts=25)
    attrs = ["x%d" % i for i in range(n)]
    v1 = values(n, base=11)
    v2 = values(n, base=101)

    vectors, salt = gokvs.joint_encode(
        [list(zip(attrs, v1)), list(zip(attrs, v2))]
    )
    assert len(vectors) == 2 and len(vectors[0]) == m and len(vectors[1]) == m
    assert gokvs.final_salt == salt
    assert gokvs.peel_order is not None
    for attr, e1, e2 in zip(attrs, v1, v2):
        assert gokvs.decode(vectors[0], attr) == e1
        assert gokvs.decode(vectors[1], attr) == e2


def test_salt_retry_is_hashed_not_incremented():
    """Retry salts come from H_s(salt_0 || b), not salt_0 + b."""
    s0 = 0
    salts = [hashdom.derive_salt(s0, b) for b in range(4)]
    assert len(set(salts)) == 4
    assert salts[1] != s0 + 1


def test_domain_separation():
    """Salt, row, permutation and session derivations are disjoint."""
    a = hashdom.derive_salt(1, 2)
    b = hashdom.row_seed(1, "attr")
    c = hashdom.perm_seed(1, b"C" * 32)
    d = int.from_bytes(hashdom.session_id([b"ct", b"nonce"]), "little")
    assert len({a, b, c, d}) == 4, "domains must not collide"
    # Changing the domain input changes the output.
    assert hashdom.row_seed(1, "a") != hashdom.row_seed(1, "b")
    assert hashdom.perm_seed(1, b"A") != hashdom.perm_seed(1, b"B")


def test_permuted_indices_is_a_deterministic_permutation():
    n = 40
    order = hashdom.permuted_indices(n, 99)
    assert sorted(order) == list(range(n))
    assert hashdom.permuted_indices(n, 99) == order
    assert hashdom.permuted_indices(n, 100) != order


def test_retry_bound_is_enforced():
    """A zero retry budget must raise rather than silently grade."""
    gokvs = SparseGOKVS(StubGroup(), 5, rho=3, m=6, salt=0, max_attempts=0)
    with pytest.raises(RuntimeError):
        gokvs.encode([("a%d" % i, El(i + 2, StubGroup())) for i in range(5)])


def test_attempt_zero_keeps_the_given_salt():
    """Encoding must not hash its own input at attempt 0.

    alpha = 2 here, so the peel always succeeds and the assertion is
    deterministic.
    """
    n, m = 12, 24
    attrs = ["z%d" % i for i in range(n)]
    gokvs = SparseGOKVS(StubGroup(), n, rho=3, m=m, salt=987654321,
                        max_attempts=1)
    gokvs.encode(list(zip(attrs, values(n))))
    assert gokvs._current_salt == 987654321
    assert gokvs.final_salt == 987654321


def test_second_vector_decodes_under_the_ciphertext_salt():
    """encap() encodes D1, then D2 with salt=final_salt and max_attempts=1;
    decap() rebuilds both decoders from that same ciphertext salt.

    Regression: deriving a fresh salt at attempt 0 made the second vector
    use a different row function than the decoder, so decapsulation returned
    garbage (and the single-attempt re-encode often failed to peel).
    """
    n, m = 60, 75
    attrs = ["d%d" % i for i in range(n)]
    v1 = values(n, base=11)
    v2 = values(n, base=311)

    first = SparseGOKVS(StubGroup(), n, rho=3, m=m, salt=0, max_attempts=25)
    D1 = first.encode(list(zip(attrs, v1)))
    ct_salt = first.final_salt

    second = SparseGOKVS(StubGroup(), n, rho=3, m=m, salt=ct_salt,
                         max_attempts=1)
    D2 = second.encode(list(zip(attrs, v2)))

    d1 = SparseGOKVS(StubGroup(), n, rho=3, m=m, salt=ct_salt, max_attempts=1)
    d2 = SparseGOKVS(StubGroup(), n, rho=3, m=m, salt=ct_salt, max_attempts=1)
    for attr, e1, e2 in zip(attrs, v1, v2):
        assert d1.decode(D1, attr) == e1
        assert d2.decode(D2, attr) == e2


def test_joint_vectors_decode_from_the_ciphertext_salt():
    """encap() joint-encodes D1 and D2; decap() rebuilds both decoders from
    the single salt stored in the ciphertext.

    This is the protocol's actual path (paper Algorithm 3): one peel, one
    salt, two vectors.  Decoding must work from a fresh instance that only
    knows the salt, exactly as decap() does.
    """
    n, m = 80, 100
    attrs = ["j%d" % i for i in range(n)]
    v1 = values(n, base=7)
    v2 = values(n, base=409)

    encoder = SparseGOKVS(StubGroup(), n, rho=3, m=m, salt=0, max_attempts=25)
    (D1, D2), salt = encoder.joint_encode(
        [list(zip(attrs, v1)), list(zip(attrs, v2))])

    d1 = SparseGOKVS(StubGroup(), n, rho=3, m=m, salt=salt, max_attempts=1)
    d2 = SparseGOKVS(StubGroup(), n, rho=3, m=m, salt=salt, max_attempts=1)
    for attr, e1, e2 in zip(attrs, v1, v2):
        assert d1.decode(D1, attr) == e1
        assert d2.decode(D2, attr) == e2


def test_rows_are_distinct_and_size_rho():
    gokvs = SparseGOKVS(StubGroup(), 10, rho=3, m=13, salt=3, max_attempts=5)
    for i in range(30):
        row = gokvs._row("probe-%d" % i)
        assert len(row) == 3 and len(set(row)) == 3
        assert all(0 <= p < 13 for p in row)
