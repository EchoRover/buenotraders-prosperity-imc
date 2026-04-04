"""Analyze TOMATOES price data to fit AR(1-4) models and find optimal coefficients"""

import csv
import numpy as np

# Read the price data
def read_prices(filepath):
    mids = []
    with open(filepath, 'r') as f:
        reader = csv.reader(f, delimiter=';')
        header = next(reader)
        for row in reader:
            if row[2] == 'TOMATOES':
                mid = float(row[15])  # mid_price column
                mids.append(mid)
    return np.array(mids)

day_m2 = read_prices('prosperity_rust_backtester/datasets/tutorial/prices_round_0_day_-2.csv')
day_m1 = read_prices('prosperity_rust_backtester/datasets/tutorial/prices_round_0_day_-1.csv')

# Also compute filtered mid (vol >= 15)
def read_filtered_mids(filepath, advol=16):
    mids = []
    with open(filepath, 'r') as f:
        reader = csv.reader(f, delimiter=';')
        header = next(reader)
        for row in reader:
            if row[2] == 'TOMATOES':
                # Parse bid/ask levels (3,4 / 5,6 / 7,8 for bids; 9,10 / 11,12 / 13,14 for asks)
                bids = []
                asks = []
                for i in range(3):
                    bp = row[3 + i*2]
                    bv = row[4 + i*2]
                    if bp and bv:
                        bids.append((int(bp), int(bv)))
                    ap = row[9 + i*2]
                    av = row[10 + i*2]
                    if ap and av:
                        asks.append((int(ap), int(av)))

                # Filtered mid
                fb = None
                for p, v in sorted(bids, key=lambda x: -x[0]):
                    if v >= advol:
                        fb = p
                        break
                fa = None
                for p, v in sorted(asks, key=lambda x: x[0]):
                    if v >= advol:
                        fa = p
                        break

                if fb is None and bids:
                    fb = max(b[0] for b in bids)
                if fa is None and asks:
                    fa = min(a[0] for a in asks)

                if fb is not None and fa is not None:
                    mids.append((fb + fa) / 2)
                else:
                    mids.append(float(row[15]))  # fallback to mid
    return np.array(mids)

fmid_m2 = read_filtered_mids('prosperity_rust_backtester/datasets/tutorial/prices_round_0_day_-2.csv')
fmid_m1 = read_filtered_mids('prosperity_rust_backtester/datasets/tutorial/prices_round_0_day_-1.csv')

print(f"Day -2: {len(day_m2)} TOMATOES ticks, price range [{day_m2.min():.0f}, {day_m2.max():.0f}]")
print(f"Day -1: {len(day_m1)} TOMATOES ticks, price range [{day_m1.min():.0f}, {day_m1.max():.0f}]")
print(f"Day -2 filtered: {len(fmid_m2)} ticks, range [{fmid_m2.min():.1f}, {fmid_m2.max():.1f}]")
print(f"Day -1 filtered: {len(fmid_m1)} ticks, range [{fmid_m1.min():.1f}, {fmid_m1.max():.1f}]")

# Combine both days for more robust estimates
all_mids = np.concatenate([fmid_m2, fmid_m1])

# Returns
returns = np.diff(all_mids) / all_mids[:-1]

# Autocorrelation at different lags
print(f"\n=== AUTOCORRELATION OF FILTERED MID RETURNS ===")
for lag in range(1, 11):
    if len(returns) > lag:
        corr = np.corrcoef(returns[lag:], returns[:-lag])[0, 1]
        print(f"  Lag {lag}: {corr:+.4f}")

# AR(1) model: r_t = alpha * r_{t-1} + epsilon
# This is what our reversion beta captures
print(f"\n=== AR(1) MODEL ===")
X = returns[:-1].reshape(-1, 1)
y = returns[1:]
beta = np.linalg.lstsq(X, y, rcond=None)[0][0]
print(f"  AR(1) coefficient: {beta:+.4f}")
print(f"  (our reversion_beta = -0.229, this is {beta:+.4f})")

# AR(2) model: r_t = a1 * r_{t-1} + a2 * r_{t-2} + epsilon
print(f"\n=== AR(2) MODEL ===")
X2 = np.column_stack([returns[1:-1], returns[:-2]])
y2 = returns[2:]
beta2 = np.linalg.lstsq(X2, y2, rcond=None)[0]
print(f"  AR(2) coefficients: lag1={beta2[0]:+.4f}, lag2={beta2[1]:+.4f}")

# AR(4) model
print(f"\n=== AR(4) MODEL ===")
X4 = np.column_stack([returns[3:-1], returns[2:-2], returns[1:-3], returns[:-4]])
y4 = returns[4:]
beta4 = np.linalg.lstsq(X4, y4, rcond=None)[0]
print(f"  AR(4) coefficients: lag1={beta4[0]:+.4f}, lag2={beta4[1]:+.4f}, lag3={beta4[2]:+.4f}, lag4={beta4[3]:+.4f}")

# Prediction accuracy for each model
print(f"\n=== DIRECTIONAL PREDICTION ACCURACY ===")
for name, X_use, y_use, betas in [
    ("AR(1)", X, y, [beta]),
    ("AR(2)", X2, y2, beta2),
    ("AR(4)", X4, y4, beta4),
]:
    pred = X_use @ np.array(betas)
    # How often does predicted direction match actual direction?
    correct = np.sum(np.sign(pred) == np.sign(y_use))
    total = len(y_use)
    nonzero = np.sum(y_use != 0)
    acc = correct / total * 100
    print(f"  {name}: {correct}/{total} = {acc:.1f}% (on {nonzero} non-zero moves)")

# Level-based AR model: predict price level, not returns
print(f"\n=== LEVEL AR(4) MODEL (price levels) ===")
X4_lvl = np.column_stack([all_mids[3:-1], all_mids[2:-2], all_mids[1:-3], all_mids[:-4]])
y4_lvl = all_mids[4:]
beta4_lvl = np.linalg.lstsq(X4_lvl, y4_lvl, rcond=None)[0]
print(f"  Level AR(4): w1={beta4_lvl[0]:.4f}, w2={beta4_lvl[1]:.4f}, w3={beta4_lvl[2]:.4f}, w4={beta4_lvl[3]:.4f}")
print(f"  Sum of weights: {sum(beta4_lvl):.4f}")

# What's the distribution of 1-tick price changes?
changes = np.diff(all_mids)
print(f"\n=== PRICE CHANGE DISTRIBUTION (filtered mid) ===")
print(f"  Mean: {changes.mean():+.3f}")
print(f"  Std: {changes.std():.3f}")
print(f"  Skew: {float(np.mean(((changes - changes.mean()) / changes.std())**3)):.3f}")
print(f"  Changes == 0: {np.sum(changes == 0)} ({np.sum(changes == 0)/len(changes)*100:.1f}%)")
print(f"  Changes != 0: {np.sum(changes != 0)} ({np.sum(changes != 0)/len(changes)*100:.1f}%)")
for delta in [-3, -2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2, 3]:
    count = np.sum(changes == delta)
    pct = count / len(changes) * 100
    if count > 0:
        print(f"    Δ={delta:+.1f}: {count} ({pct:.1f}%)")

# Regime analysis: separate trending vs mean-reverting periods
print(f"\n=== REGIME ANALYSIS ===")
# Rolling 20-tick volatility
for window in [10, 20, 50, 100]:
    vols = [np.std(changes[max(0,i-window):i]) for i in range(window, len(changes))]
    print(f"  {window}-tick rolling vol: mean={np.mean(vols):.3f}, std={np.std(vols):.3f}, min={np.min(vols):.3f}, max={np.max(vols):.3f}")

# Conditional reversion: is reversion stronger after big moves?
print(f"\n=== CONDITIONAL REVERSION STRENGTH ===")
abs_changes = np.abs(changes[:-1])
next_changes = changes[1:]
for threshold_pct in [0, 25, 50, 75, 90]:
    threshold = np.percentile(abs_changes, threshold_pct)
    mask = abs_changes >= threshold
    if np.sum(mask) > 10:
        same_dir = np.sum(np.sign(changes[:-1][mask]) == np.sign(next_changes[mask]))
        rev_dir = np.sum(np.sign(changes[:-1][mask]) == -np.sign(next_changes[mask]))
        total = np.sum(mask & (next_changes != 0))
        pct_rev = rev_dir / max(1, total) * 100
        print(f"  |Δ| >= {threshold:.2f} ({100-threshold_pct}th pctile): n={np.sum(mask)}, reversion={pct_rev:.1f}%")

# OBI signal analysis
print(f"\n=== ORDER BOOK IMBALANCE ANALYSIS ===")
# We'd need the full book for this — skip for now
print("  (requires full book data, skipping)")
