"""
TOMATOES Market Microstructure Analysis
Analyzes round0 data for exploitable patterns.
"""
import pandas as pd
import numpy as np
from collections import Counter

# Load data
dfs = []
for day in [-2, -1]:
    path = f"/Users/evantobias/repos/buenotraders-prosperity-imc/evan/data/round0/prices_round_0_day_{day}.csv"
    df = pd.read_csv(path, sep=";")
    dfs.append(df)
data = pd.concat(dfs, ignore_index=True)

# Filter TOMATOES only
tom = data[data["product"] == "TOMATOES"].copy().reset_index(drop=True)
print(f"Total TOMATOES rows: {len(tom)}")
print(f"Days: {tom['day'].unique()}")
print(f"Timestamp range: {tom['timestamp'].min()} to {tom['timestamp'].max()}")
print()

# Derived columns
tom["spread"] = tom["ask_price_1"] - tom["bid_price_1"]
tom["mid_price_calc"] = (tom["bid_price_1"] + tom["ask_price_1"]) / 2
tom["mid_change"] = tom["mid_price"].diff()
tom["bid_change"] = tom["bid_price_1"].diff()
tom["ask_change"] = tom["ask_price_1"].diff()
tom["total_bid_vol"] = tom["bid_volume_1"].fillna(0) + tom["bid_volume_2"].fillna(0) + tom["bid_volume_3"].fillna(0)
tom["total_ask_vol"] = tom["ask_volume_1"].fillna(0) + tom["ask_volume_2"].fillna(0) + tom["ask_volume_3"].fillna(0)
tom["vol_imbalance"] = tom["total_bid_vol"] - tom["total_ask_vol"]
tom["vol_imbalance_l1"] = tom["bid_volume_1"] - tom["ask_volume_1"]

# ============================================================
# 1. DISTRIBUTION OF BOT BID/ASK VOLUMES AT EACH LEVEL
# ============================================================
print("=" * 70)
print("1. VOLUME DISTRIBUTION BY LEVEL")
print("=" * 70)

for side in ["bid", "ask"]:
    for level in [1, 2, 3]:
        col = f"{side}_volume_{level}"
        vals = tom[col].dropna()
        if len(vals) == 0:
            print(f"  {col}: ALL NaN")
            continue
        print(f"\n  {col}:")
        print(f"    count={len(vals)}, min={vals.min()}, max={vals.max()}, "
              f"mean={vals.mean():.2f}, median={vals.median():.1f}, std={vals.std():.2f}")
        vc = vals.value_counts().sort_index()
        print(f"    Value counts (top 20): {dict(vc.head(20))}")

# Check if level 2 and 3 volumes are always the same
print("\n  --- Level 2 vs Level 3 comparison ---")
has_l3_bid = tom["bid_volume_3"].notna()
has_l3_ask = tom["ask_volume_3"].notna()
print(f"  Rows with bid level 3: {has_l3_bid.sum()} / {len(tom)}")
print(f"  Rows with ask level 3: {has_l3_ask.sum()} / {len(tom)}")

if has_l3_bid.sum() > 0:
    both_bid = tom[has_l3_bid]
    same_bid = (both_bid["bid_volume_2"] == both_bid["bid_volume_3"]).mean()
    print(f"  bid_vol_2 == bid_vol_3: {same_bid*100:.1f}%")
if has_l3_ask.sum() > 0:
    both_ask = tom[has_l3_ask]
    same_ask = (both_ask["ask_volume_2"] == both_ask["ask_volume_3"]).mean()
    print(f"  ask_vol_2 == ask_vol_3: {same_ask*100:.1f}%")

# Check relationship between L1 and L2 volumes
print("\n  --- L1 vs L2 relationship ---")
ratio_bid = (tom["bid_volume_2"] / tom["bid_volume_1"]).dropna()
ratio_ask = (tom["ask_volume_2"] / tom["ask_volume_1"]).dropna()
print(f"  bid_vol_2 / bid_vol_1: mean={ratio_bid.mean():.3f}, std={ratio_bid.std():.3f}, "
      f"min={ratio_bid.min():.3f}, max={ratio_bid.max():.3f}")
print(f"  ask_vol_2 / ask_vol_1: mean={ratio_ask.mean():.3f}, std={ratio_ask.std():.3f}, "
      f"min={ratio_ask.min():.3f}, max={ratio_ask.max():.3f}")

# Check if bid_volume matches ask_volume at same level
print("\n  --- Bid vs Ask volume symmetry ---")
same_l1 = (tom["bid_volume_1"] == tom["ask_volume_1"]).mean()
same_l2 = (tom["bid_volume_2"] == tom["ask_volume_2"]).mean()
print(f"  bid_vol_1 == ask_vol_1: {same_l1*100:.1f}%")
print(f"  bid_vol_2 == ask_vol_2: {same_l2*100:.1f}%")

# ============================================================
# 2. TIGHT SPREAD PATTERNS
# ============================================================
print("\n" + "=" * 70)
print("2. SPREAD ANALYSIS & TIGHT SPREAD PATTERNS")
print("=" * 70)

spread_vc = tom["spread"].value_counts().sort_index()
print(f"\n  Spread distribution:")
for s, c in spread_vc.items():
    pct = c / len(tom) * 100
    print(f"    spread={s}: {c} ({pct:.1f}%)")

# Tight spreads (< 10)
tight = tom[tom["spread"] < 10].copy()
print(f"\n  Tight spread (<10) rows: {len(tight)} / {len(tom)} = {len(tight)/len(tom)*100:.1f}%")

if len(tight) > 0:
    print(f"\n  Tight spread timestamps (first 30):")
    for _, row in tight.head(30).iterrows():
        print(f"    day={row['day']}, ts={row['timestamp']}, spread={row['spread']}, "
              f"mid={row['mid_price']}, bid1={row['bid_price_1']}, ask1={row['ask_price_1']}")

    # Check if tight spreads cluster
    tight_ts = tight["timestamp"].values
    tight_days = tight["day"].values
    diffs = []
    for i in range(1, len(tight_ts)):
        if tight_days[i] == tight_days[i-1]:
            diffs.append(tight_ts[i] - tight_ts[i-1])
    if diffs:
        diffs = np.array(diffs)
        print(f"\n  Time between consecutive tight spreads (same day):")
        print(f"    mean={diffs.mean():.1f}, median={np.median(diffs):.1f}, "
              f"std={diffs.std():.1f}, min={diffs.min()}, max={diffs.max()}")
        diff_vc = Counter(diffs)
        print(f"    Most common gaps: {diff_vc.most_common(10)}")

    # Periodicity check
    print(f"\n  Tight spread by time bucket (1000-tick bins):")
    tight["time_bucket"] = (tight["timestamp"] // 1000) * 1000
    bucket_counts = tight.groupby(["day", "time_bucket"]).size()
    print(f"    {bucket_counts.describe()}")

# ============================================================
# 3. AUTOCORRELATION OF MID-PRICE CHANGES
# ============================================================
print("\n" + "=" * 70)
print("3. AUTOCORRELATION OF MID-PRICE CHANGES")
print("=" * 70)

for day_val in tom["day"].unique():
    day_data = tom[tom["day"] == day_val].copy()
    mc = day_data["mid_change"].dropna()
    print(f"\n  Day {day_val} (n={len(mc)}):")
    print(f"    mid_change: mean={mc.mean():.4f}, std={mc.std():.4f}")

    for lag in [1, 2, 3, 4, 5, 10, 20, 50]:
        if lag < len(mc):
            ac = mc.autocorr(lag=lag)
            print(f"    lag-{lag}: {ac:.4f}")

# Combined
mc_all = tom["mid_change"].dropna()
print(f"\n  Combined (n={len(mc_all)}):")
for lag in [1, 2, 3, 4, 5, 10, 20, 50, 100]:
    if lag < len(mc_all):
        ac = mc_all.autocorr(lag=lag)
        print(f"    lag-{lag}: {ac:.4f}")

# Also check autocorrelation of RETURNS (not changes)
tom["return"] = tom["mid_price"].pct_change()
ret = tom["return"].dropna()
print(f"\n  Return autocorrelation (combined):")
for lag in [1, 2, 3, 4, 5, 10, 20]:
    ac = ret.autocorr(lag=lag)
    print(f"    lag-{lag}: {ac:.4f}")

# ============================================================
# 4. VOLUME IMBALANCE -> NEXT PRICE MOVE
# ============================================================
print("\n" + "=" * 70)
print("4. VOLUME IMBALANCE vs NEXT PRICE MOVE")
print("=" * 70)

tom["next_mid_change"] = tom["mid_change"].shift(-1)

# Level 1 imbalance
for day_val in tom["day"].unique():
    day_data = tom[tom["day"] == day_val].dropna(subset=["next_mid_change", "vol_imbalance_l1"])

    corr_l1 = day_data["vol_imbalance_l1"].corr(day_data["next_mid_change"])
    corr_total = day_data["vol_imbalance"].corr(day_data["next_mid_change"])
    print(f"\n  Day {day_val}:")
    print(f"    corr(L1 imbalance, next_mid_change) = {corr_l1:.4f}")
    print(f"    corr(total imbalance, next_mid_change) = {corr_total:.4f}")

# Bin the imbalance and look at average next move
valid = tom.dropna(subset=["next_mid_change", "vol_imbalance_l1"]).copy()
valid["imb_bin"] = pd.cut(valid["vol_imbalance_l1"], bins=20)
imb_stats = valid.groupby("imb_bin", observed=True)["next_mid_change"].agg(["mean", "std", "count"])
print(f"\n  L1 Imbalance bins -> avg next mid change:")
for idx, row in imb_stats.iterrows():
    if row["count"] > 5:
        print(f"    {idx}: mean={row['mean']:.4f}, std={row['std']:.4f}, n={int(row['count'])}")

# Also: does L1 volume SIZE predict volatility?
valid["abs_next_change"] = valid["next_mid_change"].abs()
corr_vol_size = valid["bid_volume_1"].corr(valid["abs_next_change"])
print(f"\n  corr(bid_vol_1, |next_mid_change|) = {corr_vol_size:.4f}")

# Volume ratio
valid["vol_ratio"] = valid["bid_volume_1"] / (valid["bid_volume_1"] + valid["ask_volume_1"])
corr_ratio = valid["vol_ratio"].corr(valid["next_mid_change"])
print(f"  corr(bid_vol_ratio, next_mid_change) = {corr_ratio:.4f}")

# Multi-step prediction
for horizon in [1, 2, 3, 5, 10]:
    tom[f"fwd_change_{horizon}"] = tom["mid_price"].shift(-horizon) - tom["mid_price"]

fwd_valid = tom.dropna(subset=["vol_imbalance_l1", "fwd_change_1", "fwd_change_5", "fwd_change_10"])
print(f"\n  Volume imbalance predicting multi-step forward changes:")
for horizon in [1, 2, 3, 5, 10]:
    col = f"fwd_change_{horizon}"
    c = fwd_valid["vol_imbalance_l1"].corr(fwd_valid[col])
    print(f"    corr(L1 imb, fwd_{horizon}) = {c:.4f}")

# ============================================================
# 5. PRICE ANCHORING
# ============================================================
print("\n" + "=" * 70)
print("5. PRICE ANCHORING ANALYSIS")
print("=" * 70)

# Mid price distribution
print(f"\n  Mid price stats:")
print(f"    mean={tom['mid_price'].mean():.2f}, std={tom['mid_price'].std():.2f}")
print(f"    min={tom['mid_price'].min()}, max={tom['mid_price'].max()}")

# Bid price anchoring
bid_vc = tom["bid_price_1"].value_counts().sort_index()
print(f"\n  Top 20 bid_price_1 values:")
for p, c in bid_vc.nlargest(20).sort_index().items():
    print(f"    {p}: {c} ({c/len(tom)*100:.1f}%)")

ask_vc = tom["ask_price_1"].value_counts().sort_index()
print(f"\n  Top 20 ask_price_1 values:")
for p, c in ask_vc.nlargest(20).sort_index().items():
    print(f"    {p}: {c} ({c/len(tom)*100:.1f}%)")

# Round number analysis
print(f"\n  Round number analysis (multiples of 10, 25, 50, 100):")
for mod in [5, 10, 25, 50]:
    bid_round = (tom["bid_price_1"] % mod == 0).mean()
    ask_round = (tom["ask_price_1"] % mod == 0).mean()
    mid_round = (tom["mid_price"] % mod == 0).mean()
    print(f"    mod {mod}: bid={bid_round*100:.1f}%, ask={ask_round*100:.1f}%, mid={mid_round*100:.1f}%")

# Price level 2 distances from level 1
tom["bid_spread_12"] = tom["bid_price_1"] - tom["bid_price_2"]
tom["ask_spread_12"] = tom["ask_price_2"] - tom["ask_price_1"]
print(f"\n  Bid L1-L2 gap: {tom['bid_spread_12'].dropna().value_counts().sort_index().to_dict()}")
print(f"  Ask L1-L2 gap: {tom['ask_spread_12'].dropna().value_counts().sort_index().to_dict()}")

# ============================================================
# 6. AVERAGE "TRADE SIZE" & TIME-OF-DAY
# ============================================================
print("\n" + "=" * 70)
print("6. VOLUME BY TIME OF DAY")
print("=" * 70)

# Volumes at L1 by time bucket
tom["time_pct"] = tom["timestamp"] / tom["timestamp"].max()
tom["time_5k"] = (tom["timestamp"] // 5000) * 5000

time_stats = tom.groupby("time_5k").agg({
    "bid_volume_1": "mean",
    "ask_volume_1": "mean",
    "spread": "mean",
    "mid_price": ["mean", "std"],
}).round(2)
print(f"\n  Volume and spread by 5000-tick window (sampled):")
print(f"  {'time':>8} | {'bid_v1':>8} | {'ask_v1':>8} | {'spread':>8} | {'mid':>10} | {'mid_std':>8}")
for i, (ts, row) in enumerate(time_stats.iterrows()):
    if i % 20 == 0:  # Print every 20th bucket
        print(f"  {ts:>8} | {row[('bid_volume_1','mean')]:>8.1f} | {row[('ask_volume_1','mean')]:>8.1f} | "
              f"{row[('spread','mean')]:>8.1f} | {row[('mid_price','mean')]:>10.1f} | {row[('mid_price','std')]:>8.2f}")

# Volume variation over time
early = tom[tom["timestamp"] < 200000]
mid_time = tom[(tom["timestamp"] >= 400000) & (tom["timestamp"] < 600000)]
late = tom[tom["timestamp"] >= 800000]
print(f"\n  Early (ts<200k): bid_v1={early['bid_volume_1'].mean():.1f}, ask_v1={early['ask_volume_1'].mean():.1f}, spread={early['spread'].mean():.1f}")
print(f"  Mid (400-600k): bid_v1={mid_time['bid_volume_1'].mean():.1f}, ask_v1={mid_time['ask_volume_1'].mean():.1f}, spread={mid_time['spread'].mean():.1f}")
print(f"  Late (ts>800k): bid_v1={late['bid_volume_1'].mean():.1f}, ask_v1={late['ask_volume_1'].mean():.1f}, spread={late['spread'].mean():.1f}")

# ============================================================
# 7. SEQUENCE OF BID/ASK CHANGES
# ============================================================
print("\n" + "=" * 70)
print("7. SEQUENCE ANALYSIS: BID vs ASK CHANGES")
print("=" * 70)

tom["bid_moved"] = tom["bid_change"] != 0
tom["ask_moved"] = tom["ask_change"] != 0

# When both move, does bid or ask move first?
# Since data is per-tick, check: in ticks where both move, direction correlation
both_moved = tom[tom["bid_moved"] & tom["ask_moved"]]
print(f"\n  Ticks where both bid and ask move: {len(both_moved)} / {len(tom)} = {len(both_moved)/len(tom)*100:.1f}%")
print(f"  Ticks where only bid moves: {(tom['bid_moved'] & ~tom['ask_moved']).sum()}")
print(f"  Ticks where only ask moves: {(~tom['bid_moved'] & tom['ask_moved']).sum()}")
print(f"  Ticks where neither moves: {(~tom['bid_moved'] & ~tom['ask_moved']).sum()}")

if len(both_moved) > 0:
    same_dir = (np.sign(both_moved["bid_change"]) == np.sign(both_moved["ask_change"])).mean()
    print(f"  When both move, same direction: {same_dir*100:.1f}%")

# Does a bid-only move predict the NEXT tick's ask move?
tom["next_ask_change"] = tom["ask_change"].shift(-1)
tom["next_bid_change"] = tom["bid_change"].shift(-1)
bid_only = tom[tom["bid_moved"] & ~tom["ask_moved"]].dropna(subset=["next_ask_change"])
if len(bid_only) > 0:
    ask_follows = (bid_only["next_ask_change"] != 0).mean()
    same_dir_follow = (np.sign(bid_only["bid_change"]) == np.sign(bid_only["next_ask_change"])).mean()
    print(f"\n  After bid-only move ({len(bid_only)} ticks):")
    print(f"    ask moves next tick: {ask_follows*100:.1f}%")
    print(f"    ask follows same direction: {same_dir_follow*100:.1f}%")

ask_only = tom[~tom["bid_moved"] & tom["ask_moved"]].dropna(subset=["next_bid_change"])
if len(ask_only) > 0:
    bid_follows = (ask_only["next_bid_change"] != 0).mean()
    same_dir_follow = (np.sign(ask_only["ask_change"]) == np.sign(ask_only["next_bid_change"])).mean()
    print(f"\n  After ask-only move ({len(ask_only)} ticks):")
    print(f"    bid moves next tick: {bid_follows*100:.1f}%")
    print(f"    bid follows same direction: {same_dir_follow*100:.1f}%")

# Transition matrix: categorize each tick's action
def categorize_tick(row):
    b = row["bid_change"] if pd.notna(row["bid_change"]) else 0
    a = row["ask_change"] if pd.notna(row["ask_change"]) else 0
    if b > 0 and a > 0: return "both_up"
    if b < 0 and a < 0: return "both_down"
    if b > 0 and a == 0: return "bid_up"
    if b < 0 and a == 0: return "bid_down"
    if b == 0 and a > 0: return "ask_up"
    if b == 0 and a < 0: return "ask_down"
    if b == 0 and a == 0: return "none"
    return "mixed"

tom["tick_type"] = tom.apply(categorize_tick, axis=1)
tom["next_tick_type"] = tom["tick_type"].shift(-1)

print(f"\n  Tick type distribution:")
tt_vc = tom["tick_type"].value_counts()
for t, c in tt_vc.items():
    print(f"    {t}: {c} ({c/len(tom)*100:.1f}%)")

# Transition probabilities
print(f"\n  Transition matrix (row=current, col=next, showing P(next|current)):")
trans = pd.crosstab(tom["tick_type"], tom["next_tick_type"], normalize="index")
print(trans.round(3).to_string())

# ============================================================
# 8. OPTIMAL SPREAD: MARKET-MAKING SIMULATION
# ============================================================
print("\n" + "=" * 70)
print("8. OPTIMAL SPREAD: MARKET-MAKING SIMULATION")
print("=" * 70)

print("""
  Model: At each tick, place bid at mid - spread/2 and ask at mid + spread/2.
  A fill occurs when:
    - Our bid >= best ask (we buy when our price is at or above the ask)
    - Our ask <= best bid (we sell when our price is at or below the bid)

  Actually, let's model it more realistically:
    - We place orders at (round(mid - half_spread), round(mid + half_spread))
    - Bot fills us if our bid >= bot's ask_price_1 (we buy at our bid price)
    - Bot fills us if our ask <= bot's bid_price_1 (we sell at our ask price)

  But we also need to consider position management.
  For simplicity: assume we can always trade, track PnL from round-trip trades.
""")

results = []
for half_spread in np.arange(0.5, 15.5, 0.5):
    total_pnl = 0
    total_buys = 0
    total_sells = 0
    position = 0
    pos_limit = 50

    for _, row in tom.iterrows():
        mid = row["mid_price"]
        our_bid = int(round(mid - half_spread))
        our_ask = int(round(mid + half_spread))

        bot_ask = row["ask_price_1"]
        bot_bid = row["bid_price_1"]
        bot_ask_vol = row["ask_volume_1"]
        bot_bid_vol = row["bid_volume_1"]

        # Can we buy? Our bid >= bot's ask (we're willing to pay at least what they're asking)
        if our_bid >= bot_ask and position < pos_limit:
            buy_qty = min(int(bot_ask_vol), pos_limit - position)
            if buy_qty > 0:
                position += buy_qty
                total_pnl -= our_bid * buy_qty  # We pay our bid price
                total_buys += buy_qty

        # Can we sell? Our ask <= bot's bid (they're willing to pay at least what we're asking)
        if our_ask <= bot_bid and position > -pos_limit:
            sell_qty = min(int(bot_bid_vol), position + pos_limit)
            if sell_qty > 0:
                position -= sell_qty
                total_pnl += our_ask * sell_qty  # We receive our ask price
                total_sells += sell_qty

    # Mark to market remaining position
    final_mid = tom.iloc[-1]["mid_price"]
    total_pnl += position * final_mid

    results.append({
        "half_spread": half_spread,
        "spread": half_spread * 2,
        "total_pnl": total_pnl,
        "total_buys": total_buys,
        "total_sells": total_sells,
        "total_trades": total_buys + total_sells,
    })

results_df = pd.DataFrame(results)
print(f"\n  {'Spread':>8} | {'PnL':>12} | {'Buys':>8} | {'Sells':>8} | {'Trades':>8}")
print(f"  {'-'*8} | {'-'*12} | {'-'*8} | {'-'*8} | {'-'*8}")
for _, r in results_df.iterrows():
    print(f"  {r['spread']:>8.1f} | {r['total_pnl']:>12.0f} | {r['total_buys']:>8.0f} | {r['total_sells']:>8.0f} | {r['total_trades']:>8.0f}")

best = results_df.loc[results_df["total_pnl"].idxmax()]
print(f"\n  OPTIMAL: spread={best['spread']:.1f}, PnL={best['total_pnl']:.0f}, trades={best['total_trades']:.0f}")

# ============================================================
# 8b. ALTERNATIVE: Track spread edge per trade
# ============================================================
print("\n" + "=" * 70)
print("8b. PER-TRADE EDGE ANALYSIS")
print("=" * 70)

# For each tick, what's the max edge we could capture?
print("\n  If we could trade at mid, what's the average spread we'd capture?")
print(f"  Average half-spread (to buy at ask or sell at bid):")
print(f"    avg (ask1 - mid) = {(tom['ask_price_1'] - tom['mid_price']).mean():.2f}")
print(f"    avg (mid - bid1) = {(tom['mid_price'] - tom['bid_price_1']).mean():.2f}")

# Edge from quoting at exactly the L1 prices
print(f"\n  If we match L1 prices:")
print(f"    avg spread captured per round-trip = {tom['spread'].mean():.2f}")
print(f"    but we only get filled when price crosses our level...")

# ============================================================
# 9. BONUS: REGIME DETECTION
# ============================================================
print("\n" + "=" * 70)
print("9. BONUS: REGIME DETECTION")
print("=" * 70)

# Rolling volatility
window = 50
tom["rolling_vol"] = tom["mid_change"].rolling(window).std()
tom["rolling_mean_change"] = tom["mid_change"].rolling(window).mean()

# Identify high-vol vs low-vol regimes
vol_median = tom["rolling_vol"].median()
high_vol = tom[tom["rolling_vol"] > vol_median * 1.5]
low_vol = tom[tom["rolling_vol"] < vol_median * 0.5]
print(f"\n  Rolling vol ({window}-tick window):")
print(f"    median={vol_median:.4f}")
print(f"    High-vol ticks (>1.5x median): {len(high_vol)} ({len(high_vol)/len(tom)*100:.1f}%)")
print(f"    Low-vol ticks (<0.5x median): {len(low_vol)} ({len(low_vol)/len(tom)*100:.1f}%)")

# Spread in different vol regimes
if len(high_vol) > 0 and len(low_vol) > 0:
    print(f"    High-vol avg spread: {high_vol['spread'].mean():.2f}")
    print(f"    Low-vol avg spread: {low_vol['spread'].mean():.2f}")

# ============================================================
# 10. BONUS: MID-PRICE MEAN REVERSION TEST
# ============================================================
print("\n" + "=" * 70)
print("10. BONUS: MEAN REVERSION TEST")
print("=" * 70)

# Compute rolling mean of mid price
for window in [20, 50, 100, 200]:
    tom[f"ma_{window}"] = tom["mid_price"].rolling(window).mean()
    tom[f"dev_{window}"] = tom["mid_price"] - tom[f"ma_{window}"]

    valid_dev = tom.dropna(subset=[f"dev_{window}", "fwd_change_5", "fwd_change_10"])
    corr_5 = valid_dev[f"dev_{window}"].corr(valid_dev["fwd_change_5"])
    corr_10 = valid_dev[f"dev_{window}"].corr(valid_dev["fwd_change_10"])
    print(f"  MA-{window} deviation vs forward change:")
    print(f"    corr with fwd_5  = {corr_5:.4f}")
    print(f"    corr with fwd_10 = {corr_10:.4f}")

# ============================================================
# 11. BONUS: PRICE CHANGE MAGNITUDE DISTRIBUTION
# ============================================================
print("\n" + "=" * 70)
print("11. BONUS: PRICE CHANGE MAGNITUDE DISTRIBUTION")
print("=" * 70)

mc = tom["mid_change"].dropna()
print(f"\n  Mid-price change distribution:")
mc_vc = mc.value_counts().sort_index()
for val, cnt in mc_vc.items():
    if cnt > 5:
        print(f"    {val:>6.1f}: {cnt:>5} ({cnt/len(mc)*100:.1f}%)")

print(f"\n  Bid change distribution:")
bc = tom["bid_change"].dropna()
bc_vc = bc.value_counts().sort_index()
for val, cnt in bc_vc.items():
    if cnt > 5:
        print(f"    {val:>6.1f}: {cnt:>5} ({cnt/len(bc)*100:.1f}%)")

print(f"\n  Ask change distribution:")
ac = tom["ask_change"].dropna()
ac_vc = ac.value_counts().sort_index()
for val, cnt in ac_vc.items():
    if cnt > 5:
        print(f"    {val:>6.1f}: {cnt:>5} ({cnt/len(ac)*100:.1f}%)")

# ============================================================
# SUMMARY
# ============================================================
print("\n" + "=" * 70)
print("SUMMARY OF KEY FINDINGS")
print("=" * 70)
print("""
  Review the output above for exploitable patterns. Key things to check:
  - Autocorrelation: negative lag-1 = mean reversion, positive = momentum
  - Volume imbalance correlation: if significant, use as signal
  - Tight spread clustering: if predictable, widen/tighten our quotes
  - Sequence patterns: if bid leads ask, use as leading indicator
  - Optimal spread: use for market-making parameters
""")
