# Archived research method; known defects and hardcoded verdicts are preserved.
# Read docs/CLAIM_LEDGER.md before interpreting any result. Not a certified suite.
import os as _os
from pathlib import Path as _Path
if _os.environ.get("WINGO_ALLOW_LEGACY") != "1":
    raise SystemExit("Use scripts/run_audit_suite.py --replay with explicit options.")

import math
import json
import numpy as np
import pandas as pd
from collections import Counter
from scipy import stats

csv_path = _os.environ["WINGO_INPUT_CSV"]
df = pd.read_csv(csv_path)
premiums = df['premium'].astype(int).values
numbers = df['number'].astype(int).values
N = len(premiums)

# 1. ENT on Numbers (Digits 0-9)
p_digits = [Counter(numbers)[d] / float(N) for d in range(10)]
ent_entropy_digits = -sum(p * math.log2(p) for p in p_digits if p > 0)
ent_mean_digits = float(np.mean(numbers)) # Expected 4.5
ent_chi2_digits = float(stats.chisquare([Counter(numbers)[d] for d in range(10)], [N/10.0]*10).statistic)
r_serial_digits = float(stats.pearsonr(numbers[:-1], numbers[1:])[0])

# Monte Carlo Pi estimation using pairs of floats
# Sample points in [0, 1)^2
pts_x = (premiums[0::2] - 10000) / 90000.0
pts_y = (premiums[1::2] - 10000) / 90000.0
min_len = min(len(pts_x), len(pts_y))
inside_circle = np.sum(pts_x[:min_len]**2 + pts_y[:min_len]**2 <= 1.0)
pi_estimate = float(4.0 * inside_circle / min_len)
pi_error = float(abs(pi_estimate - math.pi) / math.pi * 100)

ent_results = {
    'shannon_entropy_digits': ent_entropy_digits,
    'theoretical_max_entropy': math.log2(10),
    'arithmetic_mean_digits': ent_mean_digits,
    'expected_mean': 4.5000,
    'chi_square_stat': ent_chi2_digits,
    'serial_correlation': r_serial_digits,
    'monte_carlo_pi_estimate': pi_estimate,
    'pi_actual': math.pi,
    'pi_error_percent': pi_error
}

print("ENT Results:")
print(json.dumps(ent_results, indent=2))

with open(str(_Path(_os.environ["WINGO_OUTPUT_DIR"]) / 'audit_ent.json'), "w") as f:
    json.dump(ent_results, f, indent=2)
