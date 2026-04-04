"""
Comprehensive TOMATOES market microstructure analysis.
7 sections: taker events, bot patterns, volume asymmetry, L2 info, trades, spread dynamics, price sequences.
"""
import pandas as pd
import numpy as np
from collections import Counter

# ── Load data ──────────────────────────────────────────────────────────────
prices_path = "/Users/evantobias/repos/buenotraders-prosperity-imc/evan/prosperity_rust_backtester/datasets/tutorial/prices_round_0_day_-1.csv"
trades_path = "/Users/evantobias/repos/buenotraders-prosperity-imc/evan/prosperity_rust_backtester/datasets/tutorial/trades_round_0_day_-1.csv"

df = pd.read_csv(prices_path, sep=";")
df_trades = pd.read_csv(trades_path, sep=";")

# Filter TOMATOES only
tom = df[df["product"] == "TOMATOES"].copy().reset_index(drop=True)
tom_trades = df_trades[df_trades["symbol"] == "TOMATOES"].copy().reset_index(drop=True)

print(f"TOMATOES price ticks: {len(tom)}")
print(f"TOMATOES trades: {len(tom_trades)}")
print(f"Timestamp range: {tom['timestamp'].min()} to {tom['timestamp'].max()}")
print(f"Timestamp step: {tom['timestamp'].diff().dropna().value_counts().head()}")
print()

# Derived columns
tom["spread"] = tom["ask_price_1"] - tom["bid_price_1"]
tom["mid"] = (tom["bid_price_1"] + tom["ask_price_1"]) / 2
tom["mid_change"] = tom["mid"].diff()
tom["bid_change"] = tom["bid_price_1"].diff()
tom["ask_change"] = tom["ask_price_1"].diff()
tom["vol_imbalance"] = tom["bid_volume_1"] - tom["ask_volume_1"]
tom["vol_ratio"] = tom["bid_volume_1"] / (tom["bid_volume_1"] + tom["ask_volume_1"])

# ══════════════════════════════════════════════════════════════════════════
# 1. TAKER EVENT DETECTION
# ══════════════════════════════════════════════════════════════════════════
print("=" * 80)
print("1. TAKER EVENT DETECTION")
print("=" * 80)

spread_counts = tom["spread"].value_counts().sort_index()
print(f"\nSpread distribution:")
for s, c in spread_counts.items():
    print(f"  Spread={s}: {c} ticks ({100*c/len(tom):.1f}%)")

# Define taker events: spread < 14 (normal is 13-14)
# Actually let's look at spread transitions
print(f"\nNormal spread range: {tom['spread'].quantile(0.25):.0f} - {tom['spread'].quantile(0.75):.0f}")
print(f"Mean spread: {tom['spread'].mean():.2f}")
print(f"Spread < 14 ticks: {(tom['spread'] < 14).sum()} ({100*(tom['spread'] < 14).mean():.1f}%)")
print(f"Spread == 13 ticks: {(tom['spread'] == 13).sum()} ({100*(tom['spread'] == 13).mean():.1f}%)")
print(f"Spread <= 12 ticks: {(tom['spread'] <= 12).sum()} ({100*(tom['spread'] <= 12).mean():.1f}%)")

# What happens to mid_price AFTER spread compression?
# Look at ticks where spread narrows
tom["spread_narrowed"] = tom["spread"].diff() < 0  # spread got tighter
tom["spread_widened"] = tom["spread"].diff() > 0

for horizon in [1, 2, 3, 5, 10]:
    tom[f"mid_fwd_{horizon}"] = tom["mid"].shift(-horizon) - tom["mid"]

print(f"\n--- After spread NARROWS (tighter book) ---")
narrowed = tom[tom["spread_narrowed"]]
print(f"  Count: {len(narrowed)}")
for h in [1, 2, 3, 5, 10]:
    col = f"mid_fwd_{h}"
    m = narrowed[col].mean()
    s = narrowed[col].std()
    print(f"  Mid change +{h} ticks: mean={m:.4f}, std={s:.4f}")

print(f"\n--- After spread WIDENS (looser book) ---")
widened = tom[tom["spread_widened"]]
print(f"  Count: {len(widened)}")
for h in [1, 2, 3, 5, 10]:
    col = f"mid_fwd_{h}"
    m = widened[col].mean()
    s = widened[col].std()
    print(f"  Mid change +{h} ticks: mean={m:.4f}, std={s:.4f}")

# More specific: what happens when bid goes UP (buy taker) vs ask goes DOWN (sell taker)
tom["bid_up"] = tom["bid_change"] > 0
tom["bid_down"] = tom["bid_change"] < 0
tom["ask_up"] = tom["ask_change"] > 0
tom["ask_down"] = tom["ask_change"] < 0

print(f"\n--- After BID moves UP (potential buy pressure) ---")
bu = tom[tom["bid_up"]]
print(f"  Count: {len(bu)}")
for h in [1, 2, 3, 5, 10]:
    col = f"mid_fwd_{h}"
    m = bu[col].mean()
    print(f"  Mid change +{h} ticks: mean={m:.4f}")

print(f"\n--- After ASK moves DOWN (potential sell pressure) ---")
ad = tom[tom["ask_down"]]
print(f"  Count: {len(ad)}")
for h in [1, 2, 3, 5, 10]:
    col = f"mid_fwd_{h}"
    m = ad[col].mean()
    print(f"  Mid change +{h} ticks: mean={m:.4f}")

print(f"\n--- After BID moves DOWN ---")
bd = tom[tom["bid_down"]]
print(f"  Count: {len(bd)}")
for h in [1, 2, 3, 5, 10]:
    col = f"mid_fwd_{h}"
    m = bd[col].mean()
    print(f"  Mid change +{h} ticks: mean={m:.4f}")

print(f"\n--- After ASK moves UP ---")
au = tom[tom["ask_up"]]
print(f"  Count: {len(au)}")
for h in [1, 2, 3, 5, 10]:
    col = f"mid_fwd_{h}"
    m = au[col].mean()
    print(f"  Mid change +{h} ticks: mean={m:.4f}")


# ══════════════════════════════════════════════════════════════════════════
# 2. BOT QUOTING PATTERN
# ══════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("2. BOT QUOTING PATTERN")
print("=" * 80)

# Track how L1 changes tick-to-tick
print(f"\nBid price changes per tick:")
bid_ch = tom["bid_change"].dropna()
print(bid_ch.value_counts().sort_index())

print(f"\nAsk price changes per tick:")
ask_ch = tom["ask_change"].dropna()
print(ask_ch.value_counts().sort_index())

# Volume patterns
print(f"\nBid volume L1 distribution:")
print(tom["bid_volume_1"].describe())
print(f"\nAsk volume L1 distribution:")
print(tom["ask_volume_1"].describe())

# Volume unique values
print(f"\nBid volume L1 unique values: {sorted(tom['bid_volume_1'].unique())}")
print(f"Ask volume L1 unique values: {sorted(tom['ask_volume_1'].unique())}")

# Check if bid_vol == ask_vol always
print(f"\nBid vol == Ask vol: {(tom['bid_volume_1'] == tom['ask_volume_1']).sum()} / {len(tom)} ({100*(tom['bid_volume_1'] == tom['ask_volume_1']).mean():.1f}%)")

# Check volume cycling
print(f"\nBid volume changes tick-to-tick:")
tom["bid_vol_change"] = tom["bid_volume_1"].diff()
print(tom["bid_vol_change"].dropna().value_counts().sort_index())

# Look for cyclic patterns in volume
print(f"\n--- Volume cycle analysis ---")
# Track sequences of volume values
vol_seq = tom["bid_volume_1"].values
# Find repeating patterns
for period in range(2, 20):
    matches = sum(1 for i in range(period, len(vol_seq)) if vol_seq[i] == vol_seq[i - period])
    total = len(vol_seq) - period
    pct = 100 * matches / total
    if pct > 30:
        print(f"  Period {period}: {pct:.1f}% match")

# Check if volume predicts next mid change
print(f"\n--- Volume level predicting next mid change ---")
for vol_val in sorted(tom["bid_volume_1"].unique()):
    subset = tom[tom["bid_volume_1"] == vol_val]
    if len(subset) > 10:
        fwd1 = subset["mid_fwd_1"].mean()
        fwd3 = subset["mid_fwd_3"].mean()
        print(f"  bid_vol={vol_val}: n={len(subset)}, fwd1_mid={fwd1:.4f}, fwd3_mid={fwd3:.4f}")

# Check if volume change predicts mid change
print(f"\n--- Volume CHANGE predicting next mid change ---")
for vc in sorted(tom["bid_vol_change"].dropna().unique()):
    subset = tom[tom["bid_vol_change"] == vc]
    if len(subset) > 10:
        fwd1 = subset["mid_fwd_1"].mean()
        fwd3 = subset["mid_fwd_3"].mean()
        print(f"  bid_vol_change={vc:.0f}: n={len(subset)}, fwd1_mid={fwd1:.4f}, fwd3_mid={fwd3:.4f}")

# Are bid/ask symmetric?
print(f"\n--- Spread composition ---")
# Where is mid relative to round numbers?
tom["mid_frac"] = tom["mid"] % 1
print(f"Mid fractional part distribution:")
print(tom["mid_frac"].value_counts().sort_index().head(10))

# Check if L2 tracks L1 deterministically
tom["l1_l2_bid_gap"] = tom["bid_price_1"] - tom["bid_price_2"]
tom["l1_l2_ask_gap"] = tom["ask_price_2"] - tom["ask_price_1"]
print(f"\nL1-L2 bid gap: {tom['l1_l2_bid_gap'].value_counts().sort_index().to_dict()}")
print(f"L1-L2 ask gap: {tom['l1_l2_ask_gap'].value_counts().sort_index().to_dict()}")

# L2 volume patterns
print(f"\nBid volume L2: {sorted(tom['bid_volume_2'].unique())}")
print(f"Ask volume L2: {sorted(tom['ask_volume_2'].unique())}")
print(f"L1/L2 bid vol ratio: {(tom['bid_volume_1'] / tom['bid_volume_2']).describe()}")


# ══════════════════════════════════════════════════════════════════════════
# 3. VOLUME ASYMMETRY (L1 imbalance)
# ══════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("3. VOLUME ASYMMETRY — L1 IMBALANCE PREDICTING DIRECTION")
print("=" * 80)

# vol_imbalance = bid_vol_1 - ask_vol_1
# vol_ratio = bid_vol_1 / (bid_vol_1 + ask_vol_1)
print(f"\nVolume imbalance (bid - ask) distribution:")
print(tom["vol_imbalance"].describe())
print(f"\nVolume imbalance value counts (top 20):")
print(tom["vol_imbalance"].value_counts().sort_index().head(30))

# Predictive power of imbalance
print(f"\n--- Imbalance quintiles vs future mid ---")
tom["imb_quintile"] = pd.qcut(tom["vol_imbalance"], 5, duplicates="drop", labels=False)
for q in sorted(tom["imb_quintile"].dropna().unique()):
    subset = tom[tom["imb_quintile"] == q]
    mean_imb = subset["vol_imbalance"].mean()
    for h in [1, 3, 5, 10]:
        fwd = subset[f"mid_fwd_{h}"].mean()
        if h == 1:
            print(f"  Q{q} (mean_imb={mean_imb:.1f}, n={len(subset)}): ", end="")
        print(f"fwd{h}={fwd:.4f}  ", end="")
    print()

# Binary signal
print(f"\n--- Binary: bid_vol > ask_vol ---")
long_sig = tom[tom["vol_imbalance"] > 0]
short_sig = tom[tom["vol_imbalance"] < 0]
flat_sig = tom[tom["vol_imbalance"] == 0]
print(f"  Bid > Ask: n={len(long_sig)}")
for h in [1, 3, 5, 10]:
    print(f"    fwd{h}: {long_sig[f'mid_fwd_{h}'].mean():.4f}")
print(f"  Bid < Ask: n={len(short_sig)}")
for h in [1, 3, 5, 10]:
    print(f"    fwd{h}: {short_sig[f'mid_fwd_{h}'].mean():.4f}")
print(f"  Bid == Ask: n={len(flat_sig)}")
for h in [1, 3, 5, 10]:
    print(f"    fwd{h}: {flat_sig[f'mid_fwd_{h}'].mean():.4f}")

# Correlation
print(f"\n--- Correlations ---")
for h in [1, 2, 3, 5, 10]:
    corr = tom["vol_imbalance"].corr(tom[f"mid_fwd_{h}"])
    print(f"  vol_imbalance vs mid_fwd_{h}: r={corr:.4f}")

# Volume ratio (normalized 0-1)
print(f"\n--- vol_ratio (bid/(bid+ask)) correlations ---")
for h in [1, 2, 3, 5, 10]:
    corr = tom["vol_ratio"].corr(tom[f"mid_fwd_{h}"])
    print(f"  vol_ratio vs mid_fwd_{h}: r={corr:.4f}")

# Combined signal: imbalance + recent price direction
tom["recent_trend"] = tom["mid"].diff(5)
tom["imb_x_trend"] = tom["vol_imbalance"] * np.sign(tom["recent_trend"])
print(f"\n--- Imbalance aligned with 5-tick trend ---")
for h in [1, 3, 5, 10]:
    corr = tom["imb_x_trend"].corr(tom[f"mid_fwd_{h}"])
    print(f"  imb_x_trend vs mid_fwd_{h}: r={corr:.4f}")


# ══════════════════════════════════════════════════════════════════════════
# 4. LEVEL 2 INFORMATION
# ══════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("4. LEVEL 2 INFORMATION")
print("=" * 80)

# L2 gap from L1
print(f"\nL1-L2 bid gap distribution:")
print(tom["l1_l2_bid_gap"].value_counts().sort_index())
print(f"\nL1-L2 ask gap distribution:")
print(tom["l1_l2_ask_gap"].value_counts().sort_index())

# When L2 is close to L1, does that predict anything?
print(f"\n--- L2 bid gap predicting direction ---")
for gap in sorted(tom["l1_l2_bid_gap"].dropna().unique()):
    subset = tom[tom["l1_l2_bid_gap"] == gap]
    if len(subset) > 10:
        for h in [1, 3, 5]:
            fwd = subset[f"mid_fwd_{h}"].mean()
            if h == 1:
                print(f"  bid_gap={gap}: n={len(subset)}, ", end="")
            print(f"fwd{h}={fwd:.4f}  ", end="")
        print()

print(f"\n--- L2 ask gap predicting direction ---")
for gap in sorted(tom["l1_l2_ask_gap"].dropna().unique()):
    subset = tom[tom["l1_l2_ask_gap"] == gap]
    if len(subset) > 10:
        for h in [1, 3, 5]:
            fwd = subset[f"mid_fwd_{h}"].mean()
            if h == 1:
                print(f"  ask_gap={gap}: n={len(subset)}, ", end="")
            print(f"fwd{h}={fwd:.4f}  ", end="")
        print()

# L2 volume imbalance
tom["l2_vol_imbalance"] = tom["bid_volume_2"] - tom["ask_volume_2"]
print(f"\n--- L2 volume imbalance ---")
print(tom["l2_vol_imbalance"].value_counts().sort_index())

print(f"\n--- L2 vol imbalance correlations ---")
for h in [1, 2, 3, 5, 10]:
    corr = tom["l2_vol_imbalance"].corr(tom[f"mid_fwd_{h}"])
    print(f"  l2_vol_imbalance vs mid_fwd_{h}: r={corr:.4f}")

# Weighted price: combine L1 and L2
tom["wprice_bid"] = (tom["bid_price_1"]*tom["bid_volume_1"] + tom["bid_price_2"]*tom["bid_volume_2"]) / (tom["bid_volume_1"] + tom["bid_volume_2"])
tom["wprice_ask"] = (tom["ask_price_1"]*tom["ask_volume_1"] + tom["ask_price_2"]*tom["ask_volume_2"]) / (tom["ask_volume_1"] + tom["ask_volume_2"])
tom["wmid"] = (tom["wprice_bid"] + tom["wprice_ask"]) / 2
tom["wmid_vs_mid"] = tom["wmid"] - tom["mid"]

print(f"\n--- Weighted mid vs simple mid (wmid - mid) ---")
print(tom["wmid_vs_mid"].describe())
for h in [1, 2, 3, 5, 10]:
    corr = tom["wmid_vs_mid"].corr(tom[f"mid_fwd_{h}"])
    print(f"  wmid_vs_mid vs mid_fwd_{h}: r={corr:.4f}")

# Filtered mid (vol >= 16) signal
tom["filtered_mid_bid"] = tom.apply(lambda r: r["bid_price_1"] if r["bid_volume_1"] >= 16 else r["bid_price_2"], axis=1)
tom["filtered_mid_ask"] = tom.apply(lambda r: r["ask_price_1"] if r["ask_volume_1"] >= 16 else r["ask_price_2"], axis=1)
tom["filtered_mid"] = (tom["filtered_mid_bid"] + tom["filtered_mid_ask"]) / 2
tom["filt_vs_mid"] = tom["filtered_mid"] - tom["mid"]

print(f"\n--- Filtered mid (vol>=16) vs simple mid ---")
print(tom["filt_vs_mid"].describe())
for h in [1, 2, 3, 5, 10]:
    corr = tom["filt_vs_mid"].corr(tom[f"mid_fwd_{h}"])
    print(f"  filt_vs_mid vs mid_fwd_{h}: r={corr:.4f}")

# Compare filtered mid to wmid as signals
tom["filt_fwd_1"] = tom["filtered_mid"].shift(-1) - tom["filtered_mid"]
print(f"\n--- Filtered mid change autocorrelation ---")
for lag in [1, 2, 3, 5]:
    ac = tom["filt_vs_mid"].autocorr(lag)
    print(f"  lag {lag}: r={ac:.4f}")

# ══════════════════════════════════════════════════════════════════════════
# 5. MARKET TRADES ANALYSIS
# ══════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("5. MARKET TRADES ANALYSIS")
print("=" * 80)

print(f"\nTotal TOMATOES trades: {len(tom_trades)}")
print(f"\nTrade prices:")
print(tom_trades["price"].describe())
print(f"\nTrade quantities:")
print(tom_trades["quantity"].describe())
print(f"\nPrice distribution:")
print(tom_trades["price"].value_counts().sort_index())

# Timing
print(f"\nTrade timestamps (first 30):")
print(tom_trades["timestamp"].values[:30])
print(f"\nTrade inter-arrival times:")
trade_gaps = tom_trades["timestamp"].diff().dropna()
print(trade_gaps.describe())
print(f"\nTrade gap distribution (top 15):")
print(trade_gaps.value_counts().sort_values(ascending=False).head(15))

# Are trades periodic?
print(f"\n--- Trade periodicity check ---")
trade_ts = tom_trades["timestamp"].values
for period in [100, 200, 500, 1000, 1500, 1600, 1700, 1800, 1900, 2000, 2500, 3000, 4000, 5000]:
    # What fraction of trades occur at timestamps that are multiples of period?
    mod = trade_ts % period
    zero_pct = 100 * np.sum(mod == 0) / len(trade_ts)
    if zero_pct > 5:
        print(f"  Period {period}: {zero_pct:.1f}% trades at exact multiples")

# Trade direction inference: compare trade price to mid at that timestamp
# Merge trades with nearest price tick
print(f"\n--- Trade direction analysis ---")
trade_directions = []
for _, trade in tom_trades.iterrows():
    ts = trade["timestamp"]
    # Find the price tick at or just before this trade
    tick = tom[tom["timestamp"] <= ts].iloc[-1] if len(tom[tom["timestamp"] <= ts]) > 0 else None
    if tick is not None:
        mid_at_trade = tick["mid"]
        if trade["price"] > mid_at_trade:
            trade_directions.append("BUY")
        elif trade["price"] < mid_at_trade:
            trade_directions.append("SELL")
        else:
            trade_directions.append("MID")
    else:
        trade_directions.append("UNKNOWN")

tom_trades["direction"] = trade_directions
print(f"Trade directions: {Counter(trade_directions)}")

# What happens to price after each trade?
print(f"\n--- Price movement after trades ---")
for direction in ["BUY", "SELL"]:
    dir_trades = tom_trades[tom_trades["direction"] == direction]
    print(f"\n  After {direction} trades (n={len(dir_trades)}):")
    fwd_changes = []
    for _, trade in dir_trades.iterrows():
        ts = trade["timestamp"]
        # Find future ticks
        future = tom[tom["timestamp"] > ts].head(10)
        current = tom[tom["timestamp"] <= ts].iloc[-1] if len(tom[tom["timestamp"] <= ts]) > 0 else None
        if current is not None and len(future) > 0:
            for h in [1, 3, 5, 10]:
                if h <= len(future):
                    fwd_changes.append({
                        "horizon": h,
                        "change": future.iloc[min(h-1, len(future)-1)]["mid"] - current["mid"]
                    })
    fwd_df = pd.DataFrame(fwd_changes)
    for h in [1, 3, 5, 10]:
        subset = fwd_df[fwd_df["horizon"] == h]
        if len(subset) > 0:
            print(f"    +{h} ticks: mean_mid_change={subset['change'].mean():.4f}, n={len(subset)}")

# Trade volume analysis
print(f"\n--- Trade quantity analysis ---")
for qty in sorted(tom_trades["quantity"].unique()):
    subset = tom_trades[tom_trades["quantity"] == qty]
    print(f"  qty={qty}: n={len(subset)}, directions={dict(Counter(subset['direction']))}")


# ══════════════════════════════════════════════════════════════════════════
# 6. SPREAD DYNAMICS — What predicts spread narrowing?
# ══════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("6. SPREAD DYNAMICS")
print("=" * 80)

tom["next_spread"] = tom["spread"].shift(-1)
tom["spread_change"] = tom["spread"].diff()
tom["next_spread_change"] = tom["spread_change"].shift(-1)

print(f"\nSpread change distribution:")
print(tom["spread_change"].dropna().value_counts().sort_index())

# What book state predicts spread narrowing?
print(f"\n--- Book state before spread narrows ---")
# Before spread narrows
narrow_next = tom[tom["next_spread_change"] < 0]
stable_next = tom[tom["next_spread_change"] == 0]
widen_next = tom[tom["next_spread_change"] > 0]

print(f"  Before NARROW (n={len(narrow_next)}):")
print(f"    avg spread: {narrow_next['spread'].mean():.2f}")
print(f"    avg bid_vol: {narrow_next['bid_volume_1'].mean():.2f}")
print(f"    avg ask_vol: {narrow_next['ask_volume_1'].mean():.2f}")
print(f"    avg vol_imb: {narrow_next['vol_imbalance'].mean():.2f}")
print(f"    avg bid_vol_change: {narrow_next['bid_vol_change'].mean():.2f}")

print(f"  Before STABLE (n={len(stable_next)}):")
print(f"    avg spread: {stable_next['spread'].mean():.2f}")
print(f"    avg bid_vol: {stable_next['bid_volume_1'].mean():.2f}")
print(f"    avg ask_vol: {stable_next['ask_volume_1'].mean():.2f}")
print(f"    avg vol_imb: {stable_next['vol_imbalance'].mean():.2f}")

print(f"  Before WIDEN (n={len(widen_next)}):")
print(f"    avg spread: {widen_next['spread'].mean():.2f}")
print(f"    avg bid_vol: {widen_next['bid_volume_1'].mean():.2f}")
print(f"    avg ask_vol: {widen_next['ask_volume_1'].mean():.2f}")
print(f"    avg vol_imb: {widen_next['vol_imbalance'].mean():.2f}")

# Does volume level predict spread change?
print(f"\n--- Volume level predicting spread change ---")
for vol in sorted(tom["bid_volume_1"].unique()):
    subset = tom[tom["bid_volume_1"] == vol]
    if len(subset) > 10:
        avg_next_sc = subset["next_spread_change"].mean()
        print(f"  bid_vol={vol}: n={len(subset)}, avg_next_spread_change={avg_next_sc:.4f}")

# Consecutive spread patterns
print(f"\n--- Spread transition matrix ---")
tom["spread_state"] = tom["spread"]
tom["next_spread_state"] = tom["spread"].shift(-1)
trans = pd.crosstab(tom["spread_state"], tom["next_spread_state"], normalize="index")
print(trans.round(3))

# Does the current spread predict future returns differently?
print(f"\n--- Returns conditioned on current spread ---")
for s in sorted(tom["spread"].unique()):
    subset = tom[tom["spread"] == s]
    if len(subset) > 20:
        abs_fwd1 = subset["mid_fwd_1"].abs().mean()
        abs_fwd3 = subset["mid_fwd_3"].abs().mean()
        print(f"  Spread={s}: n={len(subset)}, abs_fwd1={abs_fwd1:.4f}, abs_fwd3={abs_fwd3:.4f}")


# ══════════════════════════════════════════════════════════════════════════
# 7. PRICE MOVE SEQUENCES — Higher order patterns
# ══════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("7. PRICE MOVE SEQUENCES")
print("=" * 80)

# Discretize mid changes
tom["mid_dir"] = np.sign(tom["mid_change"])

print(f"\nMid change distribution:")
print(tom["mid_change"].dropna().value_counts().sort_index().head(20))

print(f"\nMid direction distribution:")
print(tom["mid_dir"].dropna().value_counts().sort_index())

# After a +1 move, what's the next non-zero move?
print(f"\n--- After +1 mid move, next non-zero move ---")
moves = tom["mid_change"].values
for trigger_move in [0.5, 1.0, -0.5, -1.0]:
    next_nonzero = []
    for i in range(len(moves) - 1):
        if moves[i] == trigger_move:
            # Look forward for next non-zero move
            for j in range(i + 1, min(i + 20, len(moves))):
                if moves[j] != 0:
                    next_nonzero.append(moves[j])
                    break
    if len(next_nonzero) > 0:
        c = Counter([round(x, 1) for x in next_nonzero])
        total = len(next_nonzero)
        up = sum(1 for x in next_nonzero if x > 0)
        down = sum(1 for x in next_nonzero if x < 0)
        print(f"  After move={trigger_move}: n={total}, up={100*up/total:.1f}%, down={100*down/total:.1f}%")
        print(f"    Distribution: {dict(sorted(c.items()))}")

# Two consecutive moves
print(f"\n--- After two consecutive same-direction moves ---")
dirs = tom["mid_dir"].values
mid_changes = tom["mid_change"].values
for d1, d2 in [(1, 1), (-1, -1), (1, -1), (-1, 1)]:
    next_nonzero = []
    for i in range(1, len(dirs) - 1):
        if dirs[i - 1] == d1 and dirs[i] == d2:
            for j in range(i + 1, min(i + 20, len(dirs))):
                if mid_changes[j] != 0:
                    next_nonzero.append(mid_changes[j])
                    break
    if len(next_nonzero) > 0:
        total = len(next_nonzero)
        up = sum(1 for x in next_nonzero if x > 0)
        down = sum(1 for x in next_nonzero if x < 0)
        mean_next = np.mean(next_nonzero)
        print(f"  After ({d1},{d2}): n={total}, up={100*up/total:.1f}%, down={100*down/total:.1f}%, mean={mean_next:.4f}")

# Autocorrelation of mid changes
print(f"\n--- Mid change autocorrelation ---")
for lag in range(1, 11):
    ac = tom["mid_change"].dropna().autocorr(lag)
    print(f"  lag {lag}: r={ac:.4f}")

# Run-length analysis
print(f"\n--- Run-length analysis (consecutive same-direction moves) ---")
runs = []
current_dir = 0
current_len = 0
for d in dirs:
    if np.isnan(d):
        continue
    if d == current_dir:
        current_len += 1
    else:
        if current_len > 0:
            runs.append((current_dir, current_len))
        current_dir = d
        current_len = 1
if current_len > 0:
    runs.append((current_dir, current_len))

# Run length distribution by direction
up_runs = [l for d, l in runs if d == 1]
down_runs = [l for d, l in runs if d == -1]
zero_runs = [l for d, l in runs if d == 0]

print(f"  Up runs: {Counter(up_runs)}")
print(f"  Down runs: {Counter(down_runs)}")
print(f"  Zero runs (no change): {Counter(zero_runs)}")

# After a run of length N, what happens?
print(f"\n--- After up-run of length N, next non-zero move ---")
for run_len in [1, 2, 3, 4, 5]:
    next_moves = []
    i = 0
    while i < len(runs) - 1:
        d, l = runs[i]
        if d == 1 and l == run_len:
            # Look at next non-zero run
            for j in range(i + 1, len(runs)):
                nd, nl = runs[j]
                if nd != 0:
                    next_moves.append(nd)
                    break
        i += 1
    if len(next_moves) > 3:
        up = sum(1 for x in next_moves if x == 1)
        down = sum(1 for x in next_moves if x == -1)
        total = len(next_moves)
        print(f"  After up-run len={run_len}: n={total}, continue_up={100*up/total:.1f}%, reverse_down={100*down/total:.1f}%")

print(f"\n--- After down-run of length N, next non-zero move ---")
for run_len in [1, 2, 3, 4, 5]:
    next_moves = []
    i = 0
    while i < len(runs) - 1:
        d, l = runs[i]
        if d == -1 and l == run_len:
            for j in range(i + 1, len(runs)):
                nd, nl = runs[j]
                if nd != 0:
                    next_moves.append(nd)
                    break
        i += 1
    if len(next_moves) > 3:
        up = sum(1 for x in next_moves if x == 1)
        down = sum(1 for x in next_moves if x == -1)
        total = len(next_moves)
        print(f"  After down-run len={run_len}: n={total}, reverse_up={100*up/total:.1f}%, continue_down={100*down/total:.1f}%")


# ══════════════════════════════════════════════════════════════════════════
# 8. BONUS: COMPOSITE SIGNALS
# ══════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("8. COMPOSITE SIGNALS & ADDITIONAL ANALYSIS")
print("=" * 80)

# How much does the reversion beta vary over time?
window = 50
tom["rolling_autocorr"] = tom["mid_change"].rolling(window).apply(
    lambda x: pd.Series(x).autocorr(1), raw=False
)
print(f"\nRolling autocorrelation (window={window}):")
print(tom["rolling_autocorr"].describe())

# Does the reversion strength predict future volatility?
tom["abs_mid_change"] = tom["mid_change"].abs()
tom["rolling_vol"] = tom["abs_mid_change"].rolling(20).mean()

print(f"\n--- Volatility regimes ---")
vol_med = tom["rolling_vol"].median()
high_vol = tom[tom["rolling_vol"] > vol_med]
low_vol = tom[tom["rolling_vol"] <= vol_med]
print(f"  High vol ticks: {len(high_vol)}, mean abs change: {high_vol['abs_mid_change'].mean():.4f}")
print(f"  Low vol ticks: {len(low_vol)}, mean abs change: {low_vol['abs_mid_change'].mean():.4f}")

# Does autocorrelation differ in high vs low vol?
print(f"\n  High vol autocorr lag1: {high_vol['mid_change'].autocorr(1):.4f}")
print(f"  Low vol autocorr lag1: {low_vol['mid_change'].autocorr(1):.4f}")

# Microprice as signal
tom["microprice"] = (tom["bid_price_1"] * tom["ask_volume_1"] + tom["ask_price_1"] * tom["bid_volume_1"]) / (tom["bid_volume_1"] + tom["ask_volume_1"])
tom["micro_vs_mid"] = tom["microprice"] - tom["mid"]

print(f"\n--- Microprice signal ---")
print(f"Microprice - mid stats:")
print(tom["micro_vs_mid"].describe())
for h in [1, 2, 3, 5, 10]:
    corr = tom["micro_vs_mid"].corr(tom[f"mid_fwd_{h}"])
    print(f"  micro_vs_mid vs mid_fwd_{h}: r={corr:.4f}")

# Time-of-day effects
print(f"\n--- Time-of-day analysis ---")
tom["time_bucket"] = (tom["timestamp"] // 100000) * 100000
time_stats = tom.groupby("time_bucket").agg(
    mean_spread=("spread", "mean"),
    mean_abs_change=("abs_mid_change", "mean"),
    count=("mid", "count")
)
print(time_stats)

# Bid/ask volume ratio as a more sensitive signal
print(f"\n--- L1+L2 combined volume imbalance ---")
tom["total_bid_vol"] = tom["bid_volume_1"] + tom["bid_volume_2"]
tom["total_ask_vol"] = tom["ask_volume_1"] + tom["ask_volume_2"]
tom["total_vol_imb"] = tom["total_bid_vol"] - tom["total_ask_vol"]
for h in [1, 2, 3, 5, 10]:
    corr = tom["total_vol_imb"].corr(tom[f"mid_fwd_{h}"])
    print(f"  total_vol_imb vs mid_fwd_{h}: r={corr:.4f}")

# Does the relationship between L1 and L2 volume carry info?
tom["l1_l2_vol_ratio_bid"] = tom["bid_volume_1"] / tom["bid_volume_2"]
tom["l1_l2_vol_ratio_ask"] = tom["ask_volume_1"] / tom["ask_volume_2"]
tom["l1l2_ratio_diff"] = tom["l1_l2_vol_ratio_bid"] - tom["l1_l2_vol_ratio_ask"]

print(f"\n--- L1/L2 volume ratio differential ---")
for h in [1, 2, 3, 5, 10]:
    corr = tom["l1l2_ratio_diff"].corr(tom[f"mid_fwd_{h}"])
    print(f"  l1l2_ratio_diff vs mid_fwd_{h}: r={corr:.4f}")

# Tick rule momentum
print(f"\n--- Tick-rule momentum (sum of last N signed changes) ---")
for lookback in [3, 5, 10]:
    tom[f"momentum_{lookback}"] = tom["mid_dir"].rolling(lookback).sum()
    for h in [1, 3, 5]:
        corr = tom[f"momentum_{lookback}"].corr(tom[f"mid_fwd_{h}"])
        if h == 1:
            print(f"  momentum_{lookback}: ", end="")
        print(f"fwd{h}_r={corr:.4f}  ", end="")
    print()

print("\n\nDONE.")
