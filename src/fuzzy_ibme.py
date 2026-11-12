#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fuzzy IB-ME (TIFS 2023) - BN254 reproducible experimental version (revised experimental design)
===============================================================

This script implements the fuzzy IB-ME from Section V-C of the paper, adapted for BN254 heterogeneous pairing.

Experimental design:
  EXP-A: attribute size n varies, fixed R = n, d = 5, measure EKGen, DKGen, Enc, Correct Dec, storage
  EXP-B: threshold d varies, fixed n = R = 25, measure Enc, Correct Dec
  EXP-C: subset search complexity, fixed n = R = 25, d = 5, varying actual intersection size n', measure search time in enumerate mode
"""

import argparse
import csv
import itertools
import math
import os
import statistics
import time
# Python 3.6 compatibility: provide perf_counter_ns()
if not hasattr(time, 'perf_counter_ns'):
    def _perf_counter_ns():
        return int(time.perf_counter() * 1e9)
    time.perf_counter_ns = _perf_counter_ns

from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from charm.toolbox.pairinggroup import PairingGroup, ZR, G1, G2, GT, pair

import config

# ------------------------------------------------------------
# Global parameters (imported from config, but can be overridden in main)
# ------------------------------------------------------------
CURVE = config.CURVE
DEFAULT_D = config.DEFAULT_D
DEFAULT_ROUNDS = config.ROUNDS
DEFAULT_WARMUP = 1
DEFAULT_OUT = "fuzzy_ibme_bn254_results"


# ------------------------------------------------------------
# Basic math utilities
# ------------------------------------------------------------
def modinv(a: int, p: int) -> int:
    a %= p
    if a == 0:
        raise ZeroDivisionError("modular inverse of zero")
    return pow(a, p - 2, p)


def poly_eval(coeffs: Sequence[int], x: int, p: int) -> int:
    x %= p
    acc = 0
    for c in reversed(coeffs):
        acc = (acc * x + c) % p
    return acc


def rand_nonzero_zr(group) -> object:
    while True:
        z = group.random(ZR)
        if int(z) != 0:
            return z


def random_poly(group, degree: int, constant: int) -> List[int]:
    p = int(group.order())
    return [constant % p] + [int(rand_nonzero_zr(group)) for _ in range(degree)]


def lagrange_coeff(i: int, S: Sequence[int], x: int, p: int) -> int:
    num = 1
    den = 1
    for j in S:
        if j == i:
            continue
        num = (num * (x - j)) % p
        den = (den * (i - j)) % p
    return num * modinv(den, p) % p


def mean_or_nan(values: Sequence[float]) -> float:
    return statistics.mean(values) if values else float("nan")


def power_signed(base, exp):
    if exp < 0:
        return ~(base ** (-exp))
    else:
        return base ** exp


# ------------------------------------------------------------
# FuzzyIBME_BN254 class
# ------------------------------------------------------------
class FuzzyIBME_BN254:
    def __init__(self, group: PairingGroup, d: int = DEFAULT_D):
        self.group = group
        self.d = d
        self.order = int(group.order())
        if d < 1:
            raise ValueError("d must be >= 1")

        self._attr_cache: Dict[str, int] = {}
        self._T1_cache: Dict[Tuple[int, int], object] = {}
        self._T2_cache: Dict[Tuple[int, int], object] = {}
        self._H1_cache: Dict[Tuple[int, int], object] = {}
        self._H2_cache: Dict[Tuple[int, int], object] = {}

        # Debug intermediate values (can be kept for correctness testing)
        self._debug_Ks = None
        self._debug_Kl = None
        self._debug_K_s_prime = None
        self._debug_K_l_prime = None

    def attr_to_int(self, attr: str) -> int:
        if attr not in self._attr_cache:
            x = int(self.group.hash(attr.encode("utf-8"), ZR)) % self.order
            if x == 0:
                x = 1
            self._attr_cache[attr] = x
        return self._attr_cache[attr]

    def setup(self, n: int) -> Tuple[dict, dict]:
        if n < 1:
            raise ValueError("n must be >= 1")
        if self.d > n + 1:
            raise ValueError(f"d={self.d} is incompatible with n={n}")

        g = self.group.random(G1)
        g2 = self.group.random(G2)
        rho3 = int(rand_nonzero_zr(self.group))
        g3 = g ** rho3
        g3_2 = g2 ** rho3

        t_coeffs = [int(rand_nonzero_zr(self.group)) for _ in range(n + 1)]
        l_coeffs = [int(rand_nonzero_zr(self.group)) for _ in range(n + 1)]
        t1 = [g ** c for c in t_coeffs]
        t2 = [g2 ** c for c in t_coeffs]
        l1 = [g ** c for c in l_coeffs]
        l2 = [g2 ** c for c in l_coeffs]

        alpha = rand_nonzero_zr(self.group)
        beta = rand_nonzero_zr(self.group)
        theta1 = rand_nonzero_zr(self.group)
        theta2 = rand_nonzero_zr(self.group)
        theta3 = rand_nonzero_zr(self.group)
        theta4 = rand_nonzero_zr(self.group)

        g1_pub = g ** alpha
        eta1 = g ** theta1
        eta2 = g ** theta2
        eta3 = g ** theta3
        eta4 = g ** theta4

        Y1 = pair(g1_pub, g2) ** (theta1 * theta2)
        g_beta = g2 ** beta
        Y2 = pair(g3, g_beta) ** (theta1 * theta2)

        mpk = {
            "curve": CURVE,
            "n": n,
            "d": self.d,
            "g": g,
            "g2": g2,
            "g3": g3,
            "g3_2": g3_2,
            "g1": g1_pub,
            "Y1": Y1,
            "Y2": Y2,
            "eta1": eta1,
            "eta2": eta2,
            "eta3": eta3,
            "eta4": eta4,
            "t1": t1,
            "t2": t2,
            "l1": l1,
            "l2": l2,
            "t_coeffs": t_coeffs,
            "l_coeffs": l_coeffs,
        }
        msk = {
            "alpha": alpha,
            "beta": beta,
            "theta1": theta1,
            "theta2": theta2,
            "theta3": theta3,
            "theta4": theta4,
        }
        self._T1_cache.clear()
        self._T2_cache.clear()
        self._H1_cache.clear()
        self._H2_cache.clear()
        return mpk, msk

    def _lagrange_node_set(self, n: int) -> List[int]:
        return list(range(1, n + 2))

    def eval_T_pair(self, x_int: int, mpk: dict) -> Tuple[object, object]:
        n = mpk["n"]
        key = (id(mpk), x_int)
        if key in self._T1_cache:
            return self._T1_cache[key], self._T2_cache[key]
        p = self.order
        N = self._lagrange_node_set(n)
        xpow = pow(x_int, n, p)
        t1x = mpk["g2"] ** xpow
        for i in N:
            delta = lagrange_coeff(i, N, x_int, p)
            if delta:
                t1x *= mpk["t2"][i - 1] ** delta
        t2x = mpk["g"] ** xpow
        for i in N:
            delta = lagrange_coeff(i, N, x_int, p)
            if delta:
                t2x *= mpk["t1"][i - 1] ** delta
        T_G1 = t2x
        T_G2 = t1x
        self._T1_cache[key] = T_G1
        self._T2_cache[key] = T_G2
        return T_G1, T_G2

    def eval_H_pair(self, x_int: int, mpk: dict) -> Tuple[object, object]:
        n = mpk["n"]
        key = (id(mpk), x_int)
        if key in self._H1_cache:
            return self._H1_cache[key], self._H2_cache[key]
        p = self.order
        N = self._lagrange_node_set(n)
        xpow = pow(x_int, n, p)
        H_x = xpow
        l_coeffs = mpk["l_coeffs"]
        for i in N:
            delta = lagrange_coeff(i, N, x_int, p)
            if delta:
                H_x = (H_x + delta * l_coeffs[i - 1]) % p
        H_G1 = mpk["g3"] ** H_x
        H_G2 = mpk["g3_2"] ** H_x
        self._H1_cache[key] = H_G1
        self._H2_cache[key] = H_G2
        return H_G1, H_G2

    def ekgen(self, mpk: dict, msk: dict, S_A: Sequence[str]) -> Tuple[dict, List[int]]:
        p = self.order
        d = self.d
        beta = int(msk["beta"])
        theta1 = int(msk["theta1"])
        theta2 = int(msk["theta2"])
        coeffs_q = random_poly(self.group, d - 1, beta)
        ek = {}
        for a in S_A:
            x = self.attr_to_int(a)
            qx = poly_eval(coeffs_q, x, p)
            r = int(rand_nonzero_zr(self.group))
            H_G1, _ = self.eval_H_pair(x, mpk)
            E_i = (mpk["g3"] ** (qx * theta1 * theta2)) * (H_G1 ** r)
            e_i = mpk["g2"] ** r
            ek[a] = {"E": E_i, "e": e_i}
        return ek, coeffs_q

    def dkgen(self, mpk: dict, msk: dict, S_B: Sequence[str],
              P_A: Sequence[str], q_coeffs: Optional[Sequence[int]] = None) -> dict:
        p = self.order
        d = self.d
        alpha = int(msk["alpha"])
        beta = int(msk["beta"])
        theta1 = int(msk["theta1"])
        theta2 = int(msk["theta2"])
        theta3 = int(msk["theta3"])
        theta4 = int(msk["theta4"])
        G_ID = self.group.init(G2, 1)
        coeffs_f = random_poly(self.group, d - 1, alpha)
        if q_coeffs is None:
            coeffs_qp = random_poly(self.group, d - 1, beta)
        else:
            coeffs_qp = [int(c) % p for c in q_coeffs]
        dk = {"S_B": {}, "P_A": {}, "G_ID": G_ID}

        for b in S_B:
            x = self.attr_to_int(b)
            fb = poly_eval(coeffs_f, x, p)
            k1 = int(rand_nonzero_zr(self.group))
            k2 = int(rand_nonzero_zr(self.group))
            _, T_G2 = self.eval_T_pair(x, mpk)
            dk_b = {
                "i0": mpk["g2"] ** (k1 * theta1 * theta2 + k2 * theta3 * theta4),
                "i1": (power_signed(mpk["g2"], -fb * theta2)
                       * power_signed(T_G2, -k1 * theta2)),
                "i2": (power_signed(mpk["g2"], -fb * theta1)
                       * power_signed(T_G2, -k1 * theta1)),
                "i3": power_signed(T_G2, -k2 * theta4),
                "i4": power_signed(T_G2, -k2 * theta3),
            }
            dk["S_B"][b] = dk_b

        for a in P_A:
            x = self.attr_to_int(a)
            qpa = poly_eval(coeffs_qp, x, p)
            r1 = int(rand_nonzero_zr(self.group))
            r2 = int(rand_nonzero_zr(self.group))
            _, H_G2 = self.eval_H_pair(x, mpk)
            dk_a = {
                "i0": mpk["g2"] ** (r1 * theta1 * theta2 + r2 * theta3 * theta4),
                "i1": (power_signed(mpk["g3_2"], -2 * qpa * theta2)
                       * power_signed(H_G2, -r1 * theta2)),
                "i2": (power_signed(mpk["g3_2"], -2 * qpa * theta1)
                       * power_signed(H_G2, -r1 * theta1)),
                "i3": power_signed(H_G2, -r2 * theta4),
                "i4": power_signed(H_G2, -r2 * theta3),
            }
            dk["P_A"][a] = dk_a
        return dk

    def hash_ct(self, components: Sequence[object]) -> object:
        data = b"".join(self.group.serialize(x, compression=True) for x in components)
        return self.group.hash(data, G1)

    def encrypt(self, mpk: dict, ek: dict, P_B: Sequence[str], M: object,
                S_A: Sequence[str]) -> dict:
        p = self.order
        s = int(rand_nonzero_zr(self.group))
        s1 = int(rand_nonzero_zr(self.group))
        s2 = int(rand_nonzero_zr(self.group))
        tau = int(rand_nonzero_zr(self.group))

        Ks = mpk["Y1"] ** s
        K_l = (mpk["Y2"] ** s) * power_signed(pair(mpk["g3"], mpk["g2"]), -tau)
        self._debug_Ks = Ks
        self._debug_Kl = K_l
        C0 = M * Ks * K_l
        C1 = power_signed(mpk["eta1"], s - s1)
        C2 = power_signed(mpk["eta2"], s1)
        C3 = power_signed(mpk["eta3"], s - s2)
        C4 = power_signed(mpk["eta4"], s2)

        C1_list = {}
        for b in P_B:
            x = self.attr_to_int(b)
            T_G1, _ = self.eval_T_pair(x, mpk)
            C1_list[b] = T_G1 ** s

        C2_list = {}
        C3_list = {}
        C4_list = {}
        C5_list = {}

        for a in S_A:
            x = self.attr_to_int(a)
            H_G1, _ = self.eval_H_pair(x, mpk)
            C2_list[a] = H_G1 ** s

        coeffs_l = random_poly(self.group, self.d - 1, tau)
        for a in S_A:
            x = self.attr_to_int(a)
            H_G1, _ = self.eval_H_pair(x, mpk)
            lx = poly_eval(coeffs_l, x, p)
            E_i = ek[a]["E"]
            e_i = ek[a]["e"]
            xi = int(rand_nonzero_zr(self.group))
            chi = int(rand_nonzero_zr(self.group))
            C3_i = e_i * (mpk["g2"] ** xi)
            C4_i = mpk["g2"] ** chi
            C3_list[a] = C3_i
            C4_list[a] = C4_i

            ct_i_components = [C0, C1, C2, C3, C4,
                               C1_list.get(a), C2_list[a], C3_i, C4_i]
            if ct_i_components[5] is None:
                ct_i_components[5] = self.group.init(G1, 1)
            h1_val = self.hash_ct(ct_i_components)
            C5_i = (E_i ** s) * (mpk["g3"] ** lx) * (H_G1 ** (s * xi)) * (h1_val ** chi)
            C5_list[a] = C5_i

        return {"C0": C0, "C1": C1, "C2": C2, "C3": C3, "C4": C4,
                "C1_list": C1_list, "C2_list": C2_list, "C3_list": C3_list,
                "C4_list": C4_list, "C5_list": C5_list}

    def _decrypt_with_subsets(self, mpk: dict, dk: dict, CT: dict,
                              W_B: Sequence[str], W_A: Sequence[str]) -> object:
        p = self.order
        C0, C1, C2, C3, C4 = CT["C0"], CT["C1"], CT["C2"], CT["C3"], CT["C4"]
        C1_list, C2_list, C3_list, C4_list, C5_list = (
            CT["C1_list"], CT["C2_list"], CT["C3_list"], CT["C4_list"], CT["C5_list"])

        # K'_s
        xB = [self.attr_to_int(b) for b in W_B]
        K_s_prime = self.group.init(GT, 1)
        for b, xb in zip(W_B, xB):
            delta = lagrange_coeff(xb, xB, 0, p)
            db = dk["S_B"][b]
            term_s = (pair(C1_list[b], db["i0"])
                      * pair(C1, db["i1"])
                      * pair(C2, db["i2"])
                      * pair(C3, db["i3"])
                      * pair(C4, db["i4"]))
            K_s_prime *= term_s ** delta

        # K'_l
        xA = [self.attr_to_int(a) for a in W_A]
        K_l_prime = self.group.init(GT, 1)
        for a, xa in zip(W_A, xA):
            delta = lagrange_coeff(xa, xA, 0, p)
            da = dk["P_A"][a]
            c1_i = C1_list.get(a, self.group.init(G1, 1))
            c2_i, c3_i, c4_i, c5_i = C2_list[a], C3_list[a], C4_list[a], C5_list[a]
            ct_i_components = [C0, C1, C2, C3, C4, c1_i, c2_i, c3_i, c4_i]
            h1_val = self.hash_ct(ct_i_components)
            term_l = (pair(c2_i, da["i0"])
                      * pair(C1, da["i1"])
                      * pair(C2, da["i2"])
                      * power_signed(pair(h1_val, c4_i), -1)
                      * power_signed(pair(c2_i, c3_i), -1)
                      * pair(C3, da["i3"])
                      * pair(C4, da["i4"])
                      * pair(c5_i, mpk["g2"]))
            K_l_prime *= term_l ** delta

        result = C0 * K_s_prime * K_l_prime
        self._debug_K_s_prime = K_s_prime
        self._debug_K_l_prime = K_l_prime
        return result

    def decrypt(self, mpk: dict, dk: dict, CT: dict, S_B: Sequence[str],
                P_A: Sequence[str], mode: str = "hint",
                W_A_hint: Optional[Sequence[str]] = None,
                W_B_hint: Optional[Sequence[str]] = None,
                stop_on_first_success: bool = True,
                expected_message: Optional[object] = None):
        d = self.d
        cand_B = [b for b in S_B if b in CT["C1_list"] and b in dk["S_B"]]
        cand_A = [a for a in P_A if a in CT["C2_list"] and a in dk["P_A"]]
        if len(cand_B) < d or len(cand_A) < d:
            return None, 0, None

        if mode == "hint":
            if W_A_hint is None or W_B_hint is None:
                raise ValueError("hint mode requires hints")
            W_A = tuple(W_A_hint)
            W_B = tuple(W_B_hint)
            if len(W_A) != d or len(W_B) != d:
                raise ValueError("hint subset size must equal d")
            m = self._decrypt_with_subsets(mpk, dk, CT, W_B, W_A)
            return m, 1, (W_A, W_B)

        if mode == "aligned":
            W_A = tuple(cand_A[:d])
            W_B = tuple(cand_B[:d])
            m = self._decrypt_with_subsets(mpk, dk, CT, W_B, W_A)
            return m, 1, (W_A, W_B)

        if mode != "enumerate":
            raise ValueError(f"unknown mode: {mode}")

        attempts = 0
        for W_B in itertools.combinations(cand_B, d):
            for W_A in itertools.combinations(cand_A, d):
                attempts += 1
                try:
                    m = self._decrypt_with_subsets(mpk, dk, CT, W_B, W_A)
                    if expected_message is None or m == expected_message:
                        return m, attempts, (tuple(W_A), tuple(W_B))
                except Exception:
                    continue
        return None, attempts, None

    # Serialization methods
    def serialize_element(self, elem: object, compression: bool = True) -> bytes:
        return self.group.serialize(elem, compression=compression)

    def element_size(self, elem: object, compression: bool = True) -> int:
        return len(self.serialize_element(elem, compression=compression))

    def ct_crypto_elements(self, CT: dict) -> List[object]:
        elems = [CT["C0"], CT["C1"], CT["C2"], CT["C3"], CT["C4"]]
        for a in CT["C1_list"]:
            elems.append(CT["C1_list"][a])
        for a in CT["C2_list"]:
            elems.extend([CT["C2_list"][a], CT["C3_list"][a],
                          CT["C4_list"][a], CT["C5_list"][a]])
        return elems

    def ek_crypto_elements(self, ek: dict) -> List[object]:
        out = []
        for item in ek.values():
            out.extend([item["E"], item["e"]])
        return out

    def dk_crypto_elements(self, dk: dict) -> List[object]:
        out = [dk["G_ID"]]
        for item in dk["S_B"].values():
            out.extend([item["i0"], item["i1"], item["i2"], item["i3"], item["i4"]])
        for item in dk["P_A"].values():
            out.extend([item["i0"], item["i1"], item["i2"], item["i3"], item["i4"]])
        return out

    def mpk_crypto_elements(self, mpk: dict) -> List[object]:
        out = [mpk["g1"], mpk["g2"], mpk["g3"], mpk["Y1"], mpk["Y2"],
               mpk["eta1"], mpk["eta2"], mpk["eta3"], mpk["eta4"]]
        out.extend(mpk["t1"])
        out.extend(mpk["t2"])
        out.extend(mpk["l1"])
        out.extend(mpk["l2"])
        return out

    def serialized_size(self, elements: Iterable[object], compression: bool = True) -> int:
        return sum(self.element_size(e, compression) for e in elements)

    def serialize_many(self, elements: Sequence[object], compression: bool = True) -> bytes:
        blob = bytearray()
        for e in elements:
            b = self.serialize_element(e, compression=compression)
            blob.extend(len(b).to_bytes(4, "big"))
            blob.extend(b)
        return bytes(blob)


# ------------------------------------------------------------
# Experimental data generation
# ------------------------------------------------------------
def attrs(prefix: str, n: int) -> List[str]:
    return [f"{prefix}_{i}" for i in range(n)]


def build_fuzzy_instance(n: int, R: int, d: int):
    """Construct a standard test instance, with common attributes placed at the front."""
    if d > n or d > R:
        raise ValueError(f"need n>=d and R>=d, got n={n}, R={R}, d={d}")
    common = attrs("common", d)
    S_A = common + attrs("sa", n - d)
    P_A = common + attrs("pa", R - d)
    S_B = common + attrs("sb", R - d)
    P_B = common + attrs("pb", n - d)
    return S_A, P_B, S_B, P_A


def build_instance_with_overlap(n: int, R: int, d: int, overlap: int):
    """
    Construct an instance with a specified intersection size overlap.
    Returns (S_A, P_B, S_B, P_A) with common attributes placed at random positions
    (to avoid always finding the first combination).
    """
    if overlap < d or overlap > min(n, R):
        raise ValueError("overlap must be >= d and <= min(n,R)")
    common = attrs("common", overlap)
    S_A_base = attrs("sa", n - overlap)
    P_A_base = attrs("pa", R - overlap)
    S_B_base = attrs("sb", R - overlap)
    P_B_base = attrs("pb", n - overlap)

    # Shuffle common positions within the sets (fixed random seed for reproducibility)
    import random
    rng = random.Random(42)
    S_A = S_A_base[:]
    P_A = P_A_base[:]
    S_B = S_B_base[:]
    P_B = P_B_base[:]
    # Insert common randomly into each list
    for attr in common:
        pos = rng.randint(0, len(S_A))
        S_A.insert(pos, attr)
        pos = rng.randint(0, len(P_A))
        P_A.insert(pos, attr)
        pos = rng.randint(0, len(S_B))
        S_B.insert(pos, attr)
        pos = rng.randint(0, len(P_B))
        P_B.insert(pos, attr)
    return S_A, P_B, S_B, P_A


# ------------------------------------------------------------
# ContextCache
# ------------------------------------------------------------
class ContextCache:
    def __init__(self, curve: str = CURVE, d: int = DEFAULT_D):
        self.curve = curve
        self.d = d
        self.group = PairingGroup(curve)
        self.contexts: Dict[Tuple[int, int], Tuple[FuzzyIBME_BN254, dict, dict, float]] = {}

    def get(self, n: int, d: int):
        key = (n, d)
        if key in self.contexts:
            return self.contexts[key]
        me = FuzzyIBME_BN254(self.group, d=d)
        t0 = time.perf_counter_ns()
        mpk, msk = me.setup(n)
        setup_s = (time.perf_counter_ns() - t0) / 1e9
        self.contexts[key] = (me, mpk, msk, setup_s)
        return self.contexts[key]


# ------------------------------------------------------------
# Benchmark recorder
# ------------------------------------------------------------
class CSVRecorder:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write_rows(self, rows: Sequence[dict]):
        if not rows:
            return
        exists = self.path.exists()
        with self.path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            if not exists:
                writer.writeheader()
            writer.writerows(rows)


def benchmark_case(me, mpk, msk, n, R, d, rounds, warmup, decrypt_mode="hint"):
    """Standard benchmark, using build_fuzzy_instance, with correct subset at the front."""
    S_A, P_B, S_B, P_A = build_fuzzy_instance(n, R, d)
    # warm-up
    for _ in range(warmup):
        ek, q_coeffs = me.ekgen(mpk, msk, S_A)
        dk = me.dkgen(mpk, msk, S_B, P_A, q_coeffs=q_coeffs)
        M = me.group.random(GT)
        CT = me.encrypt(mpk, ek, P_B, M, S_A)
        me.decrypt(mpk, dk, CT, S_B, P_A, mode="hint",
                   W_A_hint=P_A[:d], W_B_hint=S_B[:d], expected_message=M)

    ek_times, dk_times, enc_times, dec_times = [], [], [], []
    enc_ser_times, dec_ser_times = [], []
    dec_attempts, ct_sizes, ek_sizes, dk_sizes, mpk_sizes, ct_wire_sizes = [], [], [], [], [], []

    for _ in range(rounds):
        t0 = time.perf_counter_ns()
        ek, q_coeffs = me.ekgen(mpk, msk, S_A)
        ek_times.append((time.perf_counter_ns() - t0) / 1e9)

        t0 = time.perf_counter_ns()
        dk = me.dkgen(mpk, msk, S_B, P_A, q_coeffs=q_coeffs)
        dk_times.append((time.perf_counter_ns() - t0) / 1e9)

        M = me.group.random(GT)

        t0 = time.perf_counter_ns()
        CT = me.encrypt(mpk, ek, P_B, M, S_A)
        enc_times.append((time.perf_counter_ns() - t0) / 1e9)

        ct_elems = me.ct_crypto_elements(CT)
        t0 = time.perf_counter_ns()
        ct_blob = me.serialize_many(ct_elems, compression=True)
        enc_ser_times.append((time.perf_counter_ns() - t0) / 1e9)

        t0 = time.perf_counter_ns()
        recovered, attempts, _ = me.decrypt(mpk, dk, CT, S_B, P_A, mode=decrypt_mode,
                                            W_A_hint=P_A[:d], W_B_hint=S_B[:d],
                                            expected_message=M)
        dec_times.append((time.perf_counter_ns() - t0) / 1e9)
        dec_attempts.append(attempts)

        t0 = time.perf_counter_ns()
        offset = 0
        while offset < len(ct_blob):
            ln = int.from_bytes(ct_blob[offset:offset+4], "big")
            offset += 4
            payload = ct_blob[offset:offset+ln]
            offset += ln
            _ = me.group.deserialize(payload)
        dec_ser_times.append((time.perf_counter_ns() - t0) / 1e9)

        ct_sizes.append(me.serialized_size(ct_elems, compression=True))
        ek_sizes.append(me.serialized_size(me.ek_crypto_elements(ek), compression=True))
        dk_sizes.append(me.serialized_size(me.dk_crypto_elements(dk), compression=True))
        mpk_sizes.append(me.serialized_size(me.mpk_crypto_elements(mpk), compression=True))
        ct_wire_sizes.append(len(ct_blob))

        if recovered != M:
            raise AssertionError(f"decryption failed: n={n}, R={R}, d={d}")

    def avg(vals):
        return mean_or_nan(vals) * 1000.0

    return {
        "curve": CURVE, "n": n, "R": R, "d": d, "rounds": rounds,
        "decrypt_mode": decrypt_mode, "setup_s": float("nan"),
        "ekgen_ms": avg(ek_times), "dkgen_ms": avg(dk_times),
        "enc_ms": avg(enc_times), "dec_ms": avg(dec_times),
        "encode_ct_ms": avg(enc_ser_times), "decode_ct_ms": avg(dec_ser_times),
        "dec_attempts_mean": mean_or_nan(dec_attempts),
        "ct_bytes": mean_or_nan(ct_sizes), "ct_wire_bytes": mean_or_nan(ct_wire_sizes),
        "ek_bytes": mean_or_nan(ek_sizes), "dk_bytes": mean_or_nan(dk_sizes),
        "mpk_bytes": mean_or_nan(mpk_sizes),
        "total_key_material_bytes": mean_or_nan(ek_sizes) + mean_or_nan(dk_sizes),
    }


def benchmark_search_case(me, mpk, msk, n, R, d, overlap, rounds, warmup):
    """Benchmark for a specified overlap, with correct subset shuffled."""
    S_A, P_B, S_B, P_A = build_instance_with_overlap(n, R, d, overlap)
    # warm-up
    for _ in range(warmup):
        ek, q_coeffs = me.ekgen(mpk, msk, S_A)
        dk = me.dkgen(mpk, msk, S_B, P_A, q_coeffs=q_coeffs)
        M = me.group.random(GT)
        CT = me.encrypt(mpk, ek, P_B, M, S_A)
        # Do not perform actual decryption, only complete key and ciphertext generation

    ek, q_coeffs = me.ekgen(mpk, msk, S_A)
    dk = me.dkgen(mpk, msk, S_B, P_A, q_coeffs=q_coeffs)
    M = me.group.random(GT)
    CT = me.encrypt(mpk, ek, P_B, M, S_A)

    search_times = []
    attempts_list = []
    for _ in range(rounds):
        t0 = time.perf_counter_ns()
        recovered, attempts, _ = me.decrypt(mpk, dk, CT, S_B, P_A, mode="enumerate",
                                            expected_message=M)
        search_times.append((time.perf_counter_ns() - t0) / 1e9)
        attempts_list.append(attempts)
        if recovered != M:
            raise RuntimeError("search failed")

    return {
        "curve": CURVE, "n": n, "R": R, "d": d, "overlap": overlap,
        "search_ms": mean_or_nan(search_times) * 1000.0,
        "attempts_mean": mean_or_nan(attempts_list),
    }


# ------------------------------------------------------------
# Correctness tests
# ------------------------------------------------------------
def run_correctness_tests(me, mpk, msk, n, R, d):
    print("\n[TEST] correctness / failure behavior")
    S_A, P_B, S_B, P_A = build_fuzzy_instance(n, R, d)
    ek, q_coeffs = me.ekgen(mpk, msk, S_A)
    dk = me.dkgen(mpk, msk, S_B, P_A, q_coeffs=q_coeffs)
    M = me.group.random(GT)
    CT = me.encrypt(mpk, ek, P_B, M, S_A)

    recovered, attempts, subsets = me.decrypt(mpk, dk, CT, S_B, P_A, mode="hint",
                                              W_A_hint=P_A[:d], W_B_hint=S_B[:d])
    assert recovered == M, "decryption failed"
    print(f"  [PASS] valid decrypt, attempts={attempts}")

    # A-side less than d
    bad_PA = P_A[:d-1] + attrs("badpa", R-(d-1))
    recovered, attempts, _ = me.decrypt(mpk, dk, CT, S_B, bad_PA, mode="enumerate")
    assert recovered is None
    print(f"  [PASS] A-side threshold failure, attempts={attempts}")

    # B-side less than d
    bad_SB = S_B[:d-1] + attrs("badsb", R-(d-1))
    bad_dk = me.dkgen(mpk, msk, bad_SB, P_A, q_coeffs=q_coeffs)
    recovered, attempts, _ = me.decrypt(mpk, bad_dk, CT, bad_SB, P_A, mode="enumerate",
                                        expected_message=M)
    assert recovered is None
    print(f"  [PASS] B-side threshold failure, attempts={attempts}")

    # Tampering
    CT_tampered = dict(CT)
    CT_tampered["C5_list"] = dict(CT["C5_list"])
    victim = S_A[0]
    CT_tampered["C5_list"][victim] = me.group.random(G1)
    recovered, _, _ = me.decrypt(mpk, dk, CT_tampered, S_B, P_A, mode="hint",
                                 W_A_hint=P_A[:d], W_B_hint=S_B[:d])
    assert recovered != M
    print("  [PASS] ciphertext tampering does not recover M")


# ------------------------------------------------------------
# Experiment functions
# ------------------------------------------------------------
def run_exp_n_vs_attributes(cache, n_list, d, rounds, warmup, recorder, decrypt_mode="hint"):
    print("\n=== EXP-A: n varies, R=n, d fixed ===")
    rows = []
    for n in n_list:
        R = n
        me, mpk, msk, setup_s = cache.get(n, d)
        row = benchmark_case(me, mpk, msk, n, R, d, rounds, warmup, decrypt_mode)
        row["setup_s"] = setup_s
        row["experiment"] = "n_vs_attributes"
        rows.append(row)
        print(f"n={n:3d}, R={R:3d}, d={d:2d} | "
              f"EKGen={row['ekgen_ms']:8.2f} ms | "
              f"DKGen={row['dkgen_ms']:8.2f} ms | "
              f"Enc={row['enc_ms']:8.2f} ms | "
              f"Dec={row['dec_ms']:8.2f} ms | "
              f"CT={row['ct_bytes']:7.0f} B")
    recorder.write_rows(rows)


def run_exp_d_vs_threshold(cache, n, d_list, rounds, warmup, recorder, decrypt_mode="hint"):
    print("\n=== EXP-B: d varies, n=R fixed ===")
    rows = []
    R = n
    for d in d_list:
        if d > n:
            continue
        me, mpk, msk, setup_s = cache.get(n, d)
        row = benchmark_case(me, mpk, msk, n, R, d, rounds, warmup, decrypt_mode)
        row["setup_s"] = setup_s
        row["experiment"] = "d_vs_threshold"
        rows.append(row)
        print(f"n={n:3d}, R={R:3d}, d={d:2d} | "
              f"Enc={row['enc_ms']:8.2f} ms | "
              f"Dec={row['dec_ms']:8.2f} ms | "
              f"CT={row['ct_bytes']:7.0f} B")
    recorder.write_rows(rows)


def run_exp_subset_search(cache, n, R, d, overlaps, rounds, warmup, recorder):
    print("\n=== EXP-C: subset search cost vs overlap ===")
    rows = []
    me, mpk, msk, setup_s = cache.get(n, d)
    for overlap in overlaps:
        if overlap < d or overlap > min(n, R):
            continue
        row = benchmark_search_case(me, mpk, msk, n, R, d, overlap, rounds, warmup)
        row["setup_s"] = setup_s
        row["experiment"] = "subset_search"
        rows.append(row)
        print(f"overlap={overlap:3d} | search={row['search_ms']:10.2f} ms | "
              f"attempts={row['attempts_mean']:10.1f}")
    recorder.write_rows(rows)


# ------------------------------------------------------------
# Markdown summary
# ------------------------------------------------------------
def write_summary(path, rows):
    lines = ["# Fuzzy IB-ME BN254 Benchmark Summary", ""]
    lines.append(f"- Curve: `{CURVE}`")
    lines.append("- Implementation: paper Section V-C + BN254 heterogeneous pairing")
    lines.append("")
    if rows:
        header = list(rows[0].keys())
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "---|" * len(header))
        for r in rows:
            vals = []
            for h in header:
                v = r.get(h, "")
                if isinstance(v, float):
                    if math.isnan(v):
                        vals.append("")
                    else:
                        vals.append(f"{v:.3f}")
                else:
                    vals.append(str(v))
            lines.append("| " + " | ".join(vals) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------
def parse_int_list(text):
    return [int(x.strip()) for x in text.split(",") if x.strip()]


def main():
    parser = argparse.ArgumentParser(description="Fuzzy IB-ME BN254 benchmark (Fig.2 aligned)")
    parser.add_argument("--rounds", type=int, default=config.ROUNDS)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--d", type=int, default=config.DEFAULT_D)
    parser.add_argument("--out", type=str, default=DEFAULT_OUT)
    parser.add_argument("--n-list", type=str, default="5,10,15,20,25,30,35,40")
    parser.add_argument("--d-list", type=str, default="2,3,4,5,6,7,8")
    parser.add_argument("--overlap-list", type=str, default="5,7,10,15,20,25")
    parser.add_argument("--n-fixed", type=int, default=25)
    parser.add_argument("--R-fixed", type=int, default=25)
    parser.add_argument("--decrypt-mode", choices=["hint", "enumerate"], default="hint")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--skip-exp-n", action="store_true")
    parser.add_argument("--skip-exp-d", action="store_true")
    parser.add_argument("--skip-exp-search", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "benchmark.csv"
    summary_path = out_dir / "summary.md"
    if csv_path.exists():
        csv_path.unlink()
    recorder = CSVRecorder(csv_path)

    cache = ContextCache(curve=CURVE, d=args.d)

    print(f"[INFO] curve = {CURVE}")
    print(f"[INFO] group order bits = {int(cache.group.order()).bit_length()}")
    print(f"[INFO] rounds = {args.rounds}, warmup = {args.warmup}")
    print(f"[INFO] output = {out_dir.resolve()}")

    if not args.skip_tests:
        n_test = max(args.n_fixed, args.d + 2)
        R_test = max(args.R_fixed, args.d + 2)
        me, mpk, msk, setup_s = cache.get(n_test, args.d)
        run_correctness_tests(me, mpk, msk, n_test, R_test, args.d)
        print(f"[TEST] setup({n_test}) = {setup_s*1000:.3f} ms")

    all_rows = []
    if not args.skip_exp_n:
        run_exp_n_vs_attributes(cache, parse_int_list(args.n_list), args.d,
                                args.rounds, args.warmup, recorder, args.decrypt_mode)

    if not args.skip_exp_d:
        run_exp_d_vs_threshold(cache, args.n_fixed, parse_int_list(args.d_list),
                               args.rounds, args.warmup, recorder, args.decrypt_mode)

    if not args.skip_exp_search:
        run_exp_subset_search(cache, args.n_fixed, args.R_fixed, args.d,
                              parse_int_list(args.overlap_list),
                              args.rounds, args.warmup, recorder)

    if csv_path.exists():
        with csv_path.open("r", newline="", encoding="utf-8") as f:
            all_rows = list(csv.DictReader(f))
    write_summary(summary_path, all_rows)

    print("\n[DONE]")
    print(f"  CSV     : {csv_path}")
    print(f"  Summary : {summary_path}")


if __name__ == "__main__":
    main()