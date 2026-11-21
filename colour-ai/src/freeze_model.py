import datetime as dt
import hashlib
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from common import build_features

CSV = Path("data/processed/rounds_30s_clean.csv")
df = pd.read_csv(CSV, dtype={"period_id": str})
X, y_num, pids = build_features(df)
y_big = (y_num >= 5).astype(int)


def fit_all(y):
    return {
        "majority": int(np.bincount(y).argmax()),
        "logistic": make_pipeline(StandardScaler(), LogisticRegression(C=0.05, max_iter=2000)).fit(X, y),
        "forest": RandomForestClassifier(n_estimators=200, max_depth=6, min_samples_leaf=20,
                                         random_state=0, n_jobs=-1).fit(X, y),
    }


bundle = {
    "created_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    "last_period_id": df["period_id"].max(),          # every round up to here was used for training
    "n_train_rows": len(X),
    "data_sha256": hashlib.sha256(CSV.read_bytes()).hexdigest(),
    "big": fit_all(y_big),
    "number": fit_all(y_num),
}
Path("models").mkdir(exist_ok=True)
out = Path("models") / f"frozen_{bundle['last_period_id']}.joblib"
if out.exists():
    raise SystemExit(f"STOP: {out} already exists. A frozen model must never be replaced.")
joblib.dump(bundle, out)
print("Frozen model saved:", out)
print("Created (UTC):      ", bundle["created_utc"])
print("Trained on rounds up to Period ID:", bundle["last_period_id"])
print("Training rows:      ", bundle["n_train_rows"])
print("Data file SHA-256:  ", bundle["data_sha256"])
print("\nNow: copy this output and the .joblib file somewhere safe. Do NOT retrain or edit it.")
print("Rounds after", bundle["last_period_id"], "will be the fresh test.")
