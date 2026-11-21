import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
(ROOT / "results").mkdir(exist_ok=True)


def run(script):
    r = subprocess.run([sys.executable, str(ROOT / "src" / script)], cwd=ROOT, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", env=ENV)
    (ROOT / "results" / f"last_{script}.txt").write_text(r.stdout + r.stderr, encoding="utf-8")
    return r


def from_marker(text, marker):
    i = text.find(marker)
    return text[i:].strip() if i >= 0 else "(marker not found, see results folder)"


def keep_lines(text, words):
    return "\n".join(l for l in text.splitlines() if any(w in l for w in words))


print("=" * 60, "\nSTEP 1: prepare data\n" + "=" * 60)
r = run("prepare_data.py")
print(keep_lines(r.stdout, ["Using file", "Rows loaded", "Duplicate", "Colour values", "differs", "Days:", "Block sizes",
                            "Total clean", "WARNING", "STOP"]))
if r.returncode != 0:
    print(r.stdout[-1500:], r.stderr[-1500:])
    raise SystemExit("\nStopped: fix the problem above first.")

print("\n" + "=" * 60, "\nSTEP 2: digit health check (misread digits)\n" + "=" * 60)
r = run("check_digits.py")
print(keep_lines(r.stdout, ["CHECK", "Chunks checked"]) if r.returncode == 0 else r.stderr[-800:])

print("\n" + "=" * 60, "\nSTEP 3: 45 pattern tests on all rounds\n" + "=" * 60)
r = run("analyze_all.py")
print(from_marker(r.stdout, "=== Summary ===") if r.returncode == 0 else r.stderr[-800:])

print("\n" + "=" * 60, "\nSTEP 4: models tested walk-forward on all rounds\n" + "=" * 60)
r = run("walk_forward.py")
print(from_marker(r.stdout, "=== Verdict ===") if r.returncode == 0 else r.stderr[-800:])

print("\n" + "=" * 60, "\nSTEP 5: frozen models on FRESH rounds\n" + "=" * 60)
r = run("score_frozen.py")
if r.returncode == 0:
    print(from_marker(r.stdout, "=== Big or Small"))
else:
    print(keep_lines(r.stdout + r.stderr, ["Frozen model", "Trained on", "Strong models", "Fresh rounds", "STOP"]))

print("\nFull outputs are saved in the results folder (last_*.txt).")
