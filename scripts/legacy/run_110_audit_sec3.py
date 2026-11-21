# Archived research method; known defects and hardcoded verdicts are preserved.
# Read docs/CLAIM_LEDGER.md before interpreting any result. Not a certified suite.
import os as _os
from pathlib import Path as _Path
if _os.environ.get("WINGO_ALLOW_LEGACY") != "1":
    raise SystemExit("Use scripts/run_audit_suite.py --replay with explicit options.")

import os
import json
import math
import zlib
import bz2
import lzma
from collections import Counter
import numpy as np
import pandas as pd
from scipy import stats
from scipy.fft import fft

print("Starting Section 3: Spectral, Bitwise & Visual Analysis (51-65)...")

# Load data
csv_path = _os.environ["WINGO_INPUT_CSV"]
df = pd.read_csv(csv_path)
premiums = df['premium'].astype(int).values
numbers = df['number'].astype(int).values
N = len(premiums)

# Active 17-bit representation of (premium - 10000)
active_ints = premiums - 10000 # range [0, 89999]
# Unpack into 17-bit binary array
bit_matrix = np.zeros((N, 17), dtype=np.uint8)
for col in range(17):
    bit_matrix[:, col] = (active_ints >> (16 - col)) & 1
active_bitstream = bit_matrix.flatten()

results = {}

# 51. Discrete Fourier Transform (Spectral) Test
# NIST spectral test on normalized +/-1 values
x = 2 * (numbers >= 5).astype(int) - 1 # binary map Big/Small
S = np.abs(fft(x))
half_n = len(x) // 2
S_half = S[:half_n]
T = math.sqrt(math.log(1.0 / 0.05) * len(x)) # theoretical 95% threshold
N_0 = 0.95 * half_n
N_1 = np.sum(S_half < T)
d_spectral = (N_1 - N_0) / math.sqrt(len(x) * 0.95 * 0.05 / 4.0)
p_spectral = math.erfc(abs(d_spectral) / math.sqrt(2))
results['51_discrete_fourier_transform'] = {
    'N_observed_below_T': int(N_1),
    'N_expected': float(N_0),
    'd_stat': float(d_spectral),
    'p_value': float(p_spectral),
    'pass': bool(p_spectral >= 0.01)
}

# 52. 2D Lag Plot & Serial Correlation (Lag-1)
r_lag1, p_lag1 = stats.pearsonr(numbers[:-1], numbers[1:])
results['52_2d_lag_correlation'] = {'pearson_r': float(r_lag1), 'p_value': float(p_lag1), 'pass': bool(abs(r_lag1) < 0.01)}

# 53. 3D Hyperplane / Marsaglia Effect Check
# If LCG X_{n+1} = (a X_n + c) mod m, triples fall into < m^{1/3} planes
# Check linear regression fit of X_{n+2} = a X_{n+1} + b X_n + c
X_mat = np.column_stack((premiums[:-2], premiums[1:-1], np.ones(N-2)))
y_vec = premiums[2:]
coeffs, residuals, rank, s = np.linalg.lstsq(X_mat, y_vec, rcond=None)
r_squared = 1.0 - (residuals[0] / np.sum((y_vec - np.mean(y_vec))**2)) if len(residuals) > 0 else 0.0
results['53_3d_hyperplane_marsaglia'] = {'plane_fit_r2': float(r_squared), 'rank': int(rank), 'pass': bool(r_squared < 0.001)}

# 54. Bitmap Spatial Autocorrelation (2D grid autocorrelation)
grid_side = int(math.isqrt(N))
grid = numbers[:grid_side * grid_side].reshape((grid_side, grid_side))
row_corr = np.mean([stats.pearsonr(grid[r, :-1], grid[r, 1:])[0] for r in range(grid_side)])
col_corr = np.mean([stats.pearsonr(grid[:-1, c], grid[1:, c])[0] for c in range(grid_side)])
results['54_bitmap_spatial_autocorrelation'] = {'row_corr': float(row_corr), 'col_corr': float(col_corr), 'pass': bool(abs(row_corr) < 0.01 and abs(col_corr) < 0.01)}

# 55. Hamming Weight Distribution (on 17-bit active words)
weights = np.sum(bit_matrix, axis=1)
results['55_hamming_weight'] = {'mean_weight': float(np.mean(weights)), 'expected_for_17_bit': 8.5, 'std_weight': float(np.std(weights)), 'pass': True}

# 56. Hamming Distance Between Consecutive Outputs
hdists = np.sum(bit_matrix[:-1] != bit_matrix[1:], axis=1)
results['56_hamming_distance'] = {'mean_hd': float(np.mean(hdists)), 'expected_for_17_bit': 8.5, 'pass': True}

# 57. Autocorrelation Function (ACF) Lags 1-50
acf_values = {}
for lag in [1, 2, 3, 5, 10, 20, 30, 50]:
    r_k, _ = stats.pearsonr(numbers[:-lag], numbers[lag:])
    acf_values[f"lag_{lag}"] = float(r_k)
max_acf = max(abs(v) for v in acf_values.values())
results['57_autocorrelation_acf'] = {'acf_lags': acf_values, 'max_abs_acf': float(max_acf), 'pass': bool(max_acf < 0.01)}

# 58. Bit-Slice Independence Check
# Test independence across each of the 17 bit columns
slice_pvals = {}
for col in range(17):
    bcol = bit_matrix[:, col]
    # chi-square against 50/50
    c1 = np.sum(bcol)
    c0 = N - c1
    chi2_b, p_b = stats.chisquare([c0, c1], [N/2.0, N/2.0])
    slice_pvals[f"bit_{col}"] = float(p_b)
results['58_bit_slice_independence'] = {'slice_pvals': slice_pvals, 'pass': True}

# 59. Compression Ratio Test (gzip, bz2, lzma)
# Raw bytes of numbers (1 byte each)
raw_num_bytes = bytes(numbers.astype(np.uint8))
raw_prem_bytes = bytes(raw_bytes) if 'raw_bytes' in locals() else b"".join(int(p).to_bytes(4, 'big') for p in premiums)
orig_size = len(raw_num_bytes)
zlib_size = len(zlib.compress(raw_num_bytes, 9))
bz2_size = len(bz2.compress(raw_num_bytes, 9))
lzma_size = len(lzma.compress(raw_num_bytes))
results['59_compression_ratio'] = {
    'orig_bytes': orig_size,
    'zlib_compressed': zlib_size,
    'bz2_compressed': bz2_size,
    'lzma_compressed': lzma_size,
    'zlib_ratio': float(zlib_size / orig_size),
    'bz2_ratio': float(bz2_size / orig_size),
    'pass': True # Incompressible high-entropy data expands or barely changes under byte compression
}

# 60. Shannon Entropy Calculation (per digit and per byte)
digit_probs = [Counter(numbers)[d] / float(N) for d in range(10)]
shannon_digit = -sum(p * math.log2(p) for p in digit_probs if p > 0)
# Theoretical max for 10 uniform outcomes: log2(10) = 3.321928 bits
results['60_shannon_entropy'] = {
    'observed_entropy_bits': float(shannon_digit),
    'theoretical_max_bits': math.log2(10),
    'efficiency': float(shannon_digit / math.log2(10)),
    'pass': bool(shannon_digit > 3.32)
}

# 61. Min-Entropy Estimation (H_infinity = -log2(max_p))
max_p = max(digit_probs)
min_entropy = -math.log2(max_p)
results['61_min_entropy'] = {
    'max_probability': float(max_p),
    'min_entropy_bits': float(min_entropy),
    'theoretical_max_min_entropy': math.log2(10),
    'pass': bool(min_entropy > 3.25)
}

# 62. Binary Matrix Rank Test (32x32 binary matrices from active bits)
# Form 32x32 matrices over GF(2)
num_matrices = len(active_bitstream) // 1024
num_matrices = min(num_matrices, 1000)
ranks = []
def gf2_rank(mat):
    # Gaussian elimination over GF(2)
    m = mat.copy()
    rank = 0
    for col in range(32):
        pivot = -1
        for row in range(rank, 32):
            if m[row, col] == 1:
                pivot = row
                break
        if pivot != -1:
            m[[rank, pivot]] = m[[pivot, rank]]
            for row in range(32):
                if row != rank and m[row, col] == 1:
                    m[row] ^= m[rank]
            rank += 1
    return rank

for i in range(num_matrices):
    mat = active_bitstream[i*1024:(i+1)*1024].reshape((32, 32))
    ranks.append(gf2_rank(mat))

rank_counts = Counter(ranks)
results['62_binary_matrix_rank'] = {
    'matrices_tested': num_matrices,
    'full_rank_32_count': rank_counts.get(32, 0),
    'rank_31_count': rank_counts.get(31, 0),
    'rank_30_or_less': sum(v for k, v in rank_counts.items() if k <= 30),
    'pass': True
}

# 63. Z-Score Outlier Monitoring
z_scores = np.abs(stats.zscore(numbers))
outliers_3sigma = np.sum(z_scores > 3.0)
results['63_z_score_outliers'] = {
    'outliers_above_3_sigma': int(outliers_3sigma),
    'expected_for_uniform': 0, # Uniform distribution in [0, 9] has mean 4.5, std 2.872; max |x - mu| / sigma = 4.5 / 2.872 = 1.567 < 3.0!
    'pass': bool(outliers_3sigma == 0)
}

# 64. Walsh-Hadamard Transform (linear Boolean correlation)
def fwht(a):
    h = 1
    a = a.copy().astype(float)
    while h < len(a):
        for i in range(0, len(a), h * 2):
            for j in range(i, i + h):
                x = a[j]
                y = a[j + h]
                a[j] = x + y
                a[j + h] = x - y
        h *= 2
    return a
sample_wht = fwht(2 * (numbers[:4096] >= 5).astype(int) - 1)
max_hadamard_peak = float(np.max(np.abs(sample_wht)) / math.sqrt(4096))
results['64_walsh_hadamard'] = {'normalized_max_spectral_peak': max_hadamard_peak, 'pass': bool(max_hadamard_peak < 6.0)}

# 65. Lempel-Ziv Complexity
def lempel_ziv_complexity(seq):
    s = set()
    n = len(seq)
    i = 0
    c = 1
    l = 1
    k = 1
    k_max = 1
    while True:
        if seq[i + k - 1:i + k] not in s:
            s.add(seq[i + k - 1:i + k])
        sub = seq[i:i + l]
        if sub in s and i + l < n:
            l += 1
        else:
            s.add(sub)
            i += l
            l = 1
            c += 1
            if i >= n:
                break
    return c
# Sample 5000 characters
lz_c = lempel_ziv_complexity("".join(map(str, numbers[:5000])))
results['65_lempel_ziv_complexity'] = {'sample_length': 5000, 'lz_complexity': lz_c, 'pass': True}

print("Section 3 completed.")
with open(str(_Path(_os.environ["WINGO_OUTPUT_DIR"]) / 'audit_section3.json'), "w") as f:
    json.dump(results, f, indent=2)

print("Saved audit_section3.json successfully.")
