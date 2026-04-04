#!/usr/bin/env python3
"""Deep analysis of TOMATOES PnL from best bot submission (48740)."""

import json
import math
from collections import defaultdict

# Load data
with open('/Users/evantobias/repos/buenotraders-prosperity-imc/evan/userdatadump/e1_crazy17_48740/48740.json', 'r') as f:
    data = json.load(f)

lines = data['activitiesLog'].split('\n')
header = lines[0]

# Parse TOMATOES lines
tomatoes = []
for line in lines[1:]:
    if not line.strip():
        continue
    parts = line.split(';')
    if parts[2] != 'TOMATOES':
        continue

    def safe_float(x):
        return float(x) if x != '' else None
    def safe_int(x):
        return int(x) if x != '' else None

    row = {
        'day': int(parts[0]),
        'timestamp': int(parts[1]),
        'bid1_price': safe_float(parts[3]),
        'bid1_vol': safe_int(parts[4]),
        'bid2_price': safe_float(parts[5]),
        'bid2_vol': safe_int(parts[6]),
        'bid3_price': safe_float(parts[7]),
        'bid3_vol': safe_int(parts[8]),
        'ask1_price': safe_float(parts[9]),
        'ask1_vol': safe_int(parts[10]),
        'ask2_price': safe_float(parts[11]),
        'ask2_vol': safe_int(parts[12]),
        'ask3_price': safe_float(parts[13]),
        'ask3_vol': safe_int(parts[14]),
        'mid_price': safe_float(parts[15]),
        'pnl': safe_float(parts[16]),
    }
    tomatoes.append(row)

print(f"Total TOMATOES ticks: {len(tomatoes)}")
print(f"Final PnL: {tomatoes[-1]['pnl']:.2f}")
print(f"Timestamp range: {tomatoes[0]['timestamp']} to {tomatoes[-1]['timestamp']}")
print()

# ============================================================
# 1. PnL TRAJECTORY
# ============================================================
print("=" * 80)
print("1. PnL TRAJECTORY (text plot)")
print("=" * 80)

pnls = [t['pnl'] for t in tomatoes]
min_pnl = min(pnls)
max_pnl = max(pnls)

# Text-based sparkline plot: show every 20th tick
WIDTH = 70
print(f"\nMin PnL: {min_pnl:.2f}, Max PnL: {max_pnl:.2f}")
print(f"Ticks shown: every 20th tick (0 to {len(tomatoes)-1})\n")

# Sample every 20 ticks
sample_indices = list(range(0, len(tomatoes), 20))
sample_pnls = [pnls[i] for i in sample_indices]

for i, idx in enumerate(sample_indices):
    p = pnls[idx]
    if max_pnl == min_pnl:
        bar_len = WIDTH // 2
    else:
        bar_len = int((p - min_pnl) / (max_pnl - min_pnl) * WIDTH)
    bar = '#' * max(bar_len, 0)
    print(f"t={idx:4d} | {bar:<{WIDTH}} | {p:8.1f}")

# Find big PnL changes
print("\n--- Ticks with PnL change >= 20 (absolute) ---")
big_changes = []
for i in range(1, len(tomatoes)):
    delta = tomatoes[i]['pnl'] - tomatoes[i-1]['pnl']
    if abs(delta) >= 20:
        big_changes.append((i, delta, tomatoes[i]))

print(f"Count: {len(big_changes)}")
for idx, delta, t in sorted(big_changes, key=lambda x: -abs(x[1]))[:30]:
    spread = t['ask1_price'] - t['bid1_price'] if t['ask1_price'] and t['bid1_price'] else None
    print(f"  tick={idx:4d} ts={t['timestamp']:6d} delta={delta:+8.2f} mid={t['mid_price']:.1f} spread={spread}")

# ============================================================
# 2. TRADE DETECTION
# ============================================================
print("\n" + "=" * 80)
print("2. TRADE DETECTION")
print("=" * 80)

trades = []
for i in range(1, len(tomatoes)):
    delta = tomatoes[i]['pnl'] - tomatoes[i-1]['pnl']
    mid_change = tomatoes[i]['mid_price'] - tomatoes[i-1]['mid_price']
    if abs(delta) > 0.001:  # PnL changed = trade happened
        trades.append({
            'tick': i,
            'timestamp': tomatoes[i]['timestamp'],
            'delta_pnl': delta,
            'mid_price': tomatoes[i]['mid_price'],
            'mid_change': mid_change,
            'prev_mid': tomatoes[i-1]['mid_price'],
            'bid1': tomatoes[i]['bid1_price'],
            'ask1': tomatoes[i]['ask1_price'],
            'bid1_vol': tomatoes[i]['bid1_vol'],
            'ask1_vol': tomatoes[i]['ask1_vol'],
            'spread': (tomatoes[i]['ask1_price'] - tomatoes[i]['bid1_price']) if tomatoes[i]['ask1_price'] and tomatoes[i]['bid1_price'] else None,
            'prev_spread': (tomatoes[i-1]['ask1_price'] - tomatoes[i-1]['bid1_price']) if tomatoes[i-1]['ask1_price'] and tomatoes[i-1]['bid1_price'] else None,
        })

print(f"Total ticks with PnL change (trades): {len(trades)}")
print(f"Ticks without PnL change (no trade): {len(tomatoes) - 1 - len(trades)}")

# Also count ticks where PnL changed but might be mark-to-market vs actual trade
# PnL = realized + unrealized. If we have a position and mid moves, PnL changes too.
# So not every PnL change is a new trade.

# Distribution of trade PnL
deltas = [t['delta_pnl'] for t in trades]
positive = [d for d in deltas if d > 0]
negative = [d for d in deltas if d < 0]
zero_ish = [d for d in deltas if abs(d) < 0.01]

print(f"\nPositive PnL changes: {len(positive)}, total: {sum(positive):.2f}")
print(f"Negative PnL changes: {len(negative)}, total: {sum(negative):.2f}")
print(f"Net from all changes: {sum(deltas):.2f}")

# Histogram of PnL changes
print("\n--- Histogram of PnL changes ---")
buckets = [(-1000, -50), (-50, -20), (-20, -10), (-10, -5), (-5, -2), (-2, -0.5),
           (-0.5, 0.5), (0.5, 2), (2, 5), (5, 10), (10, 20), (20, 50), (50, 1000)]
for lo, hi in buckets:
    count = len([d for d in deltas if lo <= d < hi])
    total = sum(d for d in deltas if lo <= d < hi)
    if count > 0:
        bar = '#' * min(count, 60)
        print(f"  [{lo:7.1f}, {hi:7.1f}): n={count:4d} sum={total:8.2f} {bar}")

# ============================================================
# 3. WINNING vs LOSING TRADES
# ============================================================
print("\n" + "=" * 80)
print("3. WINNING vs LOSING TRADES (top/bottom 20)")
print("=" * 80)

sorted_by_pnl = sorted(trades, key=lambda t: t['delta_pnl'])

print("\n--- TOP 20 MOST PROFITABLE ticks ---")
print(f"{'tick':>5} {'ts':>7} {'delta_pnl':>10} {'mid':>8} {'bid1':>7} {'ask1':>7} {'spread':>7} {'b1vol':>6} {'a1vol':>6}")
for t in sorted_by_pnl[-20:][::-1]:
    print(f"{t['tick']:5d} {t['timestamp']:7d} {t['delta_pnl']:+10.2f} {t['mid_price']:8.1f} {t['bid1']:7.1f} {t['ask1']:7.1f} {t['spread']:7.1f} {t['bid1_vol']:6d} {t['ask1_vol']:6d}")

print("\n--- TOP 20 MOST UNPROFITABLE ticks ---")
print(f"{'tick':>5} {'ts':>7} {'delta_pnl':>10} {'mid':>8} {'bid1':>7} {'ask1':>7} {'spread':>7} {'b1vol':>6} {'a1vol':>6}")
for t in sorted_by_pnl[:20]:
    print(f"{t['tick']:5d} {t['timestamp']:7d} {t['delta_pnl']:+10.2f} {t['mid_price']:8.1f} {t['bid1']:7.1f} {t['ask1']:7.1f} {t['spread']:7.1f} {t['bid1_vol']:6d} {t['ask1_vol']:6d}")

# Pattern analysis
print("\n--- Pattern analysis: Winning vs Losing ---")
top20 = sorted_by_pnl[-20:]
bot20 = sorted_by_pnl[:20]

top_spreads = [t['spread'] for t in top20 if t['spread'] is not None]
bot_spreads = [t['spread'] for t in bot20 if t['spread'] is not None]
top_b1vols = [t['bid1_vol'] for t in top20 if t['bid1_vol'] is not None]
bot_b1vols = [t['bid1_vol'] for t in bot20 if t['bid1_vol'] is not None]
top_a1vols = [t['ask1_vol'] for t in top20 if t['ask1_vol'] is not None]
bot_a1vols = [t['ask1_vol'] for t in bot20 if t['ask1_vol'] is not None]

print(f"  Winning: avg spread={sum(top_spreads)/len(top_spreads):.2f}, avg bid1_vol={sum(top_b1vols)/len(top_b1vols):.1f}, avg ask1_vol={sum(top_a1vols)/len(top_a1vols):.1f}")
print(f"  Losing:  avg spread={sum(bot_spreads)/len(bot_spreads):.2f}, avg bid1_vol={sum(bot_b1vols)/len(bot_b1vols):.1f}, avg ask1_vol={sum(bot_a1vols)/len(bot_a1vols):.1f}")

# ============================================================
# 4. POSITION ANALYSIS
# ============================================================
print("\n" + "=" * 80)
print("4. POSITION ANALYSIS")
print("=" * 80)

# PnL = sum(trade_pnl) + position * (current_mid - avg_entry)
# When PnL changes: delta_pnl = position_before * (mid_now - mid_prev) + trade_profit
# trade_profit from new trade = qty * (sell_price - buy_price) for the new fills
#
# But we only see cumulative PnL. Let's try to infer position:
# If no trade happened: delta_pnl = position * delta_mid
# So position = delta_pnl / delta_mid (when delta_mid != 0 and we think no trade)
#
# Strategy: look at ticks where PnL changes but we suspect it's mark-to-market only
# Also, between known trade ticks, the position should be constant.

# Let's compute delta_pnl and delta_mid for every tick
all_deltas = []
for i in range(1, len(tomatoes)):
    dp = tomatoes[i]['pnl'] - tomatoes[i-1]['pnl']
    dm = tomatoes[i]['mid_price'] - tomatoes[i-1]['mid_price']
    all_deltas.append({
        'tick': i,
        'delta_pnl': dp,
        'delta_mid': dm,
        'mid': tomatoes[i]['mid_price'],
        'timestamp': tomatoes[i]['timestamp'],
    })

# Try to infer position from mark-to-market ticks
# When delta_mid != 0, position_est = delta_pnl / delta_mid
# But this only works if the ONLY source of PnL change is m2m (no new trade)
# We can look for ticks where delta_pnl is very close to position * delta_mid

# Alternative approach: use sequences of consecutive "no trade" ticks
# Actually, since the PnL here includes m2m, let's just estimate:
# At each tick, if we can isolate ticks where ONLY m2m happened (no new trade),
# we can compute position = delta_pnl / delta_mid

# Let's look at all deltas and identify position regimes
print("\nAttempting position inference from mark-to-market...")
print("(Using ticks where delta_mid != 0 to estimate position)\n")

# For each tick, compute implied position
implied_positions = []
for d in all_deltas:
    if abs(d['delta_mid']) >= 0.5:  # mid moved enough to estimate
        pos = d['delta_pnl'] / d['delta_mid']
        implied_positions.append((d['tick'], pos, d['delta_pnl'], d['delta_mid']))

# Look for stable position regimes
# Round to nearest integer (positions must be integers in IMC)
print(f"Ticks with delta_mid >= 0.5: {len(implied_positions)}")

# Group by approximate position
pos_values = [round(p[1]) for p in implied_positions]
pos_counts = defaultdict(int)
for p in pos_values:
    pos_counts[p] += 1

print("\nImplied position distribution (rounded to int):")
for pos in sorted(pos_counts.keys()):
    cnt = pos_counts[pos]
    if cnt >= 3:
        print(f"  position={pos:4d}: {cnt:4d} ticks {'#' * min(cnt, 50)}")

# Now let's track position over time using a smoothed approach
# Group implied positions by time windows
print("\nPosition over time (every 200 ticks, median implied position):")
for start in range(0, 2000, 100):
    end = start + 100
    window_pos = [p[1] for p in implied_positions if start <= p[0] < end]
    if window_pos:
        window_pos.sort()
        median = window_pos[len(window_pos)//2]
        avg = sum(window_pos) / len(window_pos)
        pnl_at_start = tomatoes[min(start, len(tomatoes)-1)]['pnl']
        pnl_at_end = tomatoes[min(end, len(tomatoes)-1)]['pnl']
        pnl_change = pnl_at_end - pnl_at_start
        print(f"  ticks [{start:4d}-{end:4d}): median_pos={median:6.1f} avg_pos={avg:6.1f} n={len(window_pos):3d} pnl_change={pnl_change:+8.2f}")

# Track max long and max short
print(f"\nMax implied long position: {max(p[1] for p in implied_positions):.1f}")
print(f"Max implied short position: {min(p[1] for p in implied_positions):.1f}")

# Correlate position with subsequent PnL
print("\n--- Position vs subsequent PnL (next 10 ticks) ---")
# Bucket positions and look at average subsequent PnL change
pos_pnl_buckets = defaultdict(list)
for tick, pos, dp, dm in implied_positions:
    rounded_pos = round(pos / 5) * 5  # round to nearest 5
    if tick + 10 < len(tomatoes):
        future_pnl = tomatoes[tick + 10]['pnl'] - tomatoes[tick]['pnl']
        pos_pnl_buckets[rounded_pos].append(future_pnl)

print(f"{'position':>10} {'n':>5} {'avg_future_pnl_10':>18} {'std':>10}")
for pos in sorted(pos_pnl_buckets.keys()):
    vals = pos_pnl_buckets[pos]
    if len(vals) >= 5:
        avg = sum(vals) / len(vals)
        std = (sum((v - avg)**2 for v in vals) / len(vals)) ** 0.5
        print(f"{pos:10d} {len(vals):5d} {avg:+18.2f} {std:10.2f}")

# ============================================================
# 5. MISSED OPPORTUNITIES
# ============================================================
print("\n" + "=" * 80)
print("5. MISSED OPPORTUNITIES")
print("=" * 80)

missed = []
for i in range(1, len(tomatoes)):
    dm = abs(tomatoes[i]['mid_price'] - tomatoes[i-1]['mid_price'])
    dp = abs(tomatoes[i]['pnl'] - tomatoes[i-1]['pnl'])
    if dm >= 2.0 and dp < 0.01:
        missed.append({
            'tick': i,
            'timestamp': tomatoes[i]['timestamp'],
            'delta_mid': tomatoes[i]['mid_price'] - tomatoes[i-1]['mid_price'],
            'mid': tomatoes[i]['mid_price'],
            'spread': (tomatoes[i]['ask1_price'] - tomatoes[i]['bid1_price']) if tomatoes[i]['ask1_price'] and tomatoes[i]['bid1_price'] else None,
            'bid1_vol': tomatoes[i]['bid1_vol'],
            'ask1_vol': tomatoes[i]['ask1_vol'],
        })

print(f"Ticks with |delta_mid| >= 2 and NO trade: {len(missed)}")
print(f"Ticks with |delta_mid| >= 2 total: {sum(1 for i in range(1, len(tomatoes)) if abs(tomatoes[i]['mid_price'] - tomatoes[i-1]['mid_price']) >= 2.0)}")

# Theoretical PnL if we had captured all big moves
total_missed_movement = sum(abs(m['delta_mid']) for m in missed)
print(f"Total absolute mid movement missed: {total_missed_movement:.1f}")

# But this is misleading - we can only capture moves we're positioned for
# More useful: when mid moved UP by 2+ and we didn't trade, that's a missed buy opportunity
# When mid moved DOWN by 2+ and we didn't trade, missed sell opportunity
missed_up = [m for m in missed if m['delta_mid'] >= 2.0]
missed_down = [m for m in missed if m['delta_mid'] <= -2.0]
print(f"  Missed upward moves (>= +2): {len(missed_up)}, total move: {sum(m['delta_mid'] for m in missed_up):.1f}")
print(f"  Missed downward moves (<= -2): {len(missed_down)}, total move: {sum(m['delta_mid'] for m in missed_down):.1f}")

# Check: are these ticks where we had zero position?
# If we had position, PnL would have changed with mid. So zero PnL change = zero position at those ticks.
print(f"\n  (Zero PnL change + big mid move => we had NO position at these ticks)")
print(f"  If we had been long 1 unit for each missed up move: +{sum(m['delta_mid'] for m in missed_up):.1f}")
print(f"  If we had been short 1 unit for each missed down move: +{-sum(m['delta_mid'] for m in missed_down):.1f}")

# Also check lower threshold
missed_1 = sum(1 for i in range(1, len(tomatoes))
               if abs(tomatoes[i]['mid_price'] - tomatoes[i-1]['mid_price']) >= 1.0
               and abs(tomatoes[i]['pnl'] - tomatoes[i-1]['pnl']) < 0.01)
print(f"\nTicks with |delta_mid| >= 1 and NO trade: {missed_1}")

# Show worst missed opportunities
print("\n--- Top 20 biggest missed moves ---")
missed_sorted = sorted(missed, key=lambda m: -abs(m['delta_mid']))
print(f"{'tick':>5} {'ts':>7} {'delta_mid':>10} {'mid':>8} {'spread':>7} {'b1vol':>6} {'a1vol':>6}")
for m in missed_sorted[:20]:
    sp = f"{m['spread']:.1f}" if m['spread'] else "N/A"
    bv = f"{m['bid1_vol']}" if m['bid1_vol'] else "N/A"
    av = f"{m['ask1_vol']}" if m['ask1_vol'] else "N/A"
    print(f"{m['tick']:5d} {m['timestamp']:7d} {m['delta_mid']:+10.1f} {m['mid']:8.1f} {sp:>7} {bv:>6} {av:>6}")

# ============================================================
# 6. TIME ANALYSIS
# ============================================================
print("\n" + "=" * 80)
print("6. TIME ANALYSIS (by quarter)")
print("=" * 80)

quarters = [
    ("Q1: ticks 0-499", 0, 500),
    ("Q2: ticks 500-999", 500, 1000),
    ("Q3: ticks 1000-1499", 1000, 1500),
    ("Q4: ticks 1500-1999", 1500, 2000),
]

print(f"\n{'Quarter':<25} {'Start PnL':>10} {'End PnL':>10} {'Change':>10} {'Trades':>7} {'Avg Spread':>11} {'Mid Range':>15}")
for name, start, end in quarters:
    start_pnl = tomatoes[start]['pnl']
    end_pnl = tomatoes[min(end-1, len(tomatoes)-1)]['pnl']
    change = end_pnl - start_pnl

    q_trades = [t for t in trades if start <= t['tick'] < end]
    q_spreads = [tomatoes[i]['ask1_price'] - tomatoes[i]['bid1_price']
                 for i in range(start, min(end, len(tomatoes)))
                 if tomatoes[i]['ask1_price'] and tomatoes[i]['bid1_price']]
    avg_spread = sum(q_spreads) / len(q_spreads) if q_spreads else 0

    q_mids = [tomatoes[i]['mid_price'] for i in range(start, min(end, len(tomatoes)))]
    mid_range = f"{min(q_mids):.0f}-{max(q_mids):.0f}"

    print(f"{name:<25} {start_pnl:10.2f} {end_pnl:10.2f} {change:+10.2f} {len(q_trades):7d} {avg_spread:11.2f} {mid_range:>15}")

# More granular: 200-tick windows
print(f"\n--- 200-tick windows ---")
print(f"{'Window':<25} {'PnL Change':>10} {'Trades':>7} {'Avg Trade PnL':>14} {'Biggest Win':>12} {'Biggest Loss':>12}")
for start in range(0, 2000, 200):
    end = start + 200
    pnl_change = tomatoes[min(end-1, len(tomatoes)-1)]['pnl'] - tomatoes[start]['pnl']
    w_trades = [t for t in trades if start <= t['tick'] < end]
    avg_trade = sum(t['delta_pnl'] for t in w_trades) / len(w_trades) if w_trades else 0
    biggest_win = max((t['delta_pnl'] for t in w_trades), default=0)
    biggest_loss = min((t['delta_pnl'] for t in w_trades), default=0)
    print(f"  [{start:4d}-{end:4d}) {pnl_change:+10.2f} {len(w_trades):7d} {avg_trade:+14.2f} {biggest_win:+12.2f} {biggest_loss:+12.2f}")

# ============================================================
# SUMMARY
# ============================================================
print("\n" + "=" * 80)
print("SUMMARY: WHERE DOES THE 1,737 COME FROM?")
print("=" * 80)

total_positive = sum(d for d in deltas if d > 0)
total_negative = sum(d for d in deltas if d < 0)
print(f"\nGross positive PnL changes: {total_positive:+.2f}")
print(f"Gross negative PnL changes: {total_negative:+.2f}")
print(f"Net: {total_positive + total_negative:+.2f}")
print(f"Actual final PnL: {tomatoes[-1]['pnl']:.2f}")

# Also compute from all ticks (not just "trade" ticks)
all_delta_pnl = [tomatoes[i]['pnl'] - tomatoes[i-1]['pnl'] for i in range(1, len(tomatoes))]
total_pos_all = sum(d for d in all_delta_pnl if d > 0)
total_neg_all = sum(d for d in all_delta_pnl if d < 0)
print(f"\nAll tick changes (inc. m2m):")
print(f"  Gross gains: {total_pos_all:+.2f}")
print(f"  Gross losses: {total_neg_all:+.2f}")
print(f"  Net: {total_pos_all + total_neg_all:+.2f}")

# Sharpe-like metric
avg_delta = sum(all_delta_pnl) / len(all_delta_pnl)
std_delta = (sum((d - avg_delta)**2 for d in all_delta_pnl) / len(all_delta_pnl)) ** 0.5
print(f"\nPer-tick stats:")
print(f"  Mean PnL change: {avg_delta:.4f}")
print(f"  Std PnL change: {std_delta:.4f}")
print(f"  Sharpe (per-tick): {avg_delta / std_delta:.4f}" if std_delta > 0 else "  Sharpe: N/A")
print(f"  Max drawdown (from peak): ", end="")

# Compute max drawdown
peak = tomatoes[0]['pnl']
max_dd = 0
max_dd_tick = 0
for i, t in enumerate(tomatoes):
    if t['pnl'] > peak:
        peak = t['pnl']
    dd = peak - t['pnl']
    if dd > max_dd:
        max_dd = dd
        max_dd_tick = i
print(f"{max_dd:.2f} at tick {max_dd_tick}")

# Win rate
winning_ticks = sum(1 for d in all_delta_pnl if d > 0)
losing_ticks = sum(1 for d in all_delta_pnl if d < 0)
flat_ticks = sum(1 for d in all_delta_pnl if d == 0)
print(f"\n  Winning ticks: {winning_ticks} ({winning_ticks/(len(all_delta_pnl))*100:.1f}%)")
print(f"  Losing ticks: {losing_ticks} ({losing_ticks/(len(all_delta_pnl))*100:.1f}%)")
print(f"  Flat ticks: {flat_ticks} ({flat_ticks/(len(all_delta_pnl))*100:.1f}%)")
print(f"  Avg win: {total_pos_all/winning_ticks:.2f}" if winning_ticks else "  Avg win: N/A")
print(f"  Avg loss: {total_neg_all/losing_ticks:.2f}" if losing_ticks else "  Avg loss: N/A")

# Gap analysis
print(f"\n--- Gap to 1,950 target ---")
gap = 1950 - tomatoes[-1]['pnl']
print(f"Current: {tomatoes[-1]['pnl']:.2f}")
print(f"Target: 1,950")
print(f"Gap: {gap:.2f}")
print(f"That's {gap / 2000:.2f} more PnL per tick needed")
print(f"Or capturing ~{gap / 14:.0f} more winning trades at avg win of 14 points")
print(f"Or reducing losses by {-gap:.0f} points total")
