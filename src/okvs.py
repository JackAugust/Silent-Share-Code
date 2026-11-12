#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Scalar OKVS and Group-valued OKVS (GOKVS)."""

import random
import hashlib
import multiprocessing as mp

from charm.toolbox.pairinggroup import G2

from utils import modinv, hash_to_nonzero_zr


class LinearOKVS:
    """Scalar OKVS baseline over F_p."""

    def __init__(self, m, order, salt=0):
        self.m = m
        self.order = order
        self.salt = salt
        self.cache = {}

    def _seed_from_key(self, key):
        h = hashlib.sha256(
            ("okvs:%d:%s" % (self.salt, key)).encode()
        ).digest()[:8]
        return int.from_bytes(h, 'little')

    def row(self, key):
        if key not in self.cache:
            seed = self._seed_from_key(key)
            rng = random.Random(seed)
            self.cache[key] = [
                rng.randrange(self.order)
                for _ in range(self.m)
            ]
        return self.cache[key]

    def encode(self, pairs):
        n = len(pairs)
        m = self.m
        p = self.order
        if n > m:
            raise ValueError("n > m")

        A = [[0] * (m + 1) for _ in range(n)]
        for i, (key, value) in enumerate(pairs):
            row = self.row(key)
            A[i][:m] = row
            A[i][m] = int(value) % p

        pivots = []
        cur = 0
        for col in range(m):
            if cur >= n:
                break
            found = -1
            for r in range(cur, n):
                if A[r][col] % p != 0:
                    found = r
                    break
            if found == -1:
                continue
            if found != cur:
                A[cur], A[found] = A[found], A[cur]
            inv = modinv(A[cur][col], p)
            for j in range(col, m + 1):
                A[cur][j] = A[cur][j] * inv % p
            for r in range(cur + 1, n):
                factor = A[r][col]
                if factor == 0:
                    continue
                for j in range(col, m + 1):
                    A[r][j] = (A[r][j] - factor * A[cur][j]) % p
            pivots.append((cur, col))
            cur += 1

        if cur < n:
            raise RuntimeError("rank failure")

        D = [0] * m
        for r, c in reversed(pivots):
            value = A[r][m]
            for j in range(c + 1, m):
                value = (value - A[r][j] * D[j]) % p
            D[c] = value
        return D

    def decode(self, D, key):
        row = self.row(key)
        result = 0
        for x, y in zip(row, D):
            result = (result + x * y) % self.order
        return result


# ============================================================
# Vandermonde interpolation (优化：移除重复求逆)
# ============================================================

def vandermonde_inverse_coefficients(xs, p):
    n = len(xs)
    xs = [int(x) % p for x in xs]

    # P(X) = prod (X - x_i)
    P = [1]
    for x in xs:
        newP = [0] * (len(P) + 1)
        for k, coeff in enumerate(P):
            newP[k] = (newP[k] - x * coeff) % p
            newP[k + 1] = (newP[k + 1] + coeff) % p
        P = newP

    inverse = [[0] * n for _ in range(n)]
    for i, x in enumerate(xs):
        inv_x = modinv(x, p)   # 每个x只求一次逆
        Q = [0] * n
        Q[0] = (-P[0] * inv_x) % p
        for k in range(1, n):
            Q[k] = (Q[k - 1] - P[k]) * inv_x % p

        den = 1
        for j, xj in enumerate(xs):
            if i == j:
                continue
            den = den * (x - xj) % p
        inv_den = modinv(den, p)

        for k in range(n):
            inverse[k][i] = Q[k] * inv_den % p
    return inverse


# ============================================================
# GOKVS policy preprocessing plan
# ============================================================

class GOKVSPlan:
    def __init__(self, group, attributes):
        self.group = group
        self.order = int(group.order())
        self.attributes = list(attributes)
        self.n = len(self.attributes)
        self.m = self.n + 1

        # x_i
        self.xs = [
            int(hash_to_nonzero_zr(group, attr))
            for attr in self.attributes
        ]

        if len(set(self.xs)) != self.n:
            raise RuntimeError("H_x collision in GOKVS policy")

        # Vandermonde interpolation coefficients
        self.inverse_coeffs = vandermonde_inverse_coefficients(self.xs, self.order)

        # x_i^n for correction
        self.xn = [pow(x, self.n, self.order) for x in self.xs]


# ============================================================
# Group-valued OKVS
# ============================================================

class GOKVS:
    def __init__(self, group, n=None, plan=None):
        self.group = group
        self.order = int(group.order())
        if plan is not None:
            self.plan = plan
            self.n = plan.n
            self.m = plan.m
        else:
            if n is None:
                raise ValueError("Either n or plan is required")
            self.n = n
            self.m = n + 1
            self.plan = None

    @classmethod
    def from_attributes(cls, group, attributes):
        plan = GOKVSPlan(group, attributes)
        return cls(group, plan=plan)

    def row(self, attr):
        if self.plan is not None:
            try:
                idx = self.plan.attributes.index(attr)
                x = self.plan.xs[idx]
            except ValueError:
                x = int(hash_to_nonzero_zr(self.group, attr))
        else:
            x = int(hash_to_nonzero_zr(self.group, attr))
        row = [1]
        cur = 1
        for _ in range(self.n):
            cur = (cur * x) % self.order
            row.append(cur)
        return row

    def encode(self, pairs, plan=None):
        if plan is None:
            plan = self.plan
        if plan is None:
            attrs = [p[0] for p in pairs]
            plan = GOKVSPlan(self.group, attrs)

        n = plan.n
        if len(pairs) != n:
            raise ValueError("Unexpected number of pairs")

        values = [p[1] for p in pairs]
        D = [None] * (n + 1)

        D_free = self.group.random(G2)
        D[n] = D_free

        corrected = []
        for i in range(n):
            corrected.append(
                values[i] * (D_free ** ((-plan.xn[i]) % self.order))
            )

        inverse_coeffs = plan.inverse_coeffs
        for k in range(n):
            acc = self.group.init(G2, 1)
            coeff_row = inverse_coeffs[k]
            for i in range(n):
                exponent = coeff_row[i]
                if exponent:
                    acc = acc * (corrected[i] ** exponent)
            D[k] = acc

        return D

    def encode_parallel(self, pairs, workers=4, plan=None):
        if plan is None:
            plan = self.plan
        if plan is None:
            attrs = [p[0] for p in pairs]
            plan = GOKVSPlan(self.group, attrs)

        n = plan.n
        values = [p[1] for p in pairs]
        D_free = self.group.random(G2)
        D = [None] * (n + 1)
        D[n] = D_free

        corrected = []
        for i in range(n):
            corrected.append(
                values[i] * (D_free ** ((-plan.xn[i]) % self.order))
            )

        serialized_bases = [self.group.serialize(x) for x in corrected]
        coeff_rows = plan.inverse_coeffs

        workers = max(1, min(int(workers), n))

        # multiprocessing Pool
        def init_worker(group_name, serialized_bases):
            global _WORKER_GROUP, _WORKER_BASES
            from charm.toolbox.pairinggroup import PairingGroup
            _WORKER_GROUP = PairingGroup(group_name)
            _WORKER_BASES = [_WORKER_GROUP.deserialize(s) for s in serialized_bases]

        def worker(coeff_row):
            global _WORKER_GROUP, _WORKER_BASES
            from charm.toolbox.pairinggroup import G2
            acc = _WORKER_GROUP.init(G2, 1)
            for base, exp in zip(_WORKER_BASES, coeff_row):
                exp = int(exp)
                if exp:
                    acc = acc * (base ** exp)
            return _WORKER_GROUP.serialize(acc)

        try:
            with mp.Pool(processes=workers,
                         initializer=init_worker,
                         initargs=(CURVE, serialized_bases)) as pool:
                serialized_results = pool.map(worker, coeff_rows)
        except Exception:
            return self.encode(pairs, plan=plan)

        D[:n] = [self.group.deserialize(s) for s in serialized_results]
        return D

    def decode(self, D, attr):
        x = int(hash_to_nonzero_zr(self.group, attr))
        current = 1
        result = self.group.init(G2, 1)
        for j in range(self.m):
            if j > 0:
                current = current * x % self.order
            exponent = current
            if exponent:
                result = result * (D[j] ** exponent)
        return result