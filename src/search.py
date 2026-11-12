#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Candidate d-subset enumeration for threshold reconstruction.

Three callers exist and they must not be confused:

  order='lex'  -- lexicographic order.  Reproducible baseline, but the
                  position of the correct subset correlates with which
                  indices match, so latency leaks the intersection pattern.
  order='prh'  -- pseudo-random order induced by H_s(salt || C).  This is
                  the default used by the protocol and by the paper.
  hint=...     -- a single candidate supplied out of band.  This exists so
                  that benchmarks can isolate reconstruction cost.  It must
                  be an explicit argument; producing a "hint" by permuting
                  the attribute list is not allowed (it silently changes
                  what is being measured).

`budget` bounds the number of candidates tried; exhausting it is reported
as a failure, never as a success.
"""

from itertools import combinations

import hashdom


def candidate_subsets(A, d, order="prh", seed=0, hint=None):
    """Yield index tuples of size d from range(A), in the requested order.

    Args:
        A:     number of attributes held by the receiver.
        d:     threshold.
        order: 'prh' (default) or 'lex'.
        seed:  integer seed for the pseudo-random order.
        hint:  optional explicit candidate (iterable of indices).
    """
    if d <= 0:
        raise ValueError("threshold must be positive")
    if d > A:
        return

    if hint is not None:
        candidate = tuple(sorted(int(i) for i in hint))
        if len(candidate) != d:
            raise ValueError("hint has %d indices, expected %d" % (len(candidate), d))
        if len(set(candidate)) != d:
            raise ValueError("hint contains repeated indices")
        if candidate[0] < 0 or candidate[-1] >= A:
            raise ValueError("hint index out of range")
        yield candidate
        return

    if order == "lex":
        for subset in combinations(range(A), d):
            yield subset
        return

    if order == "prh":
        labels = hashdom.permuted_indices(A, seed)
        for subset in combinations(labels, d):
            # Sorting keeps the subset canonical for indexing into Z/xs;
            # the enumeration order across subsets is what H_s controls.
            yield tuple(sorted(subset))
        return

    raise ValueError("unknown order: %r" % (order,))


def enumerate_with_budget(A, d, budget=None, **kwargs):
    """Return (subsets, exhausted) trying at most `budget` candidates."""
    subsets = []
    for subset in candidate_subsets(A, d, **kwargs):
        if budget is not None and len(subsets) >= budget:
            return subsets, True
        subsets.append(subset)
    return subsets, False
