#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Silent-Share core: PB-KEM and bilateral composition.

Supports both dense Vandermonde GOKVS and sparse GOKVS via the
USE_SPARSE_GOKVS flag in config.py.
"""

import os
import sys
import math

# Ensure src/ is on the path when run directly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from charm.toolbox.pairinggroup import ZR, G1, G2, GT, pair

from utils import (modinv, xor_bytes, hash_to_nonzero_zr,
                   ro_hash_bytes, random_bytes, now)
import hashdom
from search import candidate_subsets

try:
    from config import (USE_SPARSE_GOKVS, SPARSE_GOKVS_RHO,
                        SPARSE_GOKVS_M_FACTOR)
except ImportError:
    USE_SPARSE_GOKVS = False
    SPARSE_GOKVS_RHO = 3
    SPARSE_GOKVS_M_FACTOR = 1.3

if USE_SPARSE_GOKVS:
    from sparse_gokvs import SparseGOKVS
else:
    from okvs import GOKVS, GOKVSPlan, vandermonde_inverse_coefficients


class UserSecretKey:
    def __init__(self, uid, attributes, x_map, D1_map, D2_map):
        self.uid = uid
        self.attributes = list(attributes)
        self.x = x_map
        self.D1 = D1_map
        self.D2 = D2_map


class SilentShare:
    def __init__(self, group, threshold=5):
        self.group = group
        self.p = int(group.order())
        self.d = threshold

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------
    def setup(self, universe):
        start = now()
        g1 = self.group.random(G1)
        g2 = self.group.random(G2)
        y = self.group.random(ZR)
        while int(y) == 0:
            y = self.group.random(ZR)
        Y = pair(g1, g2) ** y

        t_map = {}
        T_map = {}
        for attr in universe:
            t = self.group.random(ZR)
            while int(t) == 0:
                t = self.group.random(ZR)
            t_map[attr] = int(t)
            T_map[attr] = g2 ** t

        pp = {'g1': g1, 'g2': g2, 'Y': Y, 'T': T_map}
        msk = {'y': y, 't': t_map}
        return pp, msk, (now() - start) * 1000

    # ------------------------------------------------------------------
    # Key generation
    # ------------------------------------------------------------------
    def keygen(self, pp, msk, uid, attributes):
        start = now()
        coeffs = [msk['y']]
        for _ in range(self.d - 1):
            coeffs.append(self.group.random(ZR))

        x_map = {}
        D1_map = {}
        D2_map = {}
        for attr in attributes:
            x = int(hash_to_nonzero_zr(self.group, attr))
            x_map[attr] = x
            # Horner evaluation
            qx = int(coeffs[-1])
            for j in range(len(coeffs) - 2, -1, -1):
                qx = (qx * x + int(coeffs[j])) % self.p
            t_a = int(msk['t'][attr])
            inv_t = modinv(t_a, self.p)
            D1_map[attr] = pp['g1'] ** ((qx * inv_t) % self.p)
            D2_map[attr] = pp['g1'] ** qx

        sk = UserSecretKey(uid, attributes, x_map, D1_map, D2_map)
        return sk, (now() - start) * 1000

    # ------------------------------------------------------------------
    # Encapsulation
    # ------------------------------------------------------------------
    def encap(self, pp, msk, policy):
        start_total = now()
        n = len(policy)
        kappa = random_bytes()
        s = self.group.random(ZR)
        while int(s) == 0:
            s = self.group.random(ZR)
        Y_s = pp['Y'] ** s

        hk = ro_hash_bytes(self.group, b"H_K", Y_s)
        hv = ro_hash_bytes(self.group, b"H_V", Y_s)
        E0 = xor_bytes(kappa, hk)
        C = hv

        # Generate correlated group values for each policy attribute
        E1 = []
        E2 = []
        for attr in policy:
            r = self.group.random(ZR)
            E1.append(pp['T'][attr] ** (s + r))
            E2.append(pp['g2'] ** r)

        # Encode using the selected GOKVS
        if USE_SPARSE_GOKVS:
            rho = SPARSE_GOKVS_RHO
            m = int(math.ceil(SPARSE_GOKVS_M_FACTOR * n))

            t0 = now()
            # One hypergraph, one peel, two value vectors (paper Algorithm 3).
            # Encoding the vectors separately would peel twice and would make
            # D2 depend on re-deriving the accepted salt instead of sharing
            # the peel by construction.
            gokvs = SparseGOKVS(self.group, n, rho=rho, m=m)
            vectors, salt_used = gokvs.joint_encode(
                [list(zip(policy, E1)), list(zip(policy, E2))])
            D1, D2 = vectors
            gokvs_ms1 = (now() - t0) * 1000
            gokvs_ms2 = 0.0

            details = {
                'total_ms': (now() - start_total) * 1000,
                'gokvs_preprocess_ms': 0.0,
                'gokvs_d1_ms': gokvs_ms1,
                'gokvs_d2_ms': gokvs_ms2,
                'gokvs_total_ms': gokvs_ms1 + gokvs_ms2,
                'Y_s': Y_s
            }
            ct = {
                'E0': E0, 'C': C, 'D1': D1, 'D2': D2, 'n': n,
                'gokvs_salt': salt_used,
                'gokvs_rho': rho,
                'gokvs_m': m
            }
        else:
            # Dense Vandermonde GOKVS with shared plan
            t0 = now()
            plan = GOKVSPlan(self.group, policy)
            gokvs = GOKVS(self.group, plan=plan)
            preprocess_ms = (now() - t0) * 1000

            t0 = now()
            D1 = gokvs.encode(list(zip(policy, E1)), plan=plan)
            gokvs_ms1 = (now() - t0) * 1000

            t0 = now()
            D2 = gokvs.encode(list(zip(policy, E2)), plan=plan)
            gokvs_ms2 = (now() - t0) * 1000

            details = {
                'total_ms': (now() - start_total) * 1000,
                'gokvs_preprocess_ms': preprocess_ms,
                'gokvs_d1_ms': gokvs_ms1,
                'gokvs_d2_ms': gokvs_ms2,
                'gokvs_total_ms': preprocess_ms + gokvs_ms1 + gokvs_ms2,
                'Y_s': Y_s
            }
            ct = {'E0': E0, 'C': C, 'D1': D1, 'D2': D2, 'n': n}

        return ct, kappa, details

    # ------------------------------------------------------------------
    # Decapsulation
    # ------------------------------------------------------------------
    def decap(self, pp, sk, ct, optimize='precompute', order='prh',
              hint_subset=None, budget=None, search_seed=None):
        """Decapsulate.

        Args:
            order:       'prh' (default) or 'lex'; ignored when hint_subset
                         is given.
            hint_subset: explicit index tuple of the correct d-subset.
                         Benchmarks must pass this to isolate reconstruction
                         cost; it must never be emulated by permuting the
                         attribute list.
            budget:      maximum number of candidate subsets to try;
                         exhausting it is reported as a failure.
            search_seed: override for the H_s(salt||C) permutation seed.
        """
        start_total = now()
        A = len(sk.attributes)
        n = ct['n']

        # Stage 1: GOKVS decoding
        t0 = now()
        if USE_SPARSE_GOKVS:
            salt_from_ct = ct.get('gokvs_salt', 0)
            rho_from_ct = ct.get('gokvs_rho', SPARSE_GOKVS_RHO)
            m_from_ct = ct.get('gokvs_m', int(math.ceil(SPARSE_GOKVS_M_FACTOR * n)))
            gokvs1 = SparseGOKVS(self.group, n, rho=rho_from_ct, m=m_from_ct,
                                 salt=salt_from_ct, max_attempts=1)
            gokvs2 = SparseGOKVS(self.group, n, rho=rho_from_ct, m=m_from_ct,
                                 salt=salt_from_ct, max_attempts=1)
            decoded1 = {}
            decoded2 = {}
            for attr in sk.attributes:
                decoded1[attr] = gokvs1.decode(ct['D1'], attr)
                decoded2[attr] = gokvs2.decode(ct['D2'], attr)
        else:
            gokvs1 = GOKVS(self.group, n=n)
            gokvs2 = GOKVS(self.group, n=n)
            decoded1 = {}
            decoded2 = {}
            for attr in sk.attributes:
                decoded1[attr] = gokvs1.decode(ct['D1'], attr)
                decoded2[attr] = gokvs2.decode(ct['D2'], attr)
        decode_ms = (now() - t0) * 1000

        # Stage 2: Pairing computations
        t0 = now()
        Z = []
        xs = []
        for attr in sk.attributes:
            z1 = pair(sk.D1[attr], decoded1[attr])
            z2 = pair(sk.D2[attr], decoded2[attr])
            z = z1 * z2 ** (-1)
            Z.append(z)
            xs.append(sk.x[attr])
        pairing_ms = (now() - t0) * 1000

        # Stage 3: Lagrange cache preparation (if needed)
        cache_ms = 0.0
        ratio_cache = None
        if optimize in ('precompute', 'multi'):
            t0 = now()
            ratio_cache = self.prepare_lagrange_cache(xs)
            cache_ms = (now() - t0) * 1000

        # Stage 4: Threshold subset enumeration
        recon_ms = 0.0
        trials = 0
        recovered = None
        budget_exhausted = False
        target_C = ct['C']
        if search_seed is None:
            search_seed = hashdom.perm_seed(int(ct.get('gokvs_salt', 0)), target_C)
        if A >= self.d:
            t0 = now()
            for subset in candidate_subsets(A, self.d, order=order,
                                            seed=search_seed,
                                            hint=hint_subset):
                if budget is not None and trials >= budget:
                    budget_exhausted = True
                    break
                trials += 1
                omega = self.reconstruct_candidate(
                    subset, Z, xs, optimize, ratio_cache
                )
                if ro_hash_bytes(self.group, b"H_V", omega) == target_C:
                    recovered = omega
                    break
            recon_ms = (now() - t0) * 1000

        # Stage 5: Key recovery
        key_ms = 0.0
        kappa = None
        if recovered is not None:
            t0 = now()
            hk = ro_hash_bytes(self.group, b"H_K", recovered)
            kappa = xor_bytes(ct['E0'], hk)
            key_ms = (now() - t0) * 1000

        total_ms = (now() - start_total) * 1000
        details = {
            'total_ms': total_ms,
            'decode_ms': decode_ms,
            'pairing_ms': pairing_ms,
            'recon_ms': recon_ms,
            'lagrange_cache_ms': cache_ms,
            'key_ms': key_ms,
            'trials': trials,
            'order': 'hint' if hint_subset is not None else order,
            'search_seed': search_seed,
            'budget': budget,
            'budget_exhausted': budget_exhausted,
            'success': recovered is not None
        }
        return kappa, details

    # ------------------------------------------------------------------
    # Lagrange helpers
    # ------------------------------------------------------------------
    def lagrange_naive(self, subset, xs):
        p = self.p
        deltas = []
        for i in subset:
            xi = xs[i]
            delta = 1
            for j in subset:
                if i == j:
                    continue
                xj = xs[j]
                num = (-xj) % p
                den = (xi - xj) % p
                delta = (delta * num) % p
                delta = (delta * modinv(den, p)) % p
            deltas.append(delta)
        return deltas

    def prepare_lagrange_cache(self, xs):
        p = self.p
        A = len(xs)
        ratio = [[0] * A for _ in range(A)]
        for i in range(A):
            xi = xs[i]
            for j in range(A):
                if i == j:
                    continue
                xj = xs[j]
                ratio[i][j] = ((-xj) * modinv((xi - xj) % p, p)) % p
        return ratio

    def lagrange_cached(self, subset, ratio):
        p = self.p
        deltas = []
        for i in subset:
            value = 1
            for j in subset:
                if i == j:
                    continue
                value = (value * ratio[i][j]) % p
            deltas.append(value)
        return deltas

    def joint_multi_exp(self, bases, exponents):
        if not bases:
            return self.group.init(GT, 1)
        exponents = [int(e) % self.p for e in exponents]
        max_bits = max(e.bit_length() for e in exponents)
        acc = self.group.init(GT, 1)
        for bit in range(max_bits - 1, -1, -1):
            acc = acc * acc
            for base, exponent in zip(bases, exponents):
                if (exponent >> bit) & 1:
                    acc = acc * base
        return acc

    def reconstruct_candidate(self, subset, Z, xs, mode, ratio_cache=None):
        if mode == 'naive':
            deltas = self.lagrange_naive(subset, xs)
        else:
            deltas = self.lagrange_cached(subset, ratio_cache)
        bases = [Z[i] for i in subset]
        if mode == 'multi':
            return self.joint_multi_exp(bases, deltas)
        result = self.group.init(GT, 1)
        for base, exponent in zip(bases, deltas):
            result = result * (base ** exponent)
        return result