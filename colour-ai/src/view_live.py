"""Read-only live viewer of immutable, pre-result predictions in SQLite."""
import argparse
import json
import os
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone

import numpy as np

from neural_predictor import ROOT
from adaptive_patterns import categories


def probability_lines(title, size, colour, digit=None, compact=False):
    size, colour = np.asarray(size), np.asarray(colour)
    primary = colour[:2] + colour[2:]
    choice = 'BIG' if size.argmax() else 'SMALL'
    if compact:
        lines = [title, f'  BIG / SMALL: {choice} | confidence estimate {size.max():.2%}',
                 f"  Colour: {'GREEN' if primary.argmax() else 'RED'} ({primary.max():.2%}) | Violet: {colour[2:].sum():.2%}"]
        if digit is not None:
            digit = np.asarray(digit)
            lines.append(f'  Number: {digit.argmax()} ({digit.max():.2%})')
        return lines
    lines = [title, f'  BIG / SMALL PICK: {choice}',
             f'  ESTIMATED CONFIDENCE: {size.max():.2%}',
             f'  Big: {size[1]:.2%}     Small: {size[0]:.2%}',
             f"  COLOUR PICK: {'GREEN' if primary.argmax() else 'RED'} ({primary.max():.2%})",
             f'  Violet: {colour[2:].sum():.2%}']
    if digit is not None:
        digit = np.asarray(digit)
        top = np.argsort(-digit, kind='stable')[:3]
        lines += [f'  NUMBER PICK: {top[0]} ({digit[top[0]]:.2%})',
                  '  Top numbers: ' + ', '.join(f'{i}: {digit[i]:.2%}' for i in top)]
    return lines


def render(connection, now=None):
    now = now or datetime.now(timezone.utc)
    row = connection.execute('''SELECT period, deadline_utc, size_probs, colour_probs,
        shadow_size_probs, shadow_colour_probs, updates, actual, created_utc
        FROM category_predictions ORDER BY period DESC LIMIT 1''').fetchone()
    if row is None:
        return 'Waiting for the first recorded prediction. Start-Live-Predictions.cmd starts the learner.'
    period, deadline, sp, cp, shadow_sp, shadow_cp, updates, actual, created = row
    end = datetime.fromisoformat(deadline)
    remaining = (end-now).total_seconds()
    status = f'LIVE | {remaining:.0f} seconds remaining' if remaining > 0 else 'ROUND CLOSED | waiting for a newer forecast'
    if actual is not None:
        status = f"RESULT: {actual} ({'BIG' if actual >= 5 else 'SMALL'}) | waiting for a newer forecast"
    lines = ['WINGO LIVE PREDICTIONS', f'Period: {period}', status,
             'Confidence is an estimate, NOT a guaranteed win rate.']
    has_thousand = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='thousand_predictions'").fetchone()
    thousand = connection.execute('''SELECT model_id, learning_size, learning_colour, learning_digit,
        updates, base_size_accuracy FROM thousand_predictions WHERE period=?''', (period,)).fetchone() if has_thousand else None
    if thousand:
        model_id, size, colour, number, weight_updates, historical_accuracy = thousand
        lines += probability_lines('1000 INPUT LEARNING MODEL (experimental)', json.loads(size), json.loads(colour), json.loads(number))
        lines += ['Picks are separate target estimates.',
                  f'Frozen model historical Big/Small test: {historical_accuracy:.2%}',
                  f'New rounds used to adjust model weights: {weight_updates}']
        scores = connection.execute('''SELECT t.learning_size, t.learning_colour, t.learning_digit, p.actual
            FROM thousand_predictions t JOIN category_predictions p ON t.period=p.period
            WHERE t.model_id=? AND p.actual IS NOT NULL''', (model_id,)).fetchall()
        if scores:
            actuals = np.array([r[3] for r in scores])
            correct_size = sum(int(np.argmax(json.loads(r[0]))) == int(r[3] >= 5) for r in scores)
            correct_colour = sum(int(np.argmax(np.asarray(json.loads(r[1]))[:2] + np.asarray(json.loads(r[1]))[2:])) == r[3] % 2 for r in scores)
            correct_number = sum(int(np.argmax(json.loads(r[2]))) == r[3] for r in scores)
            lines += [f'LIVE SCORE | Big/Small {correct_size}/{len(actuals)} ({correct_size/len(actuals):.1%})',
                      f'LIVE SCORE | Colour {correct_colour}/{len(actuals)} | Number {correct_number}/{len(actuals)}']
        else:
            lines += ['LIVE SCORE | Waiting for the first completed 1000-input forecast.']
        lines += ['Seed status: NOT recovered. These are statistical forecasts.',
                  'Ctrl+C closes this viewer. Live learning continues.']
        return '\n'.join(lines)
    digit = connection.execute('SELECT main_probs, shadow_probs FROM digit_predictions WHERE period=?', (period,)).fetchone()
    adaptive = connection.execute('SELECT digit_probs FROM adaptive_predictions WHERE period=?', (period,)).fetchone()
    if adaptive:
        p = categories(np.array(json.loads(adaptive[0])))
        lines += probability_lines('PATTERN LEARNER (experimental)', p['size'], p['colour'], p['digit']) + ['']
    lines += probability_lines('LEARNING NEURAL MODEL', json.loads(shadow_sp), json.loads(shadow_cp),
                               json.loads(digit[1]) if digit else None, compact=bool(adaptive))
    lines += probability_lines('REFERENCE NEURAL MODEL', json.loads(sp), json.loads(cp),
                               json.loads(digit[0]) if digit else None, compact=True)
    lines += [f'Neural updates: {updates} | Ctrl+C closes only this viewer.']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    path = ROOT / 'results/category_predictions.sqlite3'
    try:
        while True:
            try:
                with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=2)) as connection:
                    connection.execute('BEGIN')
                    output = render(connection)
            except sqlite3.Error as exc:
                output = f'Waiting for saved live predictions: {exc}\nUse Start-Live-Predictions.cmd to start learning.'
            if not args.once:
                os.system('cls' if os.name == 'nt' else 'clear')
            print(output, flush=True)
            if args.once:
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print('\nViewer closed. Learning continues in the background.')


if __name__ == '__main__':
    main()
