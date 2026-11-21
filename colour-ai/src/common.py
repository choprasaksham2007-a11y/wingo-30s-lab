import numpy as np
import pandas as pd

LAGS = 10          # how many past rounds a model may look at
FEATURE_NAMES = ([f"big_{k}" for k in range(1, LAGS + 1)] + [f"odd_{k}" for k in range(1, LAGS + 1)]
                 + [f"violet_{k}" for k in range(1, LAGS + 1)] + ["big_count", "streak"]
                 + [f"last{k}_is_{d}" for k in (1, 2, 3) for d in range(10)])


def build_features(df):
    """One row per round. Features use ONLY earlier rounds of the same block."""
    X, y_num, order, pids = [], [], [], []
    for _, g in df.groupby("block_id"):
        g = g.sort_values("pos_in_block")
        num, idx, pid = g["number"].values, g["abs_index"].values, g["period_id"].values
        for i in range(LAGS, len(g)):
            past = num[i - LAGS:i][::-1]               # past[0] = the round just before
            big, odd, vio = (past >= 5).astype(int), past % 2, np.isin(past, [0, 5]).astype(int)
            run = 1
            while run < LAGS and big[run] == big[0]:
                run += 1
            feats = list(big) + list(odd) + list(vio) + [big.sum(), run if big[0] == 1 else -run]
            for k in range(3):
                one_hot = np.zeros(10)
                one_hot[past[k]] = 1
                feats += list(one_hot)
            X.append(feats)
            y_num.append(num[i])
            order.append(idx[i])
            pids.append(pid[i])
    sort = np.argsort(np.array(order))
    X = pd.DataFrame(X, columns=FEATURE_NAMES).iloc[sort].reset_index(drop=True)
    return X, np.array(y_num)[sort], np.array(pids)[sort]
