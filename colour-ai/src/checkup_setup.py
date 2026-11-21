import sys

import numpy as np
import pandas as pd
import scipy
import matplotlib
import sklearn

print("Python:", sys.version.split()[0])
print("numpy:", np.__version__)
print("pandas:", pd.__version__)
print("scipy:", scipy.__version__)
print("matplotlib:", matplotlib.__version__)
print("scikit-learn:", sklearn.__version__)

# Tiny test: 1000 fake coin flips (1 = Big, 0 = Small)
rng = np.random.default_rng(42)
flips = rng.integers(0, 2, size=1000)
print("Fake Big share:", flips.mean())
print("Setup is working!")
