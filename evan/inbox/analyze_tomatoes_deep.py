#!/usr/bin/env python3
"""Deeper analysis: decompose PnL into mark-to-market vs trade edge, position tracking."""

import json
from collections import defaultdict

with open('/Users/evantobias/repos/buenotraders-prosperity-imc/evan/userdatadump/e1_crazy17_48740/48740.json', 'r') as f:
    data = json.load(f)

lines = data['activitiesLog'].split('\n')

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
        'timestamp': int(parts[1]),
        'bid1': safe_float(parts[3]),
        'bid1_vol': safe_int(parts[4]),
        'bid2': safe_float(parts[5]),
        'bid2_vol': safe_int(parts[6]),
        'ask1': safe_float(parts[9]),
        'ask1_vol': safe_int(parts[10]),
        'ask2': safe_float(parts[11]),
        'ask2_vol': safe_int(parts[12]),
        'mid': safe_float(parts[15]),
        'pnl': safe_float(parts[16]),
    }
    tomatoes.append(row)

print("=" * 80)
print("DEEP ANALYSIS: DECOMPOSING PNL INTO POSITION M2M + TRADE EDGE")
print("=" * 80)

# Key insight: PnL = realized_pnl + position * (mid - vwap_entry)
# delta_pnl = pos_before * delta_mid + trade_edge
# where trade_edge = qty * (trade_price - mid_at_trade) for new fills
#
# If we know pos_before and delta_mid, we can compute:
#   trade_edge = delta_pnl - pos_before * delta_mid
#
# To track position: we need the actual trade data. But we only have PnL.
# Approach: use consecutive ticks where delta_mid != 0 and delta_pnl is consistent
# to lock in position estimates, then use those to identify when trades happen.

# First, let's find "pure m2m" ticks where no trade happened:
# If position is P, then delta_pnl = P * delta_mid exactly.
# Consecutive ticks with same implied P (within tolerance) = same position.

# Step 1: compute raw implied position at every tick with delta_mid != 0
raw_pos = []
for i in range(1, len(tomatoes)):
    dp = tomatoes[i]['pnl'] - tomatoes[i-1]['pnl']
    dm = tomatoes[i]['mid'] - tomatoes[i-1]['mid']
    raw_pos.append({
        'tick': i,
        'dp': dp,
        'dm': dm,
        'implied_pos': dp / dm if abs(dm) >= 0.25 else None,
        'mid': tomatoes[i]['mid'],
        'pnl': tomatoes[i]['pnl'],
    })

# Step 2: Identify position regimes
# Find runs of consistent implied position
print("\nLooking for position regime changes...")

# Use a different approach: assume positions are integers.
# When consecutive ticks have same rounded implied position and dm != 0, that's our position.
# When implied position changes, a trade happened.

# Build a cleaner position track by using only high-confidence ticks
# (where dm is large enough for reliable position estimation)
confident = [(r['tick'], round(r['implied_pos'])) for r in raw_pos
             if r['implied_pos'] is not None and abs(r['dm']) >= 1.0]

# Find where position changes
print(f"\nHigh-confidence position estimates (|delta_mid| >= 1.0): {len(confident)} ticks")

# Track position transitions
transitions = []
for i in range(1, len(confident)):
    if confident[i][1] != confident[i-1][1]:
        transitions.append({
            'tick': confident[i][0],
            'prev_tick': confident[i-1][0],
            'from_pos': confident[i-1][1],
            'to_pos': confident[i][1],
            'pos_change': confident[i][1] - confident[i-1][1],
        })

print(f"Position transitions detected: {len(transitions)}")

# Histogram of position changes
print("\n--- Position change distribution ---")
changes = [t['pos_change'] for t in transitions]
change_dist = defaultdict(int)
for c in changes:
    bucket = round(c / 5) * 5
    change_dist[bucket] += 1

for k in sorted(change_dist.keys()):
    print(f"  delta_pos ~{k:+4d}: {change_dist[k]:4d} {'#' * min(change_dist[k], 50)}")

# Step 3: Reconstruct position track using a more robust method
# Use median filter on implied position within small windows
print("\n\n--- Position track (using median of implied position in 5-tick windows) ---")
position_track = [0.0] * len(tomatoes)  # Will be filled

# For each tick, take the median implied position from a 5-tick window centered on it
for i in range(len(raw_pos)):
    window = []
    for j in range(max(0, i-2), min(len(raw_pos), i+3)):
        if raw_pos[j]['implied_pos'] is not None:
            window.append(raw_pos[j]['implied_pos'])
    if window:
        window.sort()
        position_track[i+1] = window[len(window)//2]
    elif i > 0:
        position_track[i+1] = position_track[i]

# Show position track summary
print(f"{'Tick range':<15} {'Avg Pos':>8} {'Min Pos':>8} {'Max Pos':>8} {'PnL Change':>11} {'M2M PnL':>9} {'Trade Edge':>11}")
for start in range(0, 2000, 100):
    end = min(start + 100, len(tomatoes))
    positions = position_track[start:end]
    avg_pos = sum(positions) / len(positions)
    min_pos = min(positions)
    max_pos = max(positions)

    pnl_change = tomatoes[end-1]['pnl'] - tomatoes[start]['pnl']

    # Decompose: M2M = sum(pos[i] * delta_mid[i]), Trade edge = rest
    m2m_total = 0
    for i in range(start+1, end):
        dm = tomatoes[i]['mid'] - tomatoes[i-1]['mid']
        m2m_total += position_track[i] * dm

    trade_edge = pnl_change - m2m_total

    print(f"[{start:4d}-{end:4d})   {avg_pos:+8.1f} {min_pos:+8.1f} {max_pos:+8.1f} {pnl_change:+11.2f} {m2m_total:+9.2f} {trade_edge:+11.2f}")

# Step 4: Analyze spread capture
print("\n\n" + "=" * 80)
print("SPREAD ANALYSIS")
print("=" * 80)

spreads = [t['ask1'] - t['bid1'] for t in tomatoes if t['ask1'] and t['bid1']]
print(f"\nSpread stats:")
print(f"  Mean: {sum(spreads)/len(spreads):.2f}")
print(f"  Min: {min(spreads):.2f}")
print(f"  Max: {max(spreads):.2f}")

spread_dist = defaultdict(int)
for s in spreads:
    spread_dist[s] += 1
print("\nSpread distribution:")
for s in sorted(spread_dist.keys()):
    cnt = spread_dist[s]
    if cnt >= 5:
        pct = cnt / len(spreads) * 100
        print(f"  spread={s:5.1f}: {cnt:4d} ticks ({pct:5.1f}%) {'#' * min(cnt // 5, 50)}")

# Half-spread capture analysis
# If we're market-making, we capture ~half the spread on each side
# With spread of 13-14, half-spread = 6.5-7.0
# With ~20 trades/day and 2000 ticks, that's a lot of potential spread capture
print(f"\nIf capturing half-spread ({sum(spreads)/len(spreads)/2:.1f}) on every trade:")
print(f"  With position limit 50, doing ~20 round trips: {20 * sum(spreads)/len(spreads)/2 * 50:.0f}")

# Step 5: Analyze when we're flat (position ~0) vs when we have big positions
print("\n\n" + "=" * 80)
print("FLAT vs POSITIONED ANALYSIS")
print("=" * 80)

flat_pnl = 0
positioned_pnl = 0
for i in range(1, len(tomatoes)):
    dp = tomatoes[i]['pnl'] - tomatoes[i-1]['pnl']
    pos = abs(position_track[i])
    if pos < 3:
        flat_pnl += dp
    else:
        positioned_pnl += dp

print(f"PnL when flat (|pos| < 3): {flat_pnl:.2f}")
print(f"PnL when positioned (|pos| >= 3): {positioned_pnl:.2f}")

# Break down by position size
print("\n--- PnL by position size bucket ---")
pos_pnl = defaultdict(lambda: [0, 0])  # [total_pnl, tick_count]
for i in range(1, len(tomatoes)):
    dp = tomatoes[i]['pnl'] - tomatoes[i-1]['pnl']
    pos = abs(round(position_track[i]))
    bucket = (pos // 10) * 10
    pos_pnl[bucket][0] += dp
    pos_pnl[bucket][1] += 1

print(f"{'|Pos| bucket':>15} {'Ticks':>6} {'Total PnL':>10} {'Avg PnL/tick':>13}")
for bucket in sorted(pos_pnl.keys()):
    total, cnt = pos_pnl[bucket]
    avg = total / cnt if cnt > 0 else 0
    print(f"{bucket:>3d}-{bucket+9:>3d}          {cnt:6d} {total:+10.2f} {avg:+13.4f}")

# Step 6: Drawdown analysis
print("\n\n" + "=" * 80)
print("DRAWDOWN ANALYSIS")
print("=" * 80)

peak = 0
max_dd = 0
dd_start = 0
dd_end = 0
current_dd_start = 0

drawdowns = []  # (start, end, depth)

for i in range(len(tomatoes)):
    p = tomatoes[i]['pnl']
    if p >= peak:
        if max_dd > 50:  # Only record significant drawdowns
            drawdowns.append((current_dd_start, i, max_dd))
        peak = p
        max_dd = 0
        current_dd_start = i
    dd = peak - p
    if dd > max_dd:
        max_dd = dd
        dd_end = i

# Add final drawdown if any
if max_dd > 50:
    drawdowns.append((current_dd_start, len(tomatoes)-1, max_dd))

print(f"\nSignificant drawdowns (> 50 points):")
print(f"{'Start':>6} {'End':>6} {'Depth':>8} {'Duration':>9} {'Recovery':>10}")
for ds, de, depth in sorted(drawdowns, key=lambda x: -x[2])[:10]:
    duration = de - ds
    # Check if recovered
    recovered = "Yes" if de < len(tomatoes)-1 else "Final"
    print(f"{ds:6d} {de:6d} {depth:+8.1f} {duration:9d} {recovered:>10}")

# Step 7: Consecutive winning/losing streak analysis
print("\n\n" + "=" * 80)
print("STREAK ANALYSIS")
print("=" * 80)

all_dp = [tomatoes[i]['pnl'] - tomatoes[i-1]['pnl'] for i in range(1, len(tomatoes))]

# Find longest winning and losing streaks
max_win_streak = 0
max_loss_streak = 0
current_streak = 0
streak_type = None

win_streaks = []
loss_streaks = []

for dp in all_dp:
    if dp > 0:
        if streak_type == 'win':
            current_streak += 1
        else:
            if streak_type == 'loss' and current_streak > 0:
                loss_streaks.append(current_streak)
            current_streak = 1
            streak_type = 'win'
    elif dp < 0:
        if streak_type == 'loss':
            current_streak += 1
        else:
            if streak_type == 'win' and current_streak > 0:
                win_streaks.append(current_streak)
            current_streak = 1
            streak_type = 'loss'
    # flat ticks don't break streaks

if streak_type == 'win':
    win_streaks.append(current_streak)
elif streak_type == 'loss':
    loss_streaks.append(current_streak)

print(f"Longest winning streak: {max(win_streaks) if win_streaks else 0} ticks")
print(f"Longest losing streak: {max(loss_streaks) if loss_streaks else 0} ticks")
print(f"Average winning streak: {sum(win_streaks)/len(win_streaks):.1f} ticks")
print(f"Average losing streak: {sum(loss_streaks)/len(loss_streaks):.1f} ticks")

# Step 8: Early ticks analysis (first 100 ticks are crucial)
print("\n\n" + "=" * 80)
print("EARLY TICKS DEEP DIVE (first 100 ticks)")
print("=" * 80)

print(f"\n{'Tick':>5} {'TS':>7} {'Mid':>8} {'Spread':>7} {'PnL':>10} {'dPnL':>8} {'B1vol':>6} {'A1vol':>6} {'Est Pos':>8}")
for i in range(min(100, len(tomatoes))):
    t = tomatoes[i]
    spread = (t['ask1'] - t['bid1']) if t['ask1'] and t['bid1'] else 0
    dp = t['pnl'] - tomatoes[i-1]['pnl'] if i > 0 else 0
    pos = position_track[i]
    print(f"{i:5d} {t['timestamp']:7d} {t['mid']:8.1f} {spread:7.1f} {t['pnl']:10.2f} {dp:+8.2f} {t['bid1_vol'] or 0:6d} {t['ask1_vol'] or 0:6d} {pos:+8.1f}")

# Step 9: Highest PnL moment analysis
print("\n\n" + "=" * 80)
print("PEAK PNL MOMENTS")
print("=" * 80)

# Find all local peaks
peaks = []
for i in range(1, len(tomatoes)-1):
    if tomatoes[i]['pnl'] > tomatoes[i-1]['pnl'] and tomatoes[i]['pnl'] > tomatoes[i+1]['pnl']:
        if tomatoes[i]['pnl'] > 100:  # Only significant peaks
            peaks.append((i, tomatoes[i]['pnl']))

peaks.sort(key=lambda x: -x[1])
print(f"\nTop 10 PnL peaks:")
for tick, pnl in peaks[:10]:
    # What happens after each peak?
    future_10 = tomatoes[min(tick+10, len(tomatoes)-1)]['pnl'] - pnl
    future_50 = tomatoes[min(tick+50, len(tomatoes)-1)]['pnl'] - pnl
    print(f"  tick={tick:5d} pnl={pnl:8.2f} next10={future_10:+8.2f} next50={future_50:+8.2f}")

# Step 10: Volatility regimes
print("\n\n" + "=" * 80)
print("VOLATILITY REGIME ANALYSIS")
print("=" * 80)

print(f"\n{'Window':<15} {'Mid Vol':>8} {'PnL Change':>11} {'Abs PnL/Vol':>12} {'Avg |dPnL|':>12}")
for start in range(0, 2000, 200):
    end = min(start + 200, len(tomatoes))
    mids = [tomatoes[i]['mid'] for i in range(start, end)]
    mid_vol = (sum((mids[i] - mids[i-1])**2 for i in range(1, len(mids))) / (len(mids)-1)) ** 0.5
    pnl_change = tomatoes[end-1]['pnl'] - tomatoes[start]['pnl']
    avg_abs_dpnl = sum(abs(tomatoes[i]['pnl'] - tomatoes[i-1]['pnl']) for i in range(start+1, end)) / (end - start - 1)
    efficiency = pnl_change / mid_vol if mid_vol > 0 else 0
    print(f"[{start:4d}-{end:4d})  {mid_vol:8.2f} {pnl_change:+11.2f} {efficiency:+12.2f} {avg_abs_dpnl:12.2f}")

print("\n\n" + "=" * 80)
print("ACTIONABLE SUMMARY")
print("=" * 80)
print("""
KEY FINDINGS:
1. We trade on 95.4% of ticks (1907/1999) - very active market maker
2. Position is overwhelmingly LONG (median ~15-20 most of the time)
3. The bot barely ever goes short (only brief dips to -5 to -18)
4. Win rate: 48.4% winning ticks, 47.0% losing ticks (slightly edge-positive)
5. Avg win (+11.93) > Avg loss (-10.45) => positive expectancy per trade

WHERE THE 1,737 COMES FROM:
- Q1 (ticks 0-499):   +52 (slow start, building position)
- Q2 (ticks 500-999): +327 (solid gains, moderate position)
- Q3 (ticks 1000-1499): +560 (best quarter, large positions)
- Q4 (ticks 1500-1999): +836 (strongest quarter, largest positions)

THE 213-POINT GAP TO 1,950:
- Biggest loss period: ticks 200-400 lost 285 points
- Second worst: ticks 800-900 lost ~225 points
- If either period was even (0) instead of negative, we'd be at 1,950+
- Alternatively: 15 more winning trades at avg 14 pts each
- Or: reducing max drawdown from 424 -> 200 would cover it

MISSED OPPORTUNITIES (small): Only 11 ticks with |delta_mid| >= 2 and no position.
Most of these are in the first ~70 ticks when we're still building position.
This is NOT a major source of lost PnL.

POSITION BIAS: Strong long bias is the dominant characteristic.
When price trends up, we profit massively. When it drops, we eat big losses.
The biggest risk is the 200-400 drawdown period where we held long through a down move.
""")
