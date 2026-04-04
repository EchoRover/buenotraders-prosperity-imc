#!/usr/bin/env python3
"""Final targeted analysis: narrow spread ticks, and the 30-tick dead zone."""

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
    def sf(x): return float(x) if x != '' else None
    def si(x): return int(x) if x != '' else None
    tomatoes.append({
        'ts': int(parts[1]),
        'bid1': sf(parts[3]), 'bid1_vol': si(parts[4]),
        'bid2': sf(parts[5]), 'bid2_vol': si(parts[6]),
        'ask1': sf(parts[9]), 'ask1_vol': si(parts[10]),
        'ask2': sf(parts[11]), 'ask2_vol': si(parts[12]),
        'mid': sf(parts[15]), 'pnl': sf(parts[16]),
    })

# ============================================================
# 1. NARROW SPREAD TICKS - are these special?
# ============================================================
print("=" * 80)
print("NARROW SPREAD ANALYSIS (spread 5-9 vs normal 13-14)")
print("=" * 80)

narrow_ticks = []
normal_ticks = []
for i, t in enumerate(tomatoes):
    spread = t['ask1'] - t['bid1'] if t['ask1'] and t['bid1'] else None
    if spread is None:
        continue
    if spread <= 9:
        narrow_ticks.append(i)
    else:
        normal_ticks.append(i)

print(f"Narrow spread ticks (5-9): {len(narrow_ticks)}")
print(f"Normal spread ticks (13-14): {len(normal_ticks)}")

# PnL contribution from narrow vs normal spread ticks
narrow_pnl = sum(tomatoes[i]['pnl'] - tomatoes[i-1]['pnl'] for i in narrow_ticks if i > 0)
normal_pnl = sum(tomatoes[i]['pnl'] - tomatoes[i-1]['pnl'] for i in normal_ticks if i > 0)
print(f"\nPnL from narrow spread ticks: {narrow_pnl:+.2f}")
print(f"PnL from normal spread ticks: {normal_pnl:+.2f}")
print(f"PnL per narrow tick: {narrow_pnl/len(narrow_ticks):.2f}")
print(f"PnL per normal tick: {normal_pnl/len(normal_ticks):.2f}")

# What happens in the tick AFTER a narrow spread?
print("\n--- What happens the tick AFTER a narrow spread? ---")
after_narrow_pnl = []
for i in narrow_ticks:
    if i + 1 < len(tomatoes):
        dp = tomatoes[i+1]['pnl'] - tomatoes[i]['pnl']
        after_narrow_pnl.append(dp)
print(f"Avg PnL change in tick after narrow spread: {sum(after_narrow_pnl)/len(after_narrow_pnl):+.2f}")
print(f"Positive: {sum(1 for x in after_narrow_pnl if x > 0)}, Negative: {sum(1 for x in after_narrow_pnl if x < 0)}")

# Narrow spread tick details
print("\n--- All narrow spread ticks ---")
print(f"{'Tick':>5} {'TS':>7} {'Mid':>8} {'Spread':>7} {'dPnL':>8} {'B1':>7} {'A1':>7} {'B1vol':>6} {'A1vol':>6}")
for i in narrow_ticks[:50]:
    t = tomatoes[i]
    spread = t['ask1'] - t['bid1']
    dp = tomatoes[i]['pnl'] - tomatoes[i-1]['pnl'] if i > 0 else 0
    print(f"{i:5d} {t['ts']:7d} {t['mid']:8.1f} {spread:7.1f} {dp:+8.2f} {t['bid1']:7.1f} {t['ask1']:7.1f} {t['bid1_vol']:6d} {t['ask1_vol']:6d}")

# ============================================================
# 2. THE DEAD ZONE: ticks 0-29 where we don't trade at all
# ============================================================
print("\n\n" + "=" * 80)
print("THE DEAD ZONE: First 30 ticks (0-29) with ZERO PnL")
print("=" * 80)

# The bot doesn't trade for the first 30 ticks. Why?
# Price drops from 5006 to 5003 during this time.
print("These are 30 ticks where mid drops from 5006 to 5003 and we capture NOTHING.")
print("If we had been long 20 at mid 5006, we'd have lost 20*3 = 60 pts.")
print("If we had been short 20 at mid 5006, we'd have gained 20*3 = 60 pts.")
print("The bot correctly avoids trading when it doesn't know the market yet.")
print(f"Cost of caution: 0 (we miss a 3-point down move, which would hurt a long bot)")

# ============================================================
# 3. THE BAD PERIODS: ticks 200-400 and 800-900
# ============================================================
print("\n\n" + "=" * 80)
print("DEEP DIVE: WORST PERIOD (ticks 200-400, lost 285 points)")
print("=" * 80)

# Track mid-price movement during this period
mids_200_400 = [tomatoes[i]['mid'] for i in range(200, 400)]
print(f"Mid at tick 200: {mids_200_400[0]}")
print(f"Mid at tick 400: {mids_200_400[-1]}")
print(f"Mid range: {min(mids_200_400):.1f} to {max(mids_200_400):.1f}")
print(f"Net mid change: {mids_200_400[-1] - mids_200_400[0]:+.1f}")

# This was a ~16 point drop while holding ~15-25 long
# PnL impact: ~20 pos * ~15 drop = ~300 loss, matches the 285 we see

# What if we had reduced position faster?
print(f"\nHypothetical: if position had been halved (10 instead of 20):")
print(f"  Would have lost ~142 instead of ~285 = saving ~143 points")
print(f"  But would have also halved gains in good periods")

# ============================================================
# 4. BID/ASK VOLUME ASYMMETRY SIGNALS
# ============================================================
print("\n\n" + "=" * 80)
print("BID/ASK VOLUME ASYMMETRY")
print("=" * 80)

# When bid volume >> ask volume, price likely to go up (more demand)
# When ask volume >> bid volume, price likely to go down (more supply)
print("\nDo volume asymmetries predict next-tick price moves?")

correct_vol_signal = 0
wrong_vol_signal = 0
no_signal = 0

for i in range(len(tomatoes) - 1):
    t = tomatoes[i]
    if t['bid1_vol'] and t['ask1_vol']:
        vol_diff = t['bid1_vol'] - t['ask1_vol']
        mid_change = tomatoes[i+1]['mid'] - t['mid']
        if abs(vol_diff) >= 2:  # meaningful asymmetry
            if (vol_diff > 0 and mid_change > 0) or (vol_diff < 0 and mid_change < 0):
                correct_vol_signal += 1
            elif mid_change != 0:
                wrong_vol_signal += 1
            else:
                no_signal += 1

total_signals = correct_vol_signal + wrong_vol_signal
print(f"Volume asymmetry (|diff| >= 2) predicts direction: {correct_vol_signal}/{total_signals} = {correct_vol_signal/total_signals*100:.1f}%")
print(f"(50% would be random, anything above 52% is useful)")

# ============================================================
# 5. L2 BOOK DEPTH ANALYSIS
# ============================================================
print("\n\n" + "=" * 80)
print("L2 BOOK DEPTH ANALYSIS")
print("=" * 80)

# How often do we see L2 data?
has_l2 = sum(1 for t in tomatoes if t['bid2'] is not None)
print(f"Ticks with L2 bid data: {has_l2} / {len(tomatoes)}")

# L2 spread analysis
for i in range(min(20, len(tomatoes))):
    t = tomatoes[i]
    l2_info = ""
    if t['bid2'] is not None:
        l2_info = f"  L2: {t['bid2']:.0f}x{t['bid2_vol']} / {t['ask2']:.0f}x{t['ask2_vol']}"
    print(f"  tick={i:3d} mid={t['mid']:.1f} L1: {t['bid1']:.0f}x{t['bid1_vol']} / {t['ask1']:.0f}x{t['ask1_vol']}{l2_info}")

# ============================================================
# 6. TRADE SIZE ESTIMATION
# ============================================================
print("\n\n" + "=" * 80)
print("TRADE SIZE ESTIMATION")
print("=" * 80)

# When we detect a trade (PnL changed), we can estimate trade size
# from the magnitude of PnL change relative to the spread
# If we buy at ask and the mid is mid, we pay (ask - mid) per unit
# If we sell at bid, we get (mid - bid) per unit
# Half spread capture per unit ≈ spread/2 ≈ 6.5-7.0

# PnL change from a trade = position_m2m + new_trade_edge
# For a trade where we BUY qty units at ask:
#   immediate PnL impact = qty * (mid - ask) + pos * delta_mid
# Since mid = (bid+ask)/2 and we buy at ask:
#   qty * (mid - ask) = qty * (-spread/2)  (negative = cost of buying)
# BUT the PnL system values position at mid, so buying at ask costs spread/2 per unit

# Let's look at ticks where PnL jumped a lot and mid didn't change much
# Those are likely large trades (the PnL came from spread capture, not m2m)

print("\nLarge PnL changes with small mid changes (likely big trades):")
print(f"{'Tick':>5} {'dPnL':>8} {'dMid':>6} {'Est Qty':>8} {'Spread':>7}")
big_trades = []
for i in range(1, len(tomatoes)):
    dp = tomatoes[i]['pnl'] - tomatoes[i-1]['pnl']
    dm = tomatoes[i]['mid'] - tomatoes[i-1]['mid']
    spread = tomatoes[i]['ask1'] - tomatoes[i]['bid1'] if tomatoes[i]['ask1'] and tomatoes[i]['bid1'] else 13.0

    if abs(dp) > 20 and abs(dm) < 1.0:
        # Trade PnL ≈ qty * half_spread (if we capture spread)
        # OR trade PnL ≈ qty * (mid - fill_price)
        est_qty = abs(dp) / (spread / 2)
        big_trades.append((i, dp, dm, est_qty, spread))

big_trades.sort(key=lambda x: -abs(x[1]))
for tick, dp, dm, eq, sp in big_trades[:20]:
    print(f"{tick:5d} {dp:+8.2f} {dm:+6.1f} {eq:8.1f} {sp:7.1f}")

# ============================================================
# 7. FINAL NUMBERS SUMMARY
# ============================================================
print("\n\n" + "=" * 80)
print("FINAL NUMBERS: THE COMPLETE PICTURE")
print("=" * 80)

# Total PnL decomposition by source
all_dp = [tomatoes[i]['pnl'] - tomatoes[i-1]['pnl'] for i in range(1, len(tomatoes))]

# Segment by magnitude
small_gains = sum(d for d in all_dp if 0 < d < 5)
med_gains = sum(d for d in all_dp if 5 <= d < 20)
large_gains = sum(d for d in all_dp if d >= 20)
small_losses = sum(d for d in all_dp if -5 < d < 0)
med_losses = sum(d for d in all_dp if -20 < d <= -5)
large_losses = sum(d for d in all_dp if d <= -20)

print(f"\nPnL by magnitude of tick change:")
print(f"  Large gains (>=20):    {large_gains:+8.2f} ({sum(1 for d in all_dp if d >= 20)} ticks)")
print(f"  Medium gains (5-20):   {med_gains:+8.2f} ({sum(1 for d in all_dp if 5 <= d < 20)} ticks)")
print(f"  Small gains (0-5):     {small_gains:+8.2f} ({sum(1 for d in all_dp if 0 < d < 5)} ticks)")
print(f"  Small losses (0 to -5):{small_losses:+8.2f} ({sum(1 for d in all_dp if -5 < d < 0)} ticks)")
print(f"  Medium losses (-5 to -20):{med_losses:+8.2f} ({sum(1 for d in all_dp if -20 < d <= -5)} ticks)")
print(f"  Large losses (<=-20):  {large_losses:+8.2f} ({sum(1 for d in all_dp if d <= -20)} ticks)")
print(f"  TOTAL: {sum(all_dp):+8.2f}")

print(f"\nNet from each bucket:")
print(f"  Large: {large_gains + large_losses:+.2f}")
print(f"  Medium: {med_gains + med_losses:+.2f}")
print(f"  Small: {small_gains + small_losses:+.2f}")

# Efficiency metric
print(f"\n\nEFFICIENCY:")
total_abs_movement = sum(abs(tomatoes[i]['mid'] - tomatoes[i-1]['mid']) for i in range(1, len(tomatoes)))
print(f"Total absolute mid-price movement: {total_abs_movement:.1f}")
print(f"Net PnL captured: {tomatoes[-1]['pnl']:.1f}")
print(f"Capture efficiency: {tomatoes[-1]['pnl'] / total_abs_movement:.2f} per unit of movement")
print(f"  (Higher is better. 1.0 would mean capturing every single move perfectly)")

# Average position size
all_implied = []
for i in range(1, len(tomatoes)):
    dp = tomatoes[i]['pnl'] - tomatoes[i-1]['pnl']
    dm = tomatoes[i]['mid'] - tomatoes[i-1]['mid']
    if abs(dm) >= 0.5:
        all_implied.append(abs(dp / dm))

avg_abs_pos = sum(all_implied) / len(all_implied)
print(f"Average absolute implied position: {avg_abs_pos:.1f}")
print(f"PnL per unit of average position: {tomatoes[-1]['pnl'] / avg_abs_pos:.1f}")
print(f"  (How much PnL each unit of position generates over the full run)")
