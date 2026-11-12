#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Sparse group-valued OKVS using rho-sparse peeling.

Two-pass encoding (the order of the passes is load-bearing):
    1. peel the hypergraph to obtain a pivot set and a peel order;
    2. initialise *every* non-pivot bucket with an independent uniform
       group element;
    3. walking the peel order backwards, solve each pivot bucket so that
       Decode(attr) returns the encoded value.

Merging passes 2 and 3 would read uninitialised buckets whenever an edge
owns a bucket that never becomes a pivot (for example, the bucket's degree
drops to zero because the edge was peeled through another bucket).  The
"unassigned bucket" guard below exists to catch exactly that regression.

Rows are rho-subsets derived from H_s (hashdom.row_seed), and retry salts
are derived as salt_b = H_s(salt_0 || b) for b >= 1, with attempt 0 using
salt_0 itself.  The b = 0 identity is load-bearing: encap() encodes two
vectors by handing the accepted salt back in with max_attempts = 1, and
decap() rebuilds the row function from the salt stored in the ciphertext.
If attempt 0 hashed its input, encoding and decoding would use different
row functions, and the single-attempt re-encode would peel a fresh
hypergraph instead of the one that already peeled.
`joint_encode` peels once and assigns two value vectors over the same
hypergraph and the same final salt, matching Algorithm 3.

Coefficients are all one: Decode(attr) = prod_{j in row(attr)} D[j], i.e.
rho group multiplications and no exponentiations.
"""

import math
from collections import deque

import hashdom

try:  # charm is optional so that the combinatorial logic is unit-testable
    from charm.toolbox.pairinggroup import G2
except ImportError:  # pragma: no cover - exercised only without Charm
    G2 = "G2"


class SparseGOKVS:
    def __init__(self, group, n, rho=3, m=None, salt=0, max_attempts=20):
        """
        Args:
            group:          PairingGroup instance (e.g. BN254, BLS12_381).
            n:              number of key-value pairs to encode.
            rho:            row sparsity (default 3).
            m:              number of buckets; if None, m = ceil(1.25 * n).
            salt:           initial salt salt_0 for row hashing.
            max_attempts:   number of salt retries if peeling fails.
        """
        self.group = group
        self.order = int(group.order())
        self.n = n
        self.rho = rho
        self.m = int(math.ceil(1.25 * n)) if m is None else int(m)
        self.salt0 = salt
        self.max_attempts = max_attempts

        if self.rho < 2:
            raise ValueError("rho must be at least 2")
        if self.m <= self.n:
            raise ValueError("m must be greater than n for sparse GOKVS")

        self._row_cache = {}
        self._current_salt = salt
        self.final_salt = None
        self.peel_order = None

    # ------------------------------------------------------------------
    # Row hashing and retry salts
    # ------------------------------------------------------------------
    def _row(self, attr):
        """Return rho distinct positions in [0, m-1] for this attribute."""
        if attr in self._row_cache:
            return self._row_cache[attr]

        seed = hashdom.row_seed(self._current_salt, attr)
        # Hash-stream sampling without replacement, deterministic across
        # Python versions (unlike random.sample with an int seed).
        chosen = []
        counter = 0
        while len(chosen) < self.rho:
            candidate = hashdom._stream(seed, counter) % self.m
            counter += 1
            if candidate not in chosen:
                chosen.append(candidate)
        self._row_cache[attr] = chosen
        return chosen

    def rows(self, attrs):
        """Row positions for a batch of attributes under the current salt."""
        return [self._row(attr) for attr in attrs]

    # ------------------------------------------------------------------
    # Encoding
    # ------------------------------------------------------------------
    def encode(self, pairs):
        """Encode a list of (attr, group_element) pairs into one vector."""
        values = [value for _, value in pairs]
        vectors, salt = self.joint_encode([pairs], [values])
        return vectors[0]

    def joint_encode(self, pair_lists, value_lists=None):
        """Encode several value vectors over one hypergraph and one salt.

        Args:
            pair_lists: list of [(attr, value), ...]; all lists must share
                        the same attribute order (length n).
            value_lists: optional list of value lists; defaults to the
                        values carried by pair_lists.
        Returns:
            (vectors, final_salt) where vectors[k] is the bucket array for
            value_lists[k], all over bucket count self.m.
        """
        if value_lists is None:
            value_lists = [[value for _, value in pairs] for pairs in pair_lists]
        if len(pair_lists) != len(value_lists):
            raise ValueError("pair_lists and value_lists must align")
        for pairs in pair_lists:
            if len(pairs) != self.n:
                raise ValueError("Expected %d pairs, got %d" % (self.n, len(pairs)))

        attrs = [attr for attr, _ in pair_lists[0]]

        for attempt in range(self.max_attempts):
            # Attempt 0 keeps salt_0 unchanged so that the accepted salt can
            # be handed back in (max_attempts=1) and reproduce this exact
            # hypergraph.  Only retries b >= 1 are hashed.
            self._current_salt = (int(self.salt0) if attempt == 0
                                  else hashdom.derive_salt(self.salt0, attempt))
            self._row_cache.clear()
            try:
                vectors, order = self._assign_multi(attrs, value_lists)
            except RuntimeError:
                continue
            self.final_salt = self._current_salt
            self.peel_order = order
            self.salt0 = self._current_salt
            return vectors, self.final_salt

        raise RuntimeError(
            "Peeling failed after %d attempts. "
            "Increase m, rho, or max_attempts." % self.max_attempts
        )

    def _peel(self, attrs):
        """Peel the incidence hypergraph; return (positions, peel order)."""
        n, m, rho = self.n, self.m, self.rho

        edge_positions = [None] * n
        buckets = [[] for _ in range(m)]
        for eid, attr in enumerate(attrs):
            positions = self._row(attr)
            edge_positions[eid] = positions
            for pos in positions:
                buckets[pos].append(eid)

        degree = [len(buckets[i]) for i in range(m)]
        peeled_flag = [False] * n

        queue = deque(v for v in range(m) if degree[v] == 1)
        peeled_edges = []  # (eid, pivot vertex)

        while queue:
            v = queue.popleft()
            if degree[v] != 1:
                continue
            eid = None
            for candidate in buckets[v]:
                if not peeled_flag[candidate]:
                    eid = candidate
                    break
            if eid is None:
                continue

            peeled_flag[eid] = True
            peeled_edges.append((eid, v))

            for u in edge_positions[eid]:
                degree[u] -= 1
                if degree[u] == 1:
                    queue.append(u)

        if len(peeled_edges) != n:
            raise RuntimeError(
                "Peeling failed: %d/%d edges peeled" % (len(peeled_edges), n)
            )
        return edge_positions, peeled_edges

    def _assign_multi(self, attrs, value_lists):
        """One peel, then two-pass assignment for every value vector."""
        edge_positions, peeled_edges = self._peel(attrs)
        m = self.m

        # Pass 1: every bucket that is not a pivot gets an independent
        # uniform element.  This must happen before any reverse assignment.
        pivots = set(v for _, v in peeled_edges)
        vectors = [[None] * m for _ in value_lists]
        for index in range(len(value_lists)):
            for i in range(m):
                if i not in pivots:
                    vectors[index][i] = self.group.random(G2)

        # Pass 2: reverse peel order.  For an edge peeled at v, every other
        # position is already final (either a pivot of a later-peeled edge,
        # or a non-pivot initialised in pass 1).
        for eid, pivot in reversed(peeled_edges):
            positions = edge_positions[eid]
            for index, values in enumerate(value_lists):
                D = vectors[index]
                if D[pivot] is not None:
                    raise RuntimeError("Peeling assignment conflict")
                result = values[eid]
                for pos in positions:
                    if pos == pivot:
                        continue
                    if D[pos] is None:
                        raise RuntimeError(
                            "Reverse peeling encountered unassigned bucket"
                        )
                    result = result * (D[pos] ** (-1))
                D[pivot] = result

        return vectors, list(peeled_edges)

    # ------------------------------------------------------------------
    # Decoding
    # ------------------------------------------------------------------
    def decode(self, D, attr):
        """Decode the group element associated with attr.

        Note: this uses only the public vector D and the public row function.
        It does not take a secret key; secrecy comes from the fact that the
        decoded element is useless without the attribute key used in the
        subsequent pairing (Proposition 2 in the paper).
        """
        if len(D) != self.m:
            raise ValueError("D has wrong length")

        positions = self._row(attr)

        result = self.group.init(G2, 1)
        for pos in positions:
            result = result * D[pos]
        return result
