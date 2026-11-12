#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Dependency-free tests for candidate enumeration (C3)."""

import os
import sys
from itertools import combinations

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from search import candidate_subsets, enumerate_with_budget


def test_lex_matches_itertools():
    for A, d in [(6, 2), (7, 3), (10, 4)]:
        assert list(candidate_subsets(A, d, order="lex")) == list(
            combinations(range(A), d)
        )


def test_prh_is_a_permutation_of_the_same_subsets():
    A, d = 8, 3
    lex = list(candidate_subsets(A, d, order="lex"))
    prh = list(candidate_subsets(A, d, order="prh", seed=12345))
    assert len(prh) == len(lex) == 56
    assert sorted(prh) == sorted(lex)
    assert len(set(prh)) == len(prh), "each subset exactly once"


def test_prh_depends_on_seed_and_is_deterministic():
    a = list(candidate_subsets(9, 3, order="prh", seed=1))
    b = list(candidate_subsets(9, 3, order="prh", seed=1))
    c = list(candidate_subsets(9, 3, order="prh", seed=2))
    assert a == b
    assert a != c
    # The first candidate must not simply track index magnitude.
    assert a[0] != min(a)


def test_hint_yields_exactly_one_candidate():
    got = list(candidate_subsets(10, 3, order="prh", hint=[7, 1, 4]))
    assert got == [(1, 4, 7)]


def test_invalid_hint_is_rejected():
    with pytest.raises(ValueError):
        list(candidate_subsets(10, 3, hint=[1, 2]))
    with pytest.raises(ValueError):
        list(candidate_subsets(10, 3, hint=[1, 1, 2]))
    with pytest.raises(ValueError):
        list(candidate_subsets(10, 3, hint=[1, 2, 99]))


def test_budget_truncates_and_reports_exhaustion():
    subsets, exhausted = enumerate_with_budget(12, 3, budget=5, order="prh", seed=3)
    assert len(subsets) == 5 and exhausted
    subsets, exhausted = enumerate_with_budget(6, 2, budget=100, order="lex")
    assert len(subsets) == 15 and not exhausted


def test_threshold_above_attribute_count_yields_nothing():
    assert list(candidate_subsets(3, 5)) == []
