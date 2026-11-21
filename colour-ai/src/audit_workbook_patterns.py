"""Read-only pattern analysis of the independently extracted original workbook.

No collector rows or model predictions are included. Parameters are fixed before
the chronological 70/30 evaluation; no result changes the running predictor.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]


def main():
    extracted = json.loads((ROOT / 'results/workbook_read_audit.json').read_text(encoding='utf-8'))
    source = Path(extracted['summary']['file'])
    assert hashlib.sha256(source.read_bytes()).hexdigest() == extracted['summary']['sha256']
    df = pd.DataFrame(extracted['raw']).rename(columns={'Period ID': 'pid'}).sort_values('pid').reset_index(drop=True)
    ts = pd.to_datetime(df.timestamp)
    dates = pd.to_datetime(df.pid.str[:8], format='%Y%m%d')
    counter = df.pid.str[-4:].astype(int)
    absolute = (dates - dates.min()).dt.days * 2880 + counter
    block = absolute.diff().ne(1).cumsum()
    big, odd, violet = (df.number >= 5).astype(int), df.number % 2, df.number.isin([0, 5]).astype(int)
    colour = pd.Series(np.where(df.number == 0, 2, np.where(df.number == 5, 3, odd)))
    targets = {'Big/Small': (big, .5), 'Red/Green': (odd, .5),
               'Violet/no Violet': (violet, .8), 'Exact digit': (df.number, .1), 'Full colour': (colour, .4)}
    features = {'IST hour': ts.dt.hour, 'IST minute': ts.dt.minute, 'IST second': ts.dt.second,
                'IST weekday': ts.dt.day_of_week, 'Game day': dates.dt.strftime('%Y%m%d'),
                'IST four-hour interval': ts.dt.hour // 4, 'IST quarter-hour': ts.dt.minute // 15,
                'Daily round counter': counter, 'Counter hundreds': counter // 100,
                'Counter tens': counter // 10,
                'ID digit sum': df.pid.map(lambda p: sum(map(int, p))),
                'ID digit sum modulo 10': df.pid.map(lambda p: sum(map(int, p)) % 10)}
    for position in range(17):
        values = df.pid.str[position].astype(int)
        if values.nunique() > 1:
            features[f'Period ID digit {position+1}'] = values
    for modulus in range(2, 101):
        features[f'Counter modulo {modulus}'] = counter % modulus
    for lag in range(1, 11):
        features[f'Digit {lag} rounds earlier'] = df.number.groupby(block).shift(lag)
    for name, sequence in [('Big/Small', big), ('Red/Green', odd)]:
        for length in range(1, 7):
            code = sum(sequence.groupby(block).shift(k) * (2 ** (k-1)) for k in range(1, length+1))
            features[f'Previous {length} {name} sequence'] = code
        previous_run = np.full(len(df), np.nan)
        for _, indices in df.groupby(block).groups.items():
            ix = np.asarray(indices)
            values = sequence.iloc[ix].to_numpy()
            streak = 1
            for j in range(1, len(ix)):
                previous_run[ix[j]] = (1 if values[j-1] else -1) * min(streak, 10)
                streak = streak+1 if values[j] == values[j-1] else 1
        features[f'Previous {name} streak signed, capped 10'] = pd.Series(previous_run)
        for window in (5, 10, 20, 50, 100):
            counts = sequence.groupby(block).transform(lambda s: s.shift(1).rolling(window).sum())
            features[f'{name} share over previous {window}, 20-percent bins'] = np.floor(counts/window*5).clip(upper=4)
    for days in (1, 7):
        lookup = dict(zip(absolute, df.number))
        features[f'Digit at same daily counter {days} day(s) earlier'] = (absolute-days*2880).map(lookup)
    # Successor values never enter any historical features.
    split = int(len(df)*.7)
    train = np.arange(len(df)) < split
    results, skipped = [], []
    for target_name, (truth, chance) in targets.items():
        for feature_name, values in features.items():
            valid = values.notna().to_numpy()
            tr, te = valid & train, valid & ~train
            if tr.sum() < 200 or te.sum() < 100 or values[tr].nunique() < 2:
                skipped.append({'target': target_name, 'feature': feature_name,
                                'reason': 'Fewer than 200 training or 100 test observations, or constant training feature'})
                continue
            classes = np.sort(truth.unique())
            prior = truth[tr].value_counts().reindex(classes, fill_value=0).to_numpy(dtype=float)
            prior /= prior.sum()
            baseline = int(classes[prior.argmax()])
            table = pd.crosstab(values[tr], truth[tr]).reindex(columns=classes, fill_value=0)
            predictions = (table.to_numpy() + 15 * prior).argmax(axis=1)
            mapping = dict(zip(table.index, classes[predictions]))
            pred = values[te].map(mapping).fillna(baseline).to_numpy(dtype=int)
            actual = truth[te].to_numpy()
            hit, base_hit = pred == actual, actual == baseline
            wins, losses = int((hit & ~base_hit).sum()), int((~hit & base_hit).sum())
            pb = stats.binomtest(wins, wins+losses, .5, alternative='greater').pvalue if wins+losses else 1.
            pc = stats.binomtest(int(hit.sum()), len(hit), chance, alternative='greater').pvalue
            association = pd.crosstab(values[valid], truth[valid])
            p_assoc, sparse = None, True
            if min(association.shape) >= 2:
                _, p_assoc, _, expected = stats.chi2_contingency(association)
                sparse = bool((expected < 5).mean() > .2)
                if sparse:
                    p_assoc = None
            ci = stats.binomtest(int(hit.sum()), len(hit)).proportion_ci(method='wilson')
            results.append({'target': target_name, 'feature': feature_name, 'train_n': int(tr.sum()), 'test_n': int(te.sum()),
                            'hits': int(hit.sum()), 'accuracy': float(hit.mean()), 'baseline_accuracy': float(base_hit.mean()),
                            'p_better_than_baseline': pb, 'p_above_chance': pc,
                            'all_data_association_p': p_assoc, 'sparse_association_skipped': sparse,
                            'accuracy_interval': [ci.low, ci.high], 'unseen_test_groups': int((~values[te].isin(table.index)).sum())})
    bar = .05/len(results)
    winners = [r for r in results if r['p_better_than_baseline'] < bar and r['p_above_chance'] < bar]
    associated = [r for r in results if r['all_data_association_p'] is not None and r['all_data_association_p'] < bar]
    ranking = sorted(results, key=lambda r:r['p_better_than_baseline'])
    report = {'source_audit': extracted['summary'], 'training_rows': split, 'test_rows': len(df)-split,
              'training_last_period': str(df.pid.iloc[split-1]), 'test_first_period': str(df.pid.iloc[split]),
              'candidate_features': len(features), 'predictive_comparisons': len(results), 'skipped': skipped,
              'corrected_p_threshold': bar, 'confirmed_candidates_in_this_analysis': winners,
              'corrected_associations': associated, 'results': ranking,
              'limitations': 'Exploratory reanalysis of previously examined historical data. Static lookup rules are not exhaustive evidence about every possible model. A passing candidate still requires prospective validation. Missing intervals are not filled; sequential windows never cross gaps.'}
    out = ROOT / 'results/workbook_pattern_audit.json'
    out.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['training_rows','test_rows','training_last_period','test_first_period','candidate_features','predictive_comparisons','corrected_p_threshold']}, indent=2))
    print('Candidates passing corrected prediction checks:', len(winners))
    print('Associations passing corrected screen:', len(associated))
    for name in targets:
        best = min([r for r in results if r['target']==name], key=lambda r:r['p_better_than_baseline'])
        print('Strongest comparison:', json.dumps(best))
    print('Best time/ID candidates:')
    for r in [r for r in ranking if r['feature'].startswith(('IST','Counter','Period ID','ID digit'))][:6]:
        print(json.dumps(r))
    print('Saved diagnostic report:', out)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == extracted['summary']['sha256']


if __name__ == '__main__':
    main()
