import datetime as dt
import hashlib
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier, VotingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from common import build_features

CSV = Path("data/processed/rounds_30s_clean.csv")
df = pd.read_csv(CSV, dtype={"period_id": str})
X, y_num, pids = build_features(df)
y_big = (y_num >= 5).astype(int)


def lr():
    return make_pipeline(StandardScaler(), LogisticRegression(C=0.05, max_iter=2000))


def rf():
    return RandomForestClassifier(n_estimators=200, max_depth=6, min_samples_leaf=20, random_state=0, n_jobs=-1)


def gb():
    return HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=150,
                                          min_samples_leaf=40, l2_regularization=1.0, random_state=0)


def mlp():
    return make_pipeline(StandardScaler(), MLPClassifier(hidden_layer_sizes=(64, 32), alpha=0.01,
                         early_stopping=True, validation_fraction=0.15, max_iter=300, random_state=0))


def fit_all(y):
    vote = VotingClassifier([("lr", lr()), ("rf", rf()), ("gb", gb()), ("mlp", mlp())], voting="soft")
    return {
        "Gradient boosting": gb().fit(X, y),
        "Small neural network (MLP)": mlp().fit(X, y),
        "Ensemble (vote of 4 models)": vote.fit(X, y),
    }


bundle = {
    "created_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    "last_period_id": df["period_id"].max(),
    "n_train_rows": len(X),
    "data_sha256": hashlib.sha256(CSV.read_bytes()).hexdigest(),
    "big": fit_all(y_big),
    "number": fit_all(y_num),
}
Path("models").mkdir(exist_ok=True)
out = Path("models") / f"frozen_strong_{bundle['last_period_id']}.joblib"
if out.exists():
    raise SystemExit(f"STOP: {out} already exists. A frozen model must never be replaced.")
joblib.dump(bundle, out)
print("Strong models frozen:", out)
print("Created (UTC):       ", bundle["created_utc"])
print("Trained on rounds up to Period ID:", bundle["last_period_id"])
print("Training rows:       ", bundle["n_train_rows"])
print("Data file SHA-256:   ", bundle["data_sha256"])
print("\nDo NOT run this again. Copy this output and the .joblib file somewhere safe.")
