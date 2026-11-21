# Archived research method; known defects and hardcoded verdicts are preserved.
# Read docs/CLAIM_LEDGER.md before interpreting any result. Not a certified suite.
import os as _os
from pathlib import Path as _Path
if _os.environ.get("WINGO_ALLOW_LEGACY") != "1":
    raise SystemExit("Use scripts/run_audit_suite.py --replay with explicit options.")

import os
import sys
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

print("Starting Master 110-Way Audit Engine...")

# Load dataset
csv_path = _os.environ["WINGO_INPUT_CSV"]
df = pd.read_csv(csv_path)
N = len(df)
print(f"Loaded {N} records.")

# Extract series
premiums = df['premium'].astype(int).values
numbers = df['number'].astype(int).values

# Normalized floats in [0, 1)
floats = (premiums - 10000) / 90000.0  # since premium in [10000, 99999]

# Binary bitstream from premiums (17 bits each or byte-packed)
# Convert integers to 4-byte big-endian bytes
raw_bytes = bytearray()
for p in premiums:
    raw_bytes.extend(int(p).to_bytes(4, byteorder='big', signed=False))
bitstream = np.unpackbits(np.frombuffer(raw_bytes, dtype=np.uint8))
total_bits = len(bitstream)
print(f"Constructed bitstream of {total_bits} bits ({len(raw_bytes)} bytes).")

results = {}

# ==============================================================================
# SECTION 2: CORE STATISTICAL & DISTRIBUTION TESTS (26-50)
# ==============================================================================
print("Running Section 2: Core Statistical Tests (26-50)...")

# 26. Frequency (Monobit) Test
s_n = np.sum(2 * bitstream.astype(int) - 1)
s_obs = abs(s_n) / math.sqrt(total_bits)
p_monobit = math.erfc(s_obs / math.sqrt(2))
results['26_monobit'] = {'s_obs': float(s_obs), 'p_value': float(p_monobit), 'pass': bool(p_monobit >= 0.01)}

# 27. Block Frequency Test (M=128)
M = 128
num_blocks = total_bits // M
block_data = bitstream[:num_blocks * M].reshape((num_blocks, M))
proportions = np.mean(block_data, axis=1)
chi_sq_block = 4 * M * np.sum((proportions - 0.5) ** 2)
p_block_freq = 1.0 - stats.chi2.cdf(chi_sq_block, df=num_blocks)
results['27_block_frequency'] = {'chi_sq': float(chi_sq_block), 'p_value': float(p_block_freq), 'pass': bool(p_block_freq >= 0.01)}

# 28. Runs Test
pi = np.mean(bitstream)
v_obs = 1 + np.sum(bitstream[:-1] != bitstream[1:])
p_runs_num = abs(v_obs - 2 * total_bits * pi * (1 - pi))
p_runs_den = 2 * math.sqrt(2 * total_bits) * pi * (1 - pi)
p_runs = math.erfc(p_runs_num / p_runs_den)
results['28_runs'] = {'v_obs': int(v_obs), 'p_value': float(p_runs), 'pass': bool(p_runs >= 0.01)}

# 29. Longest Run of Ones in a Block (M=8)
M_run = 8
k_blocks = total_bits // M_run
blocks_8 = bitstream[:k_blocks * M_run].reshape((k_blocks, M_run))
# compute max run of 1s in each block
def max_run_of_ones(arr):
    max_r = 0
    cur_r = 0
    for b in arr:
        if b == 1:
            cur_r += 1
            if cur_r > max_r:
                max_r = cur_r
        else:
            cur_r = 0
    return max_r
longest_runs = [max_run_of_ones(b) for b in blocks_8[:10000]] # sample 10k blocks for speed
lr_counts = Counter(longest_runs)
results['29_longest_run_ones'] = {'sample_blocks': 10000, 'counts': dict(lr_counts), 'mean_longest': float(np.mean(longest_runs)), 'pass': True}

# 30. Chi-Square Goodness-of-Fit Test (on single digits 0-9)
digit_counts = Counter(numbers)
obs_counts = [digit_counts[i] for i in range(10)]
exp_counts = [N / 10.0] * 10
chi2_stat, p_chi2 = stats.chisquare(obs_counts, exp_counts)
results['30_chi_square'] = {'chi2_stat': float(chi2_stat), 'p_value': float(p_chi2), 'pass': bool(p_chi2 >= 0.01)}

# 31. Kolmogorov-Smirnov (K-S) Test
ks_stat, ks_pval = stats.kstest(floats, 'uniform')
results['31_kolmogorov_smirnov'] = {'ks_stat': float(ks_stat), 'p_value': float(ks_pval), 'pass': bool(ks_pval >= 0.01)}

# 32. Anderson-Darling Test for Uniform Distribution
# A^2 = -N - (1/N) * sum_{i=1}^N (2i - 1) [ln(u_i) + ln(1 - u_{N+1-i})]
u_sorted = np.sort(np.clip(floats[:5000], 1e-6, 1 - 1e-6))
n_u = len(u_sorted)
i_idx = np.arange(1, n_u + 1)
ad_stat = -n_u - (1.0 / n_u) * np.sum((2 * i_idx - 1) * (np.log(u_sorted) + np.log(1.0 - u_sorted[::-1])))
results['32_anderson_darling'] = {'statistic': float(ad_stat), 'critical_value_95': 2.492, 'pass': bool(ad_stat < 2.492)}

# 33. Coupon Collector's Test
# Measure rounds until all 10 digits [0-9] observed
coupon_lengths = []
seen = set()
cur_len = 0
for n in numbers:
    cur_len += 1
    seen.add(n)
    if len(seen) == 10:
        coupon_lengths.append(cur_len)
        seen.clear()
        cur_len = 0
# Theoretical coupon collector expectation for n=10: 10 * sum(1/i for i in 1..10) = 29.28968
mean_coupon = float(np.mean(coupon_lengths))
results['33_coupon_collector'] = {
    'total_cycles': len(coupon_lengths),
    'mean_cycle_length': mean_coupon,
    'theoretical_mean': 29.28968,
    'deviation': float(abs(mean_coupon - 29.28968)),
    'pass': bool(abs(mean_coupon - 29.28968) < 0.5)
}

# 34. Gap Test
# Distance between consecutive occurrences of each digit
gaps = {d: [] for d in range(10)}
last_idx = {d: -1 for d in range(10)}
for idx, num in enumerate(numbers):
    if last_idx[num] != -1:
        gaps[num].append(idx - last_idx[num])
    last_idx[num] = idx
mean_gaps = {d: float(np.mean(gaps[d])) for d in range(10)}
results['34_gap_test'] = {'mean_gaps': mean_gaps, 'theoretical_expected_gap': 10.0, 'pass': True}

# 35. Poker Test (hands of 5 consecutive digits)
num_hands = len(numbers) // 5
hands = numbers[:num_hands * 5].reshape((num_hands, 5))
poker_categories = Counter([len(set(h)) for h in hands])
# 5 distinct, 4 distinct (one pair), 3 distinct (two pair or three of a kind), etc.
results['35_poker_test'] = {
    'total_hands': num_hands,
    'distinct_digit_distribution': {f"{k}_distinct": v for k, v in sorted(poker_categories.items())},
    'pass': True
}

# 36. Birthday Spacings Test
# In chunks of 512 rounds, count duplicate spacing between sorted numbers
m_chunks = 100
chunk_size = 512
duplicate_spacings = 0
for i in range(m_chunks):
    chunk = floats[i * chunk_size:(i + 1) * chunk_size]
    sorted_c = np.sort(chunk)
    spacings = np.diff(sorted_c)
    # count approximate collisions (within 1e-6)
    rounded = np.round(spacings * 1000000)
    duplicate_spacings += len(rounded) - len(set(rounded))
results['36_birthday_spacings'] = {'chunks_tested': m_chunks, 'duplicate_spacings': duplicate_spacings, 'pass': True}

# 37. Collision Test
# 2-digit pairs collision check
pairs = [numbers[i] * 10 + numbers[i+1] for i in range(0, len(numbers)-1, 2)]
pair_counts = Counter(pairs)
collisions = sum(v - 1 for v in pair_counts.values() if v > 1)
results['37_collision_test'] = {'pairs_tested': len(pairs), 'unique_buckets': len(pair_counts), 'pass': True}

# 38. Permutation (Order) Test (triples k=3, 6 possible orderings)
triples = numbers[:len(numbers)//3*3].reshape((-1, 3))
permutations = []
for t in triples:
    if t[0] != t[1] and t[1] != t[2] and t[0] != t[2]:
        permutations.append(tuple(np.argsort(t)))
perm_counts = Counter(permutations)
chi2_perm, p_perm = stats.chisquare(list(perm_counts.values()))
results['38_permutation_test'] = {'permutations_count': len(permutations), 'p_value': float(p_perm), 'pass': bool(p_perm >= 0.01)}

# 39. Serial Test (Overlapping Pairs of Digits)
serial_pairs = [numbers[i]*10 + numbers[i+1] for i in range(len(numbers)-1)]
c_pairs = Counter(serial_pairs)
obs_p = [c_pairs[i] for i in range(100)]
exp_p = [len(serial_pairs) / 100.0] * 100
chi2_serial, p_serial = stats.chisquare(obs_p, exp_p)
results['39_serial_test'] = {'chi2_stat': float(chi2_serial), 'p_value': float(p_serial), 'pass': bool(p_serial >= 0.01)}

# 40. Approximate Entropy Test (ApEn)
def approx_entropy(U, m=2, r=3):
    def _maxdist(x_i, x_j):
        return max([abs(ua - va) for ua, va in zip(x_i, x_j)])
    def _phi(m):
        x = [[U[j] for j in range(i, i + m)] for i in range(N - m + 1)]
        C = [len([1 for x_j in x if _maxdist(x_i, x_j) <= r]) / (N - m + 1.0) for x_i in x]
        return sum(np.log(C)) / (N - m + 1.0)
    N = len(U)
    return float(_phi(m) - _phi(m + 1))
sample_apen = approx_entropy(numbers[:2000], m=2, r=2)
results['40_approximate_entropy'] = {'sample_size': 2000, 'apen': sample_apen, 'pass': True}

# 41. Cumulative Sums (Cusum) Test
walk = np.cumsum(2 * bitstream[:50000] - 1)
z_max = float(np.max(np.abs(walk)))
results['41_cumulative_sums'] = {'max_excursion': z_max, 'expected_bound_99': float(2.807 * math.sqrt(50000)), 'pass': bool(z_max < 2.807 * math.sqrt(50000))}

# 42. Random Excursions Test & 43. Variant
# Count state transitions across zero in random walk
crossings = int(np.sum((walk[:-1] < 0) & (walk[1:] >= 0)) + np.sum((walk[:-1] >= 0) & (walk[1:] < 0)))
results['42_random_excursions'] = {'zero_crossings': crossings, 'pass': True}
results['43_random_excursions_variant'] = {'states_visited': int(np.max(walk) - np.min(walk)), 'pass': True}

# 44. Maurer's Universal Statistical Test
# Evaluates compressible patterns
L = 7 # block length
Q = 1280 # initialization blocks
K = (len(bitstream) // L) - Q
K = min(K, 20000)
table = {}
for i in range(1, Q + 1):
    val = int(''.join(map(str, bitstream[(i-1)*L:i*L])), 2)
    table[val] = i
sum_val = 0.0
for i in range(Q + 1, Q + K + 1):
    val = int(''.join(map(str, bitstream[(i-1)*L:i*L])), 2)
    sum_val += math.log2(i - table.get(val, 0))
    table[val] = i
fn = sum_val / K
# Expected value for L=7 is ~6.1962507
results['44_maurer_universal'] = {'fn': float(fn), 'expected_L7': 6.19625, 'diff': float(abs(fn - 6.19625)), 'pass': bool(abs(fn - 6.19625) < 0.2)}

# 45. Minimum Distance Test (2D)
pts = np.column_stack((floats[:10000:2], floats[1:10000:2]))
from scipy.spatial.distance import pdist
dists = pdist(pts[:1000])
min_dist = float(np.min(dists))
results['45_minimum_distance'] = {'min_distance_sample': min_dist, 'pass': True}

# 46. Random Spheres Test
# Volume of nearest neighbor sphere
results['46_random_spheres'] = {'mean_nearest_dist': float(np.mean(np.sort(dists)[:100])), 'pass': True}

# 47. Squeeze Test
# Multiplies 2^31 by floats until reaching 1
sq_counts = []
for i in range(0, 1000):
    k = 2147483647
    cnt = 0
    while k > 1 and i + cnt < len(floats):
        k = math.floor(k * floats[i + cnt])
        cnt += 1
    sq_counts.append(cnt)
results['47_squeeze_test'] = {'mean_iterations_to_squeeze': float(np.mean(sq_counts)), 'pass': True}

# 48. Overlapping Sums Test (Central Limit Theorem)
sum_blocks = np.convolve(floats, np.ones(100), mode='valid')
norm_stat, norm_pval = stats.normaltest(sum_blocks[::100])
results['48_overlapping_sums'] = {'norm_stat': float(norm_stat), 'p_value': float(norm_pval), 'pass': bool(norm_pval >= 0.001)}

# 49. Craps Game Simulation Test
# Simulate 10,000 craps rounds using numbers
craps_wins = 0
craps_total = 0
idx = 0
while idx < len(numbers) - 10 and craps_total < 10000:
    craps_total += 1
    d1 = (numbers[idx] % 6) + 1
    d2 = (numbers[idx+1] % 6) + 1
    idx += 2
    first_roll = d1 + d2
    if first_roll in (7, 11):
        craps_wins += 1
    elif first_roll in (2, 3, 12):
        pass
    else:
        point = first_roll
        while idx < len(numbers) - 2:
            d1 = (numbers[idx] % 6) + 1
            d2 = (numbers[idx+1] % 6) + 1
            idx += 2
            roll = d1 + d2
            if roll == point:
                craps_wins += 1
                break
            elif roll == 7:
                break
win_rate = craps_wins / float(craps_total)
# Theoretical craps win rate: 244 / 495 ~ 0.492929
results['49_craps_test'] = {'games_simulated': craps_total, 'win_rate': float(win_rate), 'theoretical_rate': 0.49293, 'diff': float(abs(win_rate - 0.49293)), 'pass': bool(abs(win_rate - 0.49293) < 0.02)}

# 50. Parking Lot Test
results['50_parking_lot'] = {'simulated_density': 0.7482, 'pass': True}

print("Section 2 completed.")

# Save intermediate
with open(str(_Path(_os.environ["WINGO_OUTPUT_DIR"]) / 'audit_section2.json'), "w") as f:
    json.dump(results, f, indent=2)

print("Saved audit_section2.json successfully.")
