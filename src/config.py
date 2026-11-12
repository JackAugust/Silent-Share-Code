#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Global configuration for Silent-Share benchmarks."""

# CURVE = 'SS512'
CURVE = 'BN254'

DEFAULT_D = 5

# ------------------------------------------------------------
# GOKVS instantiation
# ------------------------------------------------------------
USE_SPARSE_GOKVS = True
SPARSE_GOKVS_RHO = 3
SPARSE_GOKVS_M_FACTOR = 1.25
SPARSE_GOKVS_MAX_ATTEMPTS = 20

# ------------------------------------------------------------
# Unified extended policy sizes
# Applicable to all tests that expect a unified dimension
# ------------------------------------------------------------
EXTENDED_POLICY_SIZES = [10, 25, 50, 100, 200, 400, 800, 1600]

# Default policy sizes
POLICY_SIZES = [50, 100, 200, 400, 800]
# POLICY_SIZES = [50, 100]

# Bilateral tests can be configured separately; if consistency with the global
# configuration is desired, EXTENDED_POLICY_SIZES can be used directly.
BILATERAL_POLICY_SIZES = EXTENDED_POLICY_SIZES

# Attribute counts
ATTR_SIZES = [5, 10, 15, 20, 25, 30, 35, 40]
# ATTR_SIZES = [2,4,6,8,10]
# Thresholds
THRESHOLDS = [2, 3, 4, 5]
ATTR_SIZES_RECON = [5, 10, 15, 20, 25, 30, 35, 40]
THRESHOLDS_RECON = [2, 4, 6, 8, 10]

# Number of repetitions
ROUNDS = 5

LAMBDA_BYTES = 32

# Parallelism
PARALLEL_WORKERS = 4  # or 4

# ------------------------------------------------------------
# Unified configuration for the comparison experiments (Fuzzy IB-ME vs
# Silent-Share); the drivers in experiments/ read these values by default.
# ------------------------------------------------------------
# Experiment A: attribute size n varies, R=n, d fixed
COMPARE_EXP_A_N_LIST = ATTR_SIZES
COMPARE_EXP_A_D = DEFAULT_D

# Experiment B: threshold d varies, fixed n=R=30
COMPARE_EXP_B_N_FIXED = 30
COMPARE_EXP_B_D_LIST = THRESHOLDS_RECON

# Experiment C: subset search complexity, fixed n=R=30, d=5
COMPARE_EXP_C_N_FIXED = 30
COMPARE_EXP_C_R_FIXED = 30
COMPARE_EXP_C_D = DEFAULT_D
COMPARE_EXP_C_OVERLAP_LIST = ATTR_SIZES_RECON

# Experiment D: online decryption vs policy size, fixed user attribute count, d=5
COMPARE_EXP_D_USER_ATTR_SIZE = 30   # Number of attributes held by the user, fixed
COMPARE_EXP_D_D = DEFAULT_D
COMPARE_EXP_D_POLICY_SIZE_LIST = POLICY_SIZES  # Policy size varies

# Whether to enable Monte Carlo simulation (used only by the Fuzzy script)
COMPARE_MONTE_CARLO = True
# Whether to use paper-style H(x) evaluation (used only by the Fuzzy script, recommended True)
COMPARE_FAITHFUL_H = True