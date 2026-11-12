#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Domain-separated hashing for Silent-Share (dependency-free).

Every use of a hash in the protocol is bound to an explicit domain label so
that values derived for one purpose cannot be replayed in another:

    SS-v4/salt      salt_b = H(salt_0, b)          -- GOKVS retry salts
    SS-v4/row       row positions of an attribute  -- Sparse-GOKVS rows
    SS-v4/perm      candidate enumeration order    -- Decap search
    SS-v4/session   session identifier ctx         -- key confirmation

The paper defines H_s as a random oracle; this module is its concrete
instantiation (SHA-256 with length-prefixed inputs).  Nothing here depends
on Charm, so the combinatorial logic can be unit-tested without PBC.
"""

import hashlib

DOM_SALT = b"SS-v4/salt"
DOM_ROW = b"SS-v4/row"
DOM_PERM = b"SS-v4/perm"
DOM_SESSION = b"SS-v4/session"


def _encode_part(part):
    if isinstance(part, bytes):
        return part
    if isinstance(part, str):
        return part.encode("utf-8")
    if isinstance(part, int):
        return str(part).encode("ascii")
    raise TypeError("unsupported hash input: %r" % (type(part),))


def h(domain, *parts):
    """Length-prefixed, domain-separated SHA-256.

    Length prefixing prevents ambiguity such as ("ab", "c") vs ("a", "bc").
    """
    digest = hashlib.sha256()
    digest.update(domain)
    digest.update(b"\x00")
    for part in parts:
        raw = _encode_part(part)
        digest.update(len(raw).to_bytes(4, "big"))
        digest.update(raw)
    return digest.digest()


def derive_salt(salt0, attempt):
    """salt_b for retry b (paper: salt <- H_s(salt_0 || b))."""
    return int.from_bytes(h(DOM_SALT, int(salt0), int(attempt))[:8], "little")


def row_seed(salt, attr):
    """Seed of the rho-subset assigned to an attribute."""
    return int.from_bytes(h(DOM_ROW, int(salt), attr)[:16], "little")


def perm_seed(salt, ciphertext_tag):
    """Seed of the candidate enumeration order (binds salt and C)."""
    return int.from_bytes(h(DOM_PERM, int(salt), ciphertext_tag)[:16], "little")


def session_id(ctx_parts):
    """Session identifier used by the key-confirmation tag."""
    return h(DOM_SESSION, *ctx_parts)


def _stream(seed, counter):
    return int.from_bytes(h(DOM_PERM, int(seed), int(counter))[:8], "big")


def permuted_indices(n, seed):
    """Deterministic Fisher-Yates over [0, n) driven by a hash stream.

    Used to enumerate candidate d-subsets of {0, ..., n-1} in an order that
    is independent of the lexicographic position of the intersection, so
    that latency does not correlate with *which* indices match.
    """
    indices = list(range(n))
    counter = 0
    for i in range(n - 1, 0, -1):
        j = _stream(seed, counter) % (i + 1)
        counter += 1
        indices[i], indices[j] = indices[j], indices[i]
    return indices
