"""Dedicated Big/Small and colour networks with a continuously trained challenger.

Colour classes retain Violet overlap: Red, Green, Red+Violet, Green+Violet.
Only predictions logged BEFORE observed outcomes count toward live accuracy.
"""
import argparse
import copy
import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import numpy as np
from scipy.stats import binomtest
from sklearn.metrics import log_loss
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from advanced_model import advanced_features, build_advanced_rows, temper
from adaptive_patterns import categories as pattern_categories
import live_thousand
from neural_predictor import ROOT, UTC, LIVE, load_training_data, read_rounds, next_period, round_end

POINTER = ROOT / "models/latest_categories.json"
DB = ROOT / "results/category_predictions.sqlite3"
SIZE = ("Small", "Big")
COLOUR = ("Red", "Green", "Red+Violet", "Green+Violet")
PRIMARY = ("Red", "Green")
WINDOW = 1000
BUFFER = 2048


def labels(numbers):
    numbers = np.asarray(numbers, dtype=int)
    return {"digit": numbers, "size": (numbers >= 5).astype(int),
            "colour": np.where(numbers == 0, 2, np.where(numbers == 5, 3, numbers % 2))}


def primary_probabilities(p):
    return np.asarray(p)[..., :2] + np.asarray(p)[..., 2:]


def make_model(hidden, seed=42, batch_size=128):
    return MLPClassifier(hidden_layer_sizes=hidden, learning_rate_init=0.0005,
                         alpha=5.0, batch_size=batch_size, random_state=seed)


def atomic_save(state, path):
    temp = path.with_suffix(".tmp")
    joblib.dump(state, temp)
    for attempt in range(5):
        try:
            temp.replace(path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.1)


@contextmanager
def learner_lock(path=ROOT / 'results/category_learner.lock'):
    # Windows releases this byte-range lock even when the worker is terminated.
    import msvcrt
    with path.open('a+b') as handle:
        if path.stat().st_size == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise RuntimeError('The learning predictor is already running. Use View-Live-Predictions.cmd to view it.') from exc
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def train(evaluate_only=False, activate=True):
    frame = load_training_data()
    histories, numbers, ids = build_advanced_rows(frame, max_history=100)
    if len(numbers) < 2000:
        raise ValueError("Need at least 2,000 usable historical examples")
    y = labels(numbers)
    n = len(numbers)
    a, b, c = [int(n * f) for f in (0.55, 0.70, 0.80)]
    selection, evaluation = {}, {}
    targets = (("size", 2), ("colour", 4), ("digit", 10))
    print(f"Dedicated targets: Big/Small, four colour classes, exact number | {n} usable examples", flush=True)
    print(f"Train {a} | select {b-a} | calibrate {c-b} | final test {n-c}", flush=True)
    candidates, context_scores = {}, {}
    # Pick architecture AND context using selection data, before inspecting the test.
    for lookback in (60, 100):
        X = np.asarray([advanced_features(h, pid, lookback) for h, pid in zip(histories, ids)])
        scaler = StandardScaler().fit(X[:a])
        xs = scaler.transform(X)
        chosen = {}
        for name, classes in targets:
            best = None
            for hidden in ((64, 32), (128, 64, 32)):
                model = make_model(hidden)
                loss_best, saved, best_epoch = float("inf"), None, 1
                for epoch in range(1, 61):
                    model.partial_fit(xs[:a], y[name][:a], classes=np.arange(classes))
                    loss = log_loss(y[name][a:b], model.predict_proba(xs[a:b]), labels=np.arange(classes))
                    if loss < loss_best - 0.0001:
                        loss_best, saved, best_epoch = loss, copy.deepcopy(model), epoch
                    if epoch - best_epoch >= 8:
                        break
                print(f"History {lookback} | {name} {hidden}: epoch {best_epoch}, validation loss {loss_best:.5f}", flush=True)
                if best is None or loss_best < best[0]:
                    best = (loss_best, hidden, best_epoch, saved)
            chosen[name] = best
        # Equal relative weight per target (divide by uniform distribution entropy).
        context_scores[lookback] = float(np.mean([chosen[name][0] / np.log(k) for name, k in targets]))
        candidates[lookback] = (X, scaler, xs, chosen)
    lookback = min(context_scores, key=context_scores.get)
    X, scaler, xs, chosen = candidates[lookback]
    print(f"Selected history: {lookback} rounds; selection losses: {context_scores}", flush=True)
    for name, classes in targets:
        _, hidden, epochs, model = chosen[name]
        cal = model.predict_proba(xs[b:c])
        temperature = min((1, 2, 4, 8, 16, 32), key=lambda t: log_loss(y[name][b:c], temper(cal, t), labels=np.arange(classes)))
        test = temper(model.predict_proba(xs[c:]), temperature)
        truth = y[name][c:]
        accuracy = float(np.mean(test.argmax(axis=1) == truth))
        baseline = int(np.bincount(y[name][:a], minlength=classes).argmax())
        evaluation[name] = {"test_accuracy": accuracy, "baseline_accuracy": float(np.mean(truth == baseline)),
                            "log_loss": float(log_loss(truth, test, labels=np.arange(classes))),
                            "architecture": hidden, "epochs": epochs, "temperature": temperature}
        recent_p = np.array([(np.bincount(labels(h[-100:])[name], minlength=classes) + 1) /
                             (len(h[-100:]) + classes) for h in histories[c:]])
        evaluation[name]['recent_100_accuracy'] = float(np.mean(recent_p.argmax(axis=1) == truth))
        evaluation[name]['recent_100_log_loss'] = float(log_loss(truth, recent_p, labels=np.arange(classes)))
        if name == "colour":
            evaluation[name]["red_green_accuracy"] = float(np.mean(primary_probabilities(test).argmax(axis=1) == numbers[c:] % 2))
            evaluation[name]["red_green_baseline_accuracy"] = float(np.mean(numbers[c:] % 2 == np.bincount(numbers[:a] % 2).argmax()))
        selection[name] = (hidden, epochs, temperature)
    print(json.dumps(evaluation, indent=2), flush=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run_id = f"categories_{stamp}"
    report = {"run_id": run_id, "usable_rows": n, "test_rows": n-c, "lookback": lookback,
              "selection_context_losses": context_scores,
              "test_start": str(ids[c]), "test_end": str(ids[-1]), "evaluation": evaluation,
              "note": "Historical data has been explored before. Live performance is scored before online updates. Recent-100 frequencies use up to 100 consecutive preceding observations. Violet overlaps Red/Green. No guaranteed accuracy."}
    report_path = ROOT / "results" / f"{run_id}_evaluation.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if evaluate_only:
        return report
    scaler = StandardScaler().fit(X)
    scaled = scaler.transform(X)
    champions = {}
    for name, classes in targets:
        hidden, epochs, temperature = selection[name]
        model = make_model(hidden)
        for _ in range(epochs):
            model.partial_fit(scaled, y[name], classes=np.arange(classes))
        champions[name] = {"model": model, "temperature": temperature}
    challengers = copy.deepcopy(champions)
    for member in challengers.values():
        member["model"].learning_rate_init = 0.00005
        member["model"].batch_size = 32
        # Continue the trained network with a fresh low-rate online optimizer.
        if hasattr(member["model"], "_optimizer"):
            del member["model"]._optimizer
    state = {"run_id": run_id, "revision": 0, "updates": 0, "window": 1, "lookback": lookback,
             "trained_through": str(frame.period_id.iloc[-1]), "learned_through": str(frame.period_id.iloc[-1]),
             "training_rows": n, "scaler": scaler, "champions": champions, "challengers": challengers,
             "buffer_X": scaled[-BUFFER:], "buffer_numbers": numbers[-BUFFER:], "rng": np.random.default_rng(42),
             "baseline_size": int(np.bincount(y['size']).argmax()),
             "baseline_primary": int(np.bincount(numbers % 2).argmax()),
             "baseline_digit": int(np.bincount(numbers, minlength=10).argmax()),
             "evaluation": evaluation, "decisions": [],
             "data_sha256": hashlib.sha256(frame.to_csv(index=False).encode()).hexdigest()}
    path = ROOT / "models" / f"{run_id}_checkpoint.joblib"
    atomic_save(state, path)
    destination = POINTER if activate else ROOT / 'models/latest_memory_candidate.json'
    temp = destination.with_suffix(".tmp")
    temp.write_text(json.dumps({"checkpoint": str(path), "report": str(report_path)}, indent=2), encoding="utf-8")
    temp.replace(destination)
    print(f"Trained Big/Small and colour networks saved: {path}", flush=True)


def open_db(path=DB):
    connection = sqlite3.connect(path)
    connection.execute("""CREATE TABLE IF NOT EXISTS category_predictions (
        period TEXT PRIMARY KEY, source TEXT NOT NULL, created_utc TEXT NOT NULL, deadline_utc TEXT NOT NULL,
        run_id TEXT NOT NULL, revision INTEGER NOT NULL, updates INTEGER NOT NULL, window INTEGER NOT NULL,
        learned_through TEXT NOT NULL, size_probs TEXT NOT NULL, colour_probs TEXT NOT NULL,
        shadow_size_probs TEXT NOT NULL, shadow_colour_probs TEXT NOT NULL,
        baseline_size INTEGER NOT NULL, baseline_primary INTEGER NOT NULL,
        actual INTEGER, scored_utc TEXT)""")
    connection.execute("""CREATE TABLE IF NOT EXISTS digit_predictions (
        period TEXT PRIMARY KEY, main_probs TEXT NOT NULL, shadow_probs TEXT NOT NULL,
        baseline INTEGER NOT NULL)""")
    connection.execute("""CREATE TABLE IF NOT EXISTS recent_predictions (
        period TEXT PRIMARY KEY, size_probs TEXT NOT NULL, colour_probs TEXT NOT NULL,
        digit_probs TEXT NOT NULL, observed INTEGER NOT NULL)""")
    connection.execute("""CREATE TABLE IF NOT EXISTS adaptive_predictions (
        period TEXT PRIMARY KEY, model_id TEXT NOT NULL, digit_probs TEXT NOT NULL,
        learned_through TEXT NOT NULL, updates INTEGER NOT NULL)""")
    connection.execute("""CREATE TABLE IF NOT EXISTS thousand_predictions (
        period TEXT PRIMARY KEY, model_id TEXT NOT NULL, learned_through TEXT NOT NULL, updates INTEGER NOT NULL,
        fixed_size TEXT NOT NULL, fixed_colour TEXT NOT NULL, fixed_digit TEXT NOT NULL,
        learning_size TEXT NOT NULL, learning_colour TEXT NOT NULL, learning_digit TEXT NOT NULL,
        base_size_accuracy REAL NOT NULL)""")
    connection.commit()
    return connection


def reconcile(connection, frame):
    values = dict(zip(frame.period_id, frame.number))
    rows = connection.execute("SELECT period, size_probs, colour_probs FROM category_predictions WHERE actual IS NULL ORDER BY period").fetchall()
    results = []
    for pid, size_p, colour_p in rows:
        if pid not in values:
            continue
        actual = int(values[pid])
        updated = connection.execute("UPDATE category_predictions SET actual=?, scored_utc=? WHERE period=? AND actual IS NULL",
                                     (actual, datetime.now(UTC).isoformat(), pid))
        if updated.rowcount:
            s = int(np.argmax(json.loads(size_p)))
            p = int(np.argmax(primary_probabilities(json.loads(colour_p))))
            results.append(f"RESULT | {pid} | actual {actual}: {SIZE[actual >= 5]}, {COLOUR[int(labels([actual])['colour'][0])]} | "
                           f"size {SIZE[s]}: {'HIT' if s == int(actual >= 5) else 'MISS'} | "
                           f"colour {PRIMARY[p]}: {'HIT' if p == actual % 2 else 'MISS'}")
    connection.commit()
    return results


def online_update(state, frame):
    """Learn observed outcomes exactly once, using only their preceding history."""
    updates = 0
    lookback = state.get('lookback', 60)
    for _, group in frame.groupby(frame['index'].diff().ne(1).cumsum()):
        values, ids = group.number.to_numpy(), group.period_id.to_numpy()
        for i in range(20, len(group)):
            if ids[i] <= state['learned_through']:
                continue
            x = advanced_features(values[max(0, i-lookback):i], ids[i], lookback).reshape(1, -1)
            x = state['scaler'].transform(x)
            count = min(31, len(state['buffer_numbers']))
            indices = state['rng'].choice(len(state['buffer_numbers']), count, replace=False)
            replay_X = np.vstack([state['buffer_X'][indices], x])
            replay_numbers = np.append(state['buffer_numbers'][indices], values[i])
            targets = labels(replay_numbers)
            for name, member in state['challengers'].items():
                member['model'].partial_fit(replay_X, targets[name])
            state['buffer_X'] = np.vstack([state['buffer_X'], x])[-BUFFER:]
            state['buffer_numbers'] = np.append(state['buffer_numbers'], values[i])[-BUFFER:]
            state['learned_through'] = str(ids[i])
            state['updates'] += 1
            updates += 1
    # Skip unlearnable observations inside short blocks without inventing history.
    if len(frame) and frame.period_id.iloc[-1] > state['learned_through']:
        state['learned_through'] = str(frame.period_id.iloc[-1])
    return updates


def paired_p(candidate_hit, reference_hit):
    wins = int((candidate_hit & ~reference_hit).sum())
    losses = int((~candidate_hit & reference_hit).sum())
    return binomtest(wins, wins+losses, 0.5, alternative='greater').pvalue if wins+losses else 1.0


def compare_candidate(truth, champion_p, challenger_p, baseline, chance, alpha):
    main_hit, new_hit = champion_p.argmax(axis=1) == truth, challenger_p.argmax(axis=1) == truth
    reference_hit = baseline == truth
    p_main, p_base = paired_p(new_hit, main_hit), paired_p(new_hit, reference_hit)
    p_chance = binomtest(int(new_hit.sum()), len(truth), chance, alternative='greater').pvalue
    loss_main = log_loss(truth, champion_p, labels=np.arange(champion_p.shape[1]))
    loss_new = log_loss(truth, challenger_p, labels=np.arange(challenger_p.shape[1]))
    return {"champion_accuracy": float(main_hit.mean()), "challenger_accuracy": float(new_hit.mean()),
            "p_vs_champion": p_main, "p_vs_baseline": p_base, "p_vs_chance": p_chance,
            "promote": bool(p_main < alpha and p_base < alpha and p_chance < alpha and loss_new <= loss_main)}


def evaluate_window(state, connection, required=WINDOW):
    rows = connection.execute("""SELECT size_probs, colour_probs, shadow_size_probs, shadow_colour_probs,
        actual, baseline_size, baseline_primary FROM category_predictions
        WHERE run_id=? AND window=? AND actual IS NOT NULL ORDER BY period LIMIT ?""",
        (state['run_id'], state['window'], required)).fetchall()
    if len(rows) < required:
        return None
    numbers = np.array([r[4] for r in rows])
    size, colour, shadow_size, shadow_colour = [np.array([json.loads(r[k]) for r in rows]) for k in range(4)]
    # Fixed non-overlapping windows; total alpha budget across two targets/windows <= .05.
    window = state['window']
    alpha = 0.05 / (len(state['champions']) * window * (window+1))
    decisions = {"size": compare_candidate((numbers >= 5).astype(int), size, shadow_size,
                                          np.array([r[5] for r in rows]), 0.5, alpha),
                 "colour": compare_candidate(numbers % 2, primary_probabilities(colour), primary_probabilities(shadow_colour),
                                            np.array([r[6] for r in rows]), 0.5, alpha)}
    colour_y = labels(numbers)['colour']
    # Improving Red/Green must not worsen the full colour distribution including Violet.
    if log_loss(colour_y, shadow_colour, labels=range(4)) > log_loss(colour_y, colour, labels=range(4)):
        decisions['colour']['promote'] = False
    if 'digit' in state['champions']:
        digit_rows = connection.execute("""SELECT d.main_probs, d.shadow_probs, p.actual, d.baseline
            FROM category_predictions p JOIN digit_predictions d ON p.period=d.period
            WHERE p.run_id=? AND p.window=? AND p.actual IS NOT NULL ORDER BY p.period LIMIT ?""",
            (state['run_id'], state['window'], required)).fetchall()
        if len(digit_rows) == required:
            decisions['digit'] = compare_candidate(np.array([r[2] for r in digit_rows]),
                np.array([json.loads(r[0]) for r in digit_rows]), np.array([json.loads(r[1]) for r in digit_rows]),
                np.array([r[3] for r in digit_rows]), 0.1, alpha)
    for name, decision in decisions.items():
        if decision['promote']:
            state['champions'][name] = copy.deepcopy(state['challengers'][name])
            state['revision'] += 1
    result = {"window": window, "rounds": required, "alpha": alpha, "decisions": decisions}
    state['decisions'].append(result)
    state['window'] += 1
    return result


def forecast(state, frame, now=None, thousand=None):
    now = now or datetime.now(UTC)
    lookback = state.get('lookback', 60)
    recent = frame.tail(lookback)
    if len(recent):
        segments = recent['index'].diff().ne(1).cumsum()
        recent = recent[segments == segments.iloc[-1]]
    if len(recent) < 20:
        return None, "Waiting for 20 consecutive observed rounds."
    source = str(recent.period_id.iloc[-1])
    target = next_period(source)
    deadline = round_end(target)
    if now >= deadline - timedelta(seconds=3):
        return None, "Collector is too late for this next round; waiting for an update."
    if round_end(source) > now + timedelta(seconds=5) or state['learned_through'] > source:
        return None, "Clock or model/data cutoff mismatch; refusing a retrospective prediction."
    x = state['scaler'].transform(advanced_features(recent.number.to_numpy(), target, lookback).reshape(1, -1))
    result = {"source": source, "period": target, "deadline": deadline}
    for group in ('champions', 'challengers'):
        for name, member in state[group].items():
            p = temper(member['model'].predict_proba(x), member['temperature'])[0]
            if not np.isfinite(p).all() or (p < 0).any() or not np.isclose(p.sum(), 1):
                raise ValueError("Invalid model probabilities")
            result[f'{group}_{name}'] = p
    last100 = frame.tail(100)
    blocks = last100['index'].diff().ne(1).cumsum()
    last100 = last100[blocks == blocks.iloc[-1]]
    result['recent_observed'] = len(last100)
    recent_targets = labels(last100.number.to_numpy())
    for name, classes in (('size', 2), ('colour', 4), ('digit', 10)):
        result[f'recent_{name}'] = (np.bincount(recent_targets[name], minlength=classes) + 1) / (len(last100) + classes)
    if 'adaptive' in state:
        adaptive = state['adaptive']['model']
        if adaptive.learned_through == source:
            p = adaptive.predict(target)
            if not np.isfinite(p).all() or (p < 0).any() or not np.isclose(p.sum(), 1):
                raise ValueError('Invalid adaptive probabilities')
            result.update(adaptive_digit=p, adaptive_id=state['adaptive']['model_id'],
                          adaptive_learned_through=adaptive.learned_through,
                          adaptive_updates=adaptive.updates, adaptive_leaders=adaptive.leaders(),
                          adaptive_evidence=adaptive.sequence_evidence())
    if thousand is not None and 'thousand_learning' in state:
        memory = state['thousand_learning']
        if memory['model_id'] == thousand['model_id'] and memory['learned_through'] <= source:
            history = frame.tail(500)
            blocks = history['index'].diff().ne(1).cumsum()
            history = history[blocks == blocks.iloc[-1]]
            result['thousand'] = live_thousand.predict(thousand, memory, history.number.to_numpy(), target)
    return result, None


def record(connection, state, prediction):
    now = datetime.now(UTC)
    if now >= prediction['deadline'] - timedelta(seconds=3):
        return False
    with connection:
        row = connection.execute("""INSERT OR IGNORE INTO category_predictions
            (period, source, created_utc, deadline_utc, run_id, revision, updates, window, learned_through,
             size_probs, colour_probs, shadow_size_probs, shadow_colour_probs, baseline_size, baseline_primary)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (prediction['period'], prediction['source'], now.isoformat(), prediction['deadline'].isoformat(),
             state['run_id'], state['revision'], state['updates'], state['window'], state['learned_through'],
             *[json.dumps(prediction[key].tolist()) for key in ('champions_size', 'champions_colour', 'challengers_size', 'challengers_colour')],
             state['baseline_size'], state['baseline_primary']))
        if row.rowcount == 1 and 'champions_digit' in prediction:
            connection.execute('INSERT INTO digit_predictions VALUES (?, ?, ?, ?)',
                (prediction['period'], json.dumps(prediction['champions_digit'].tolist()),
                 json.dumps(prediction['challengers_digit'].tolist()), state['baseline_digit']))
        if row.rowcount == 1 and 'recent_size' in prediction:
            connection.execute('INSERT INTO recent_predictions VALUES (?, ?, ?, ?, ?)',
                (prediction['period'], *[json.dumps(prediction[f'recent_{name}'].tolist())
                                        for name in ('size', 'colour', 'digit')], prediction['recent_observed']))
        if row.rowcount == 1 and 'adaptive_digit' in prediction:
            connection.execute('INSERT INTO adaptive_predictions VALUES (?, ?, ?, ?, ?)',
                (prediction['period'], prediction['adaptive_id'], json.dumps(prediction['adaptive_digit'].tolist()),
                 prediction['adaptive_learned_through'], prediction['adaptive_updates']))
        if row.rowcount == 1 and 'thousand' in prediction:
            p = prediction['thousand']
            connection.execute('INSERT INTO thousand_predictions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (prediction['period'], p['model_id'], p['learned_through'], p['updates'],
                 *[json.dumps(p[group][name].tolist()) for group in ('fixed', 'learning') for name in ('size', 'colour', 'digit')],
                 p['test_size_accuracy']))
    return row.rowcount == 1


def print_status(connection, state):
    if 'thousand_learning' in state:
        memory = state['thousand_learning']
        rows = connection.execute('''SELECT t.fixed_size, t.learning_size, t.learning_colour, t.learning_digit, p.actual
            FROM thousand_predictions t JOIN category_predictions p ON p.period=t.period
            WHERE t.model_id=? AND p.actual IS NOT NULL ORDER BY p.period''', (memory['model_id'],)).fetchall()
        if rows:
            truth = np.array([r[4] for r in rows])
            prob = [np.array([json.loads(r[k]) for r in rows]) for k in range(4)]
            print(f"1000 INPUT LIVE SCORES | {len(rows)} completed | fixed Big/Small {np.mean(prob[0].argmax(1) == (truth >= 5)):.1%}"
                  f" | learning Big/Small {np.mean(prob[1].argmax(1) == (truth >= 5)):.1%}"
                  f" | learning Red/Green {np.mean(primary_probabilities(prob[2]).argmax(1) == truth % 2):.1%}"
                  f" | learning number {np.mean(prob[3].argmax(1) == truth):.1%}", flush=True)
        print(f"1000 INPUT MEMORY | {memory['updates']} new rounds used to adjust mixture weights | learned through {memory['learned_through']}", flush=True)
    rows = connection.execute("SELECT size_probs, colour_probs, shadow_size_probs, shadow_colour_probs, actual FROM category_predictions WHERE run_id=? AND actual IS NOT NULL ORDER BY period",
                              (state['run_id'],)).fetchall()
    if rows:
        actual = np.array([r[4] for r in rows])
        probs = [np.array([json.loads(r[k]) for r in rows]) for k in range(4)]
        accuracy = lambda pred, truth: f"{int(np.sum(pred == truth))}/{len(truth)} ({np.mean(pred == truth):.1%})"
        print("SCORES | Big/Small " + accuracy(probs[0].argmax(axis=1), actual >= 5)
              + " | Red/Green " + accuracy(primary_probabilities(probs[1]).argmax(axis=1), actual % 2)
              + " | full colour incl. Violet " + accuracy(probs[1].argmax(axis=1), labels(actual)['colour']), flush=True)
        print("CHALLENGER | Big/Small " + accuracy(probs[2].argmax(axis=1), actual >= 5)
              + " | Red/Green " + accuracy(primary_probabilities(probs[3]).argmax(axis=1), actual % 2), flush=True)
        print("SIMPLE BASELINES | Big/Small " + accuracy(np.full(len(actual), state['baseline_size']), actual >= 5)
              + " | Red/Green " + accuracy(np.full(len(actual), state['baseline_primary']), actual % 2), flush=True)
        digit_rows = connection.execute("""SELECT d.main_probs, d.shadow_probs, p.actual, d.baseline
            FROM digit_predictions d JOIN category_predictions p ON p.period=d.period
            WHERE p.run_id=? AND p.actual IS NOT NULL ORDER BY p.period""", (state['run_id'],)).fetchall()
        if digit_rows:
            truth = np.array([r[2] for r in digit_rows])
            print('NUMBER SCORES | current ' + accuracy(np.array([np.argmax(json.loads(r[0])) for r in digit_rows]), truth)
                  + ' | learning ' + accuracy(np.array([np.argmax(json.loads(r[1])) for r in digit_rows]), truth)
                  + ' | baseline ' + accuracy(np.array([r[3] for r in digit_rows]), truth), flush=True)
        recent_rows = connection.execute("""SELECT r.size_probs, r.colour_probs, r.digit_probs, p.actual
            FROM recent_predictions r JOIN category_predictions p ON p.period=r.period
            WHERE p.run_id=? AND p.actual IS NOT NULL ORDER BY p.period""", (state['run_id'],)).fetchall()
        if recent_rows:
            truth = np.array([r[3] for r in recent_rows])
            print('RECENT-100 RULE SCORES | Big/Small ' + accuracy(np.array([np.argmax(json.loads(r[0])) for r in recent_rows]), truth >= 5)
                  + ' | Red/Green ' + accuracy(np.array([np.argmax(primary_probabilities(json.loads(r[1]))) for r in recent_rows]), truth % 2)
                  + ' | number ' + accuracy(np.array([np.argmax(json.loads(r[2])) for r in recent_rows]), truth), flush=True)
    else:
        print("SCORES | No completed Big/Small or colour predictions yet.", flush=True)
    completed = connection.execute("SELECT COUNT(*) FROM category_predictions WHERE run_id=? AND window=? AND actual IS NOT NULL", (state['run_id'], state['window'])).fetchone()[0]
    print(f"LEARNING | {state['updates']} new examples learned | current comparison {completed}/{WINDOW} completed rounds | champion revision {state['revision']}", flush=True)
    print(f"MEMORY | learned through {state['learned_through']} | {state.get('lookback', 60)}-round context | "
          f"{len(state['buffer_numbers'])} replay examples | weights and replay saved on disk", flush=True)
    if 'adaptive' in state:
        adaptive = state['adaptive']
        records = connection.execute("""SELECT a.digit_probs, p.actual FROM adaptive_predictions a
            JOIN category_predictions p ON a.period=p.period
            WHERE a.model_id=? AND p.actual IS NOT NULL ORDER BY p.period""", (adaptive['model_id'],)).fetchall()
        if records:
            p = pattern_categories(np.array([json.loads(row[0]) for row in records]))
            truth = np.array([row[1] for row in records])
            size_hits = int(np.sum(p['size'].argmax(1) == (truth >= 5)))
            interval = binomtest(size_hits, len(truth)).proportion_ci(method='wilson')
            print(f"ADAPTIVE SCORES | Big/Small {size_hits}/{len(truth)} ({size_hits/len(truth):.1%}; 95% range {interval.low:.1%}-{interval.high:.1%})"
                  f" | Red/Green {np.mean(p['primary'].argmax(1) == truth % 2):.1%}"
                  f" | number {np.mean(p['digit'].argmax(1) == truth):.1%} | experimental, no established advantage", flush=True)
        model = adaptive['model']
        print(f"PATTERN MEMORY | {model.observations} observed rounds | {model.updates} scored learning updates | "
              f"{len(model.counts)} stored contexts | {len(model.names)} methods | learned through {model.learned_through}", flush=True)


def print_forecasts(prediction, frame):
    if 'thousand' in prediction:
        p = prediction['thousand']['learning']
        primary = primary_probabilities(p['colour'])
        print(f"NEXT 1000 INPUT MODEL | period {prediction['period']}", flush=True)
        print(f"  NUMBER PICK: {p['digit'].argmax()} | confidence estimate {p['digit'].max():.2%}", flush=True)
        print(f"  COLOUR PICK: {PRIMARY[primary.argmax()]} | confidence estimate {primary.max():.2%} | Violet {p['colour'][2:].sum():.2%}", flush=True)
        print(f"  BIG/SMALL PICK: {SIZE[p['size'].argmax()]} | confidence estimate {p['size'].max():.2%}", flush=True)
    recent = frame.tail(100)
    segments = recent['index'].diff().ne(1).cumsum()
    recent = recent[segments == segments.iloc[-1]]
    big = (recent.number.to_numpy() >= 5).astype(int)
    run = 1
    while run < len(big) and big[-run-1] == big[-1]:
        run += 1
    sequence = ' '.join('B' if value else 'S' for value in big[-12:])
    print(f"RECENT ACTUALS (oldest -> newest) | {sequence} | observed streak: {SIZE[big[-1]]} x{run}", flush=True)
    print(f"RECENT {len(recent)} OBSERVED | Big {big.sum()}/{len(big)} ({big.mean():.1%}) | "
          f"Small {len(big)-big.sum()}/{len(big)} ({1-big.mean():.1%}) | historical frequency, not next-round confidence", flush=True)
    end = prediction['deadline'].astimezone(timezone(timedelta(hours=5, minutes=30)))
    for group, title in (('champions', 'NEXT CURRENT MODEL'), ('challengers', 'NEXT LEARNING MODEL')):
        sp, cp = prediction[f'{group}_size'], prediction[f'{group}_colour']
        pp = primary_probabilities(cp)
        print(f"{title} | {prediction['period']} | {SIZE[sp.argmax()]} ({sp.max():.1%}) | {PRIMARY[pp.argmax()]} ({pp.max():.1%}) "
              f"| Violet chance {cp[2:].sum():.1%} | most likely full colour {COLOUR[cp.argmax()]} | ends {end:%H:%M:%S} IST", flush=True)
        if f'{group}_digit' in prediction:
            dp = prediction[f'{group}_digit']
            top = np.argsort(-dp, kind='stable')[:3]
            print(f"{title} NUMBER | {int(top[0])} ({dp[top[0]]:.2%}) | top 3: " +
                  ', '.join(f'{int(d)} ({dp[d]:.2%})' for d in top), flush=True)
    if 'adaptive_digit' in prediction:
        p = pattern_categories(prediction['adaptive_digit'])
        digit = int(p['digit'].argmax())
        print(f"NEXT ADAPTIVE MODEL | {prediction['period']} | number {digit} ({p['digit'][digit]:.2%}) | "
              f"{SIZE[p['size'].argmax()]} ({p['size'].max():.1%}) | {PRIMARY[p['primary'].argmax()]} ({p['primary'].max():.1%}) | "
              f"Violet {p['colour'][2:].sum():.1%} | ends {end:%H:%M:%S} IST", flush=True)
        print('PATTERN WEIGHTS (not confidence) | ' + ', '.join(f'{name}: {weight:.1%}' for name, weight in prediction['adaptive_leaders']), flush=True)
        evidence = prediction.get('adaptive_evidence')
        if evidence:
            print(f"SIMILAR PAST SEQUENCE | {evidence['sequence']} | followed by Big {evidence['followed_by_big']}/{evidence['observed']} times | descriptive history, not a guaranteed pattern", flush=True)


def watch(once=False):
    pointer = json.loads(POINTER.read_text(encoding='utf-8'))
    path = Path(pointer['checkpoint'])
    state = joblib.load(path)
    thousand = live_thousand.load_model()
    patterns_pointer = ROOT / 'models/latest_patterns.json'
    if 'adaptive' not in state and patterns_pointer.exists():
        state['adaptive'] = joblib.load(json.loads(patterns_pointer.read_text(encoding='utf-8'))['checkpoint'])
    connection = open_db()
    print(f"Number + Big/Small + Colour | {state['run_id']} | initially trained on {state['training_rows']} examples", flush=True)
    print("Red/Green is the primary colour; Violet additionally occurs for 0 and 5. Probabilities are estimates, not guaranteed win rates.", flush=True)
    print("The challenger learns observed outcomes. Champion changes require a completed 1,000-round future comparison.", flush=True)
    print("NEXT CURRENT MODEL is the fixed reference; NEXT LEARNING MODEL is the continuously updated challenger. Both are recorded and scored.", flush=True)
    print("Number, size and colour are separate target estimates; their top choices can differ. The number's probability is for the exact digit.", flush=True)
    if 'adaptive' in state:
        print('NEXT ADAPTIVE MODEL combines sequence, streak, frequency and clock methods. It learns after scoring each observed outcome. This new method is experimental.', flush=True)
    if thousand is not None:
        print('1000 INPUT MODEL enabled. Its frozen model and adaptive mixture are recorded separately. Mixture weights learn new outcomes; the underlying networks and trees are not retrained every round.', flush=True)
    stamp, last_message = None, None
    try:
        while True:
            try:
                current = LIVE.stat().st_mtime_ns
                if current != stamp:
                    frame = read_rounds(LIVE, 'issueNumber')
                    for line in reconcile(connection, frame):
                        print(line, flush=True)
                    # Score logged predictions, learn observed outcomes, then predict a still-unseen target.
                    decision = None
                    if not once:
                        if thousand is not None:
                            memory = state.get('thousand_learning')
                            if memory is None or memory['model_id'] != thousand['model_id']:
                                if memory is not None:
                                    state.setdefault('thousand_archive', {})[memory['model_id']] = memory
                                state['thousand_learning'] = live_thousand.initialize(thousand, str(frame.period_id.iloc[-1]))
                            else:
                                live_thousand.learn(thousand, memory, frame)
                        online_update(state, frame)
                        if 'adaptive' in state:
                            state['adaptive']['model'].ingest(frame)
                        decision = evaluate_window(state, connection)
                        atomic_save(state, path)
                    if decision:
                        print("COMPARISON COMPLETE | " + json.dumps(decision), flush=True)
                    print_status(connection, state)
                    prediction, message = forecast(state, frame, thousand=thousand)
                    if prediction and record(connection, state, prediction):
                        print_forecasts(prediction, frame)
                    elif message and message != last_message:
                        print(message, flush=True)
                    stamp, last_message = current, message
            except (OSError, sqlite3.OperationalError) as exc:
                if once:
                    raise
                print(f"Waiting for file/database access; will retry: {exc}", flush=True)
                time.sleep(2)
            if once:
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopped. Learning checkpoint and scored predictions are preserved.", flush=True)
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('train', 'train-candidate', 'evaluate', 'watch', 'predict', 'status'))
    args = parser.parse_args()
    with threadpool_limits(limits=2):
        if args.command == 'train-candidate':
            with learner_lock(ROOT / 'results/category_candidate.lock'):
                train(activate=False)
        elif args.command == 'evaluate':
            train(evaluate_only=True)
        elif args.command == 'train':
            with learner_lock():
                train()
        elif args.command == 'status':
            state = joblib.load(json.loads(POINTER.read_text(encoding='utf-8'))['checkpoint'])
            connection = open_db()
            try:
                reconcile(connection, read_rounds(LIVE, 'issueNumber'))
                print_status(connection, state)
            finally:
                connection.close()
        elif args.command == 'predict':
            watch(once=True)
        else:
            with learner_lock():
                watch()


if __name__ == '__main__':
    main()
