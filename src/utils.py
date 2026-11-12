#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Utility functions: timing, statistics, CSV output."""

import csv
import time
import statistics
import os

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from charm.toolbox.pairinggroup import ZR, G1, G2, GT, pair

def now():
    return time.perf_counter()

def process_time():
    return time.process_time()

def get_memory_usage_kb():
    if HAS_PSUTIL:
        p = psutil.Process(os.getpid())
        return p.memory_info().rss // 1024
    return 0

def modinv(a, p):
    a = int(a) % p
    if a == 0:
        raise ZeroDivisionError("inverse of zero")
    return pow(a, p - 2, p)

def xor_bytes(a, b):
    assert len(a) == len(b)
    return bytes(x ^ y for x, y in zip(a, b))

def hash_to_nonzero_zr(group, label):
    x = group.hash(label, ZR)
    if int(x) == 0:
        x = group.hash(label + "#", ZR)
    return x

import hashlib
import secrets

def ro_hash_bytes(group, domain, element):
    """Domain-separated hash to bytes for H_K and H_V."""
    raw = group.serialize(element)
    h = hashlib.sha256()
    h.update(domain)
    h.update(b'|')
    h.update(raw)
    return h.digest()

def random_bytes(n=32):
    return secrets.token_bytes(n)

def write_csv(filename, fieldnames, rows):
    """Write list of dicts to CSV."""
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

def print_summary(name, values, unit='ms'):
    """Print mean, std, min, max for a list of measurements."""
    if not values:
        print(f"{name}: no data")
        return
    mean = statistics.mean(values)
    stdev = statistics.stdev(values) if len(values) > 1 else 0.0
    mn = min(values)
    mx = max(values)
    print(f"{name:30s}: mean={mean:10.3f} {unit}  "
          f"std={stdev:8.3f} {unit}  min={mn:8.3f} {unit}  max={mx:8.3f} {unit}")

def measure_operation(func, *args, **kwargs):
    mem_before = get_memory_usage_kb()
    wall_start = now()
    cpu_start = process_time()

    result = func(*args, **kwargs)

    wall_end = now()
    cpu_end = process_time()
    mem_after = get_memory_usage_kb()

    wall_ms = (wall_end - wall_start) * 1000
    cpu_ms = (cpu_end - cpu_start) * 1000
    mem_kb = max(0, mem_after - mem_before) 

    return result, wall_ms, cpu_ms, mem_kb