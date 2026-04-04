"""
Deep analysis of EMERALDS market data to find untapped profit.
Analyzes bot order book structure, taker events, volume patterns,
and theoretical profit ceilings.
"""
import csv
import math
from collections import Counter, defaultdict

DATA_FILES = [
    "/Users/evantobias/repos/buenotraders-prosperity-imc/evan/data/round0/prices_round_0_day_-2.csv",
    "/Users/evantobias/repos/buenotraders-prosperity-imc/evan/data/round0/prices_round_0_day_-1.csv",
]

def load_emeralds(files):
    """Load all EMERALDS rows from the CSV files."""
    rows = []
    for f in files:
        with open(f) as fh:
            reader = csv.DictReader(fh, delimiter=';')
            for r in reader:
                if r['product'] == 'EMERALDS':
                    rows.append(r)
    return rows

def parse_book(r):
    """Parse a row into a structured order book snapshot."""
    snap = {
        'day': int(r['day']),
        'ts': int(r['timestamp']),
        'mid': float(r['mid_price']),
        'bids': [],
        'asks': [],
    }
    for i in range(1, 4):
        bp = r.get(f'bid_price_{i}', '')
        bv = r.get(f'bid_volume_{i}', '')
        if bp and bv and bp.strip() and bv.strip():
            snap['bids'].append((int(bp), int(bv)))
        ap = r.get(f'ask_price_{i}', '')
        av = r.get(f'ask_volume_{i}', '')
        if ap and av and ap.strip() and av.strip():
            snap['asks'].append((int(ap), int(av)))
    snap['best_bid'] = snap['bids'][0][0] if snap['bids'] else None
    snap['best_ask'] = snap['asks'][0][0] if snap['asks'] else None
    snap['spread'] = snap['best_ask'] - snap['best_bid'] if snap['best_bid'] and snap['best_ask'] else None
    return snap

def main():
    rows = load_emeralds(DATA_FILES)
    snaps = [parse_book(r) for r in rows]

    print("=" * 80)
    print("EMERALDS DEEP MARKET ANALYSIS")
    print("=" * 80)

    # ── 1. Basic Stats ──────────────────────────────────────────────
    print("\n" + "─" * 60)
    print("1. BASIC STATS")
    print("─" * 60)

    days = sorted(set(s['day'] for s in snaps))
    for day in days:
        day_snaps = [s for s in snaps if s['day'] == day]
        ts_range = (min(s['ts'] for s in day_snaps), max(s['ts'] for s in day_snaps))
        print(f"  Day {day}: {len(day_snaps)} ticks, ts range {ts_range[0]}-{ts_range[1]}")
    print(f"  Total snapshots: {len(snaps)}")

    # ── 2. Order Book Structure ─────────────────────────────────────
    print("\n" + "─" * 60)
    print("2. TYPICAL BOT ORDER BOOK STRUCTURE")
    print("─" * 60)

    # Count price levels and volumes
    bid_prices = Counter()
    ask_prices = Counter()
    bid_vol_at_price = defaultdict(list)
    ask_vol_at_price = defaultdict(list)
    num_bid_levels = Counter()
    num_ask_levels = Counter()

    for s in snaps:
        num_bid_levels[len(s['bids'])] += 1
        num_ask_levels[len(s['asks'])] += 1
        for p, v in s['bids']:
            bid_prices[p] += 1
            bid_vol_at_price[p].append(v)
        for p, v in s['asks']:
            ask_prices[p] += 1
            ask_vol_at_price[p].append(v)

    print("\n  Bid level count distribution:")
    for k in sorted(num_bid_levels):
        print(f"    {k} levels: {num_bid_levels[k]} ticks ({100*num_bid_levels[k]/len(snaps):.1f}%)")
    print("  Ask level count distribution:")
    for k in sorted(num_ask_levels):
        print(f"    {k} levels: {num_ask_levels[k]} ticks ({100*num_ask_levels[k]/len(snaps):.1f}%)")

    print("\n  Bid prices seen (price -> frequency, avg vol, min vol, max vol):")
    for p in sorted(bid_prices.keys(), reverse=True):
        vols = bid_vol_at_price[p]
        print(f"    {p}: {bid_prices[p]} ticks, vol avg={sum(vols)/len(vols):.1f}, min={min(vols)}, max={max(vols)}")

    print("\n  Ask prices seen (price -> frequency, avg vol, min vol, max vol):")
    for p in sorted(ask_prices.keys()):
        vols = ask_vol_at_price[p]
        print(f"    {p}: {ask_prices[p]} ticks, vol avg={sum(vols)/len(vols):.1f}, min={min(vols)}, max={max(vols)}")

    # ── 3. Spread Analysis ──────────────────────────────────────────
    print("\n" + "─" * 60)
    print("3. SPREAD ANALYSIS")
    print("─" * 60)

    spreads = Counter()
    for s in snaps:
        if s['spread'] is not None:
            spreads[s['spread']] += 1

    print("  Spread distribution:")
    for sp in sorted(spreads):
        print(f"    Spread {sp}: {spreads[sp]} ticks ({100*spreads[sp]/len(snaps):.1f}%)")

    # ── 4. Mid Price Deviations ─────────────────────────────────────
    print("\n" + "─" * 60)
    print("4. MID PRICE DEVIATIONS FROM 10,000")
    print("─" * 60)

    deviations = [(s['day'], s['ts'], s['mid'], s['best_bid'], s['best_ask'])
                  for s in snaps if abs(s['mid'] - 10000) > 0.01]

    if not deviations:
        print("  No mid price deviations found! Mid is ALWAYS 10,000.")
    else:
        print(f"  Found {len(deviations)} ticks with mid != 10,000:")
        for d, ts, mid, bb, ba in deviations:
            print(f"    Day {d}, ts={ts}: mid={mid}, best_bid={bb}, best_ask={ba}")

    # ── 5. Taker Events (book changes tick-to-tick) ─────────────────
    print("\n" + "─" * 60)
    print("5. TAKER EVENT ANALYSIS")
    print("─" * 60)
    print("  A 'taker event' = tick where the book changes from the previous tick")
    print("  (volume consumed, price levels change, etc.)")

    for day in days:
        day_snaps = sorted([s for s in snaps if s['day'] == day], key=lambda x: x['ts'])
        print(f"\n  Day {day}:")

        taker_events = []
        anomalous_ticks = []

        for i in range(1, len(day_snaps)):
            prev = day_snaps[i-1]
            curr = day_snaps[i]

            # Detect changes
            changes = []

            # Best bid/ask changes
            if prev['best_bid'] != curr['best_bid']:
                changes.append(f"best_bid {prev['best_bid']}->{curr['best_bid']}")
            if prev['best_ask'] != curr['best_ask']:
                changes.append(f"best_ask {prev['best_ask']}->{curr['best_ask']}")

            # Volume changes at existing price levels
            prev_bids = dict(prev['bids'])
            curr_bids = dict(curr['bids'])
            prev_asks = dict(prev['asks'])
            curr_asks = dict(curr['asks'])

            # Check for volume consumption at best levels
            bb_vol_change = curr_bids.get(prev['best_bid'], 0) - prev_bids.get(prev['best_bid'], 0)
            ba_vol_change = curr_asks.get(prev['best_ask'], 0) - prev_asks.get(prev['best_ask'], 0)

            if bb_vol_change != 0:
                changes.append(f"bid_vol@{prev['best_bid']}: {prev_bids.get(prev['best_bid'],0)}->{curr_bids.get(prev['best_bid'],0)}")
            if ba_vol_change != 0:
                changes.append(f"ask_vol@{prev['best_ask']}: {prev_asks.get(prev['best_ask'],0)}->{curr_asks.get(prev['best_ask'],0)}")

            # Check for new levels appearing
            for p in curr_bids:
                if p not in prev_bids:
                    changes.append(f"new_bid@{p}: vol={curr_bids[p]}")
            for p in curr_asks:
                if p not in prev_asks:
                    changes.append(f"new_ask@{p}: vol={curr_asks[p]}")

            # Check for levels disappearing
            for p in prev_bids:
                if p not in curr_bids:
                    changes.append(f"lost_bid@{p}: was vol={prev_bids[p]}")
            for p in prev_asks:
                if p not in curr_asks:
                    changes.append(f"lost_ask@{p}: was vol={prev_asks[p]}")

            is_taker = len(changes) > 0

            # Anomalous = price levels or structure radically different
            is_anomalous = (curr['best_bid'] != 9992 or curr['best_ask'] != 10008 or
                           len(curr['bids']) != 2 or len(curr['asks']) != 2)

            if is_taker:
                taker_events.append({
                    'ts': curr['ts'],
                    'changes': changes,
                    'snap': curr,
                    'prev': prev,
                    'anomalous': is_anomalous,
                })
            if is_anomalous:
                anomalous_ticks.append(curr)

        print(f"    Total ticks: {len(day_snaps)}")
        print(f"    Ticks with changes: {len(taker_events)}")
        print(f"    Ticks WITHOUT changes: {len(day_snaps) - 1 - len(taker_events)}")
        print(f"    Anomalous ticks (non-standard book): {len(anomalous_ticks)}")

        # Show anomalous ticks in detail
        if anomalous_ticks:
            print(f"\n    ANOMALOUS TICKS (non-standard order book):")
            for s in anomalous_ticks[:20]:
                print(f"      ts={s['ts']}: bids={s['bids']}, asks={s['asks']}, mid={s['mid']}")

    # ── 6. What are the "normal" volume ranges? ─────────────────────
    print("\n" + "─" * 60)
    print("6. L1 VOLUME ANALYSIS (bot volume at best bid/ask)")
    print("─" * 60)

    l1_bid_vols = [s['bids'][0][1] for s in snaps if s['bids'] and s['bids'][0][0] == 9992]
    l1_ask_vols = [s['asks'][0][1] for s in snaps if s['asks'] and s['asks'][0][0] == 10008]
    l2_bid_vols = []
    l2_ask_vols = []
    for s in snaps:
        if len(s['bids']) >= 2 and s['bids'][1][0] == 9990:
            l2_bid_vols.append(s['bids'][1][1])
        if len(s['asks']) >= 2 and s['asks'][1][0] == 10010:
            l2_ask_vols.append(s['asks'][1][1])

    def vol_stats(name, vols):
        if not vols:
            print(f"  {name}: no data")
            return
        print(f"  {name}:")
        print(f"    Count: {len(vols)}")
        print(f"    Min: {min(vols)}, Max: {max(vols)}")
        print(f"    Mean: {sum(vols)/len(vols):.1f}")
        print(f"    Median: {sorted(vols)[len(vols)//2]}")
        # Distribution
        vc = Counter(vols)
        print(f"    Distribution: {dict(sorted(vc.items()))}")

    vol_stats("L1 bid @ 9992", l1_bid_vols)
    vol_stats("L1 ask @ 10008", l1_ask_vols)
    vol_stats("L2 bid @ 9990", l2_bid_vols)
    vol_stats("L2 ask @ 10010", l2_ask_vols)

    # ── 7. Theoretical Max Profit — Penny Jumping ───────────────────
    print("\n" + "─" * 60)
    print("7. THEORETICAL MAX PROFIT (penny-jump at 9999/10001)")
    print("─" * 60)
    print("  If we post at 9999 bid and 10001 ask, and get filled every tick:")

    # The question: how much volume can we turn over per tick?
    # With position limit of 50, and spread of 2 (buy@9999 sell@10001),
    # we earn 2 per round-trip unit.

    # But the real question: how often do bots trade with us?
    # The bot book is 9992/10008. If we post 9999/10001, we penny-jump.
    # The key is: do other bots TAKE from us?

    # Let's compute: if we could maintain perfect 0 position by always
    # buying and selling equal amounts, what's the theoretical max?

    FAIR = 10000

    # Count ticks per day
    for day in days:
        day_snaps = sorted([s for s in snaps if s['day'] == day], key=lambda x: x['ts'])
        num_ticks = len(day_snaps)

        # Scenario 1: Post at fair-1/fair+1 (9999/10001), get filled every tick
        # This gives 2 profit per round-trip, but we need to close position
        # Max: fill 50 on each side per tick, but limited by position
        # Realistic: we cycle position between -50 and 50

        # Actually, let's think about this differently.
        # Each tick, if we can buy X at 9999 and sell X at 10001, we make 2*X.
        # But to sell X, we need position >= X. To buy X, we need pos <= 50-X.
        # So we need to cycle: buy 50, sell 50, buy 50, sell 50...
        # Each cycle: buy 50 at 9999 (cost 499,950), sell 50 at 10001 (revenue 500,050)
        # Profit per cycle: 100 (2 per unit * 50 units)
        # Cycle takes 2 ticks minimum (buy tick + sell tick)

        cycles = num_ticks // 2
        profit_scenario1 = cycles * 50 * 2
        print(f"\n  Day {day} ({num_ticks} ticks):")
        print(f"    Scenario 1 (post 9999/10001, fill every tick, 50 units):")
        print(f"      Max cycles: {cycles}, Profit: {profit_scenario1}")

        # Scenario 2: We don't fill every tick. What if we fill only when bots take?
        # For this, look at volume changes that suggest taking activity

    # ── 8. Actual bot behavior analysis ─────────────────────────────
    print("\n" + "─" * 60)
    print("8. TICK-BY-TICK VOLUME CHANGES (detecting consumption)")
    print("─" * 60)
    print("  When L1 volume drops significantly between ticks, it suggests")
    print("  someone is taking liquidity (consuming orders).")

    for day in days:
        day_snaps = sorted([s for s in snaps if s['day'] == day], key=lambda x: x['ts'])

        bid_drops = []
        ask_drops = []
        both_changes = []

        for i in range(1, len(day_snaps)):
            prev = day_snaps[i-1]
            curr = day_snaps[i]

            # L1 volume at standard prices
            prev_bid_vol = dict(prev['bids']).get(9992, 0)
            curr_bid_vol = dict(curr['bids']).get(9992, 0)
            prev_ask_vol = dict(prev['asks']).get(10008, 0)
            curr_ask_vol = dict(curr['asks']).get(10008, 0)

            bid_delta = curr_bid_vol - prev_bid_vol
            ask_delta = curr_ask_vol - prev_ask_vol

            if bid_delta != 0 or ask_delta != 0:
                both_changes.append({
                    'ts': curr['ts'],
                    'bid_delta': bid_delta,
                    'ask_delta': ask_delta,
                    'prev_bid_vol': prev_bid_vol,
                    'curr_bid_vol': curr_bid_vol,
                    'prev_ask_vol': prev_ask_vol,
                    'curr_ask_vol': curr_ask_vol,
                    'prev': prev,
                    'curr': curr,
                })

            if bid_delta < 0:
                bid_drops.append({'ts': curr['ts'], 'delta': bid_delta, 'from': prev_bid_vol, 'to': curr_bid_vol})
            if ask_delta < 0:
                ask_drops.append({'ts': curr['ts'], 'delta': ask_delta, 'from': prev_ask_vol, 'to': curr_ask_vol})

        print(f"\n  Day {day}:")
        print(f"    Ticks with ANY volume change: {len(both_changes)}/{len(day_snaps)-1}")
        print(f"    Ticks with bid volume DROP: {len(bid_drops)}")
        print(f"    Ticks with ask volume DROP: {len(ask_drops)}")

        # Estimate: ticks where volume is UNCHANGED = replenishment ticks
        unchanged = len(day_snaps) - 1 - len(both_changes)
        print(f"    Ticks with ZERO change: {unchanged}")

        # Distribution of deltas
        bid_deltas = [c['bid_delta'] for c in both_changes if c['bid_delta'] != 0]
        ask_deltas = [c['ask_delta'] for c in both_changes if c['ask_delta'] != 0]

        if bid_deltas:
            print(f"\n    Bid volume delta distribution:")
            dc = Counter(bid_deltas)
            for k in sorted(dc):
                print(f"      delta={k:+d}: {dc[k]} times")
        if ask_deltas:
            print(f"\n    Ask volume delta distribution:")
            dc = Counter(ask_deltas)
            for k in sorted(dc):
                print(f"      delta={k:+d}: {dc[k]} times")

    # ── 9. Theoretical max with realistic taking ────────────────────
    print("\n" + "─" * 60)
    print("9. THEORETICAL MAX PROFIT — REALISTIC SCENARIOS")
    print("─" * 60)

    for day in days:
        day_snaps = sorted([s for s in snaps if s['day'] == day], key=lambda x: x['ts'])
        num_ticks = len(day_snaps)

        print(f"\n  Day {day} ({num_ticks} ticks):")

        # Scenario A: Post at 9999/10001 (1 from fair), fill every tick, max vol
        # Perfect round-trip: buy 50 at 9999, sell 50 at 10001 next tick
        # Profit per pair: 50 * 2 = 100
        profit_a = (num_ticks // 2) * 50 * 2
        print(f"    A) Post 9999/10001, fill 50 every tick, perfect cycling:")
        print(f"       {num_ticks // 2} round-trips * 50 units * 2 profit = {profit_a}")

        # Scenario B: Post at 9998/10002 (2 from fair), less likely fills
        profit_b = (num_ticks // 2) * 50 * 4
        print(f"    B) Post 9998/10002, fill 50 every tick, perfect cycling:")
        print(f"       {num_ticks // 2} round-trips * 50 units * 4 profit = {profit_b}")

        # Scenario C: Only fill when volume CHANGES (conservative)
        day_changes = []
        for i in range(1, len(day_snaps)):
            prev = day_snaps[i-1]
            curr = day_snaps[i]
            prev_bid_vol = dict(prev['bids']).get(9992, 0)
            curr_bid_vol = dict(curr['bids']).get(9992, 0)
            prev_ask_vol = dict(prev['asks']).get(10008, 0)
            curr_ask_vol = dict(curr['asks']).get(10008, 0)
            if prev_bid_vol != curr_bid_vol or prev_ask_vol != curr_ask_vol:
                day_changes.append(1)

        active_ticks = len(day_changes)
        profit_c = (active_ticks // 2) * 50 * 2
        print(f"    C) Only fill on 'active' ticks ({active_ticks}), 9999/10001:")
        print(f"       {active_ticks // 2} round-trips * 50 units * 2 profit = {profit_c}")

    # ── 10. Pattern analysis: timing of volume changes ──────────────
    print("\n" + "─" * 60)
    print("10. PATTERN ANALYSIS: WHEN DO VOLUME CHANGES HAPPEN?")
    print("─" * 60)

    for day in days:
        day_snaps = sorted([s for s in snaps if s['day'] == day], key=lambda x: x['ts'])

        change_times = []
        for i in range(1, len(day_snaps)):
            prev = day_snaps[i-1]
            curr = day_snaps[i]
            prev_bids = dict(prev['bids'])
            curr_bids = dict(curr['bids'])
            prev_asks = dict(prev['asks'])
            curr_asks = dict(curr['asks'])
            if prev_bids != curr_bids or prev_asks != curr_asks:
                change_times.append(curr['ts'])

        if not change_times:
            print(f"\n  Day {day}: No changes detected")
            continue

        print(f"\n  Day {day}: {len(change_times)} change events")

        # Check if periodic
        if len(change_times) >= 2:
            gaps = [change_times[i+1] - change_times[i] for i in range(len(change_times)-1)]
            gap_counter = Counter(gaps)
            print(f"    Gap distribution (time between changes):")
            for g in sorted(gap_counter):
                print(f"      gap={g}: {gap_counter[g]} times ({100*gap_counter[g]/len(gaps):.1f}%)")
            print(f"    Mean gap: {sum(gaps)/len(gaps):.1f}")
            print(f"    Min gap: {min(gaps)}, Max gap: {max(gaps)}")

        # Check clustering by 1000-tick buckets
        bucket_size = 10000
        buckets = Counter()
        for t in change_times:
            buckets[t // bucket_size] += 1
        print(f"    Changes per {bucket_size}-tick bucket:")
        for b in sorted(buckets):
            print(f"      ts {b*bucket_size}-{(b+1)*bucket_size}: {buckets[b]} changes")

    # ── 11. Simulate different maker strategies ─────────────────────
    print("\n" + "─" * 60)
    print("11. STRATEGY SIMULATION: WHAT SPREAD SHOULD WE POST?")
    print("─" * 60)
    print("  Key insight: The BOT book is at 9992/10008 (spread=16).")
    print("  If we post INSIDE this, we become the new best bid/ask.")
    print("  The question: at what price do bot TAKERS actually trade?")
    print()

    # The fundamental question: when do taker bots arrive, and at what price
    # do they cross the spread? If they only appear occasionally and always
    # trade at 9992/10008, then our pennyjump at 9993/10007 would get
    # filled instead.

    # But we can infer: if the bot book volume DROPS, something took it.
    # And if our order would have been in front, we would have gotten filled first.

    # Let's compute: how much volume is consumed per tick on average?
    print("  Volume consumption analysis:")
    for day in days:
        day_snaps = sorted([s for s in snaps if s['day'] == day], key=lambda x: x['ts'])

        total_bid_consumed = 0
        total_ask_consumed = 0
        consumption_events_bid = 0
        consumption_events_ask = 0

        for i in range(1, len(day_snaps)):
            prev = day_snaps[i-1]
            curr = day_snaps[i]

            # Check all bid levels
            prev_bid_total = sum(v for _, v in prev['bids'])
            curr_bid_total = sum(v for _, v in curr['bids'])
            prev_ask_total = sum(v for _, v in prev['asks'])
            curr_ask_total = sum(v for _, v in curr['asks'])

            bid_consumed = max(0, prev_bid_total - curr_bid_total)
            ask_consumed = max(0, prev_ask_total - curr_ask_total)

            if bid_consumed > 0:
                total_bid_consumed += bid_consumed
                consumption_events_bid += 1
            if ask_consumed > 0:
                total_ask_consumed += ask_consumed
                consumption_events_ask += 1

        print(f"\n  Day {day}:")
        print(f"    Bid-side consumption: {total_bid_consumed} units over {consumption_events_bid} events")
        print(f"    Ask-side consumption: {total_ask_consumed} units over {consumption_events_ask} events")
        if consumption_events_bid > 0:
            print(f"    Avg bid consumption per event: {total_bid_consumed/consumption_events_bid:.1f}")
        if consumption_events_ask > 0:
            print(f"    Avg ask consumption per event: {total_ask_consumed/consumption_events_ask:.1f}")

    # ── 12. The Key Question: What Would Our Bot See? ───────────────
    print("\n" + "─" * 60)
    print("12. WHAT OUR CURRENT BOT SEES vs WHAT IT COULD DO")
    print("─" * 60)

    # Simulate our current strategy's behavior tick by tick
    for day in days:
        day_snaps = sorted([s for s in snaps if s['day'] == day], key=lambda x: x['ts'])

        print(f"\n  Day {day}:")

        # With ONLY bot orders (no other participants), the book is always:
        # Bids: 9992 (10-15), 9990 (20-30)
        # Asks: 10008 (10-15), 10010 (20-30)

        # Our bot posts at 9999/10001 (penny jump)
        # These become the new best bid/ask

        # The ONLY way we make money:
        # 1. A taker bot comes and buys from us at 10001 or sells to us at 9999
        # 2. We take from the bot book at 9992 or 10008 (but that LOSES money if fair=10000)

        # So the question is: how many taker events happen, and at what volume?

        # Look at ticks where a 3rd level appears or L1 changes dramatically
        # This suggests a taker arrived and consumed liquidity

        taker_buy_events = []  # someone bought (ask volume dropped)
        taker_sell_events = []  # someone sold (bid volume dropped)

        for i in range(1, len(day_snaps)):
            prev = day_snaps[i-1]
            curr = day_snaps[i]

            prev_ask_vol_l1 = dict(prev['asks']).get(10008, 0)
            curr_ask_vol_l1 = dict(curr['asks']).get(10008, 0)
            prev_bid_vol_l1 = dict(prev['bids']).get(9992, 0)
            curr_bid_vol_l1 = dict(curr['bids']).get(9992, 0)

            # Ask volume dropped = someone BOUGHT from the asks
            if curr_ask_vol_l1 < prev_ask_vol_l1:
                consumed = prev_ask_vol_l1 - curr_ask_vol_l1
                taker_buy_events.append({'ts': curr['ts'], 'vol': consumed})

            # Bid volume dropped = someone SOLD into the bids
            if curr_bid_vol_l1 < prev_bid_vol_l1:
                consumed = prev_bid_vol_l1 - curr_bid_vol_l1
                taker_sell_events.append({'ts': curr['ts'], 'vol': consumed})

        total_buy_vol = sum(e['vol'] for e in taker_buy_events)
        total_sell_vol = sum(e['vol'] for e in taker_sell_events)

        print(f"    Taker BUY events (ask consumed): {len(taker_buy_events)}, total vol: {total_buy_vol}")
        print(f"    Taker SELL events (bid consumed): {len(taker_sell_events)}, total vol: {total_sell_vol}")

        # If we were penny-jumping, we would intercept these taker events
        # BUY taker -> would have bought from OUR ask at 10001 instead of 10008
        # SELL taker -> would have sold to OUR bid at 9999 instead of 9992

        # But wait — the taker would get a BETTER price from us!
        # Taker buying: pays 10001 instead of 10008 (saves 7 per unit)
        # Taker selling: gets 9999 instead of 9992 (gets 7 more per unit)

        # So the taker volume we can intercept is bounded by these events
        # But our position limit is 50, and we need to cycle

        # Max profit if we intercept ALL:
        # Each buy we sell at 10001 (profit 1 per unit from fair 10000)
        # Each sell we buy at 9999 (profit 1 per unit from fair 10000)
        # But we need to close positions eventually!

        # Let's simulate perfect position management
        pos = 0
        total_profit = 0
        LIMIT = 50

        # Merge events chronologically
        all_events = []
        for e in taker_buy_events:
            all_events.append(('buy', e['ts'], e['vol']))  # taker buys = we sell
        for e in taker_sell_events:
            all_events.append(('sell', e['ts'], e['vol']))  # taker sells = we buy
        all_events.sort(key=lambda x: x[1])

        for direction, ts, vol in all_events:
            if direction == 'buy':  # taker buys from us, we sell
                can_sell = min(vol, LIMIT + pos)
                if can_sell > 0:
                    total_profit += can_sell * 1  # sell at 10001, profit 1 per unit
                    pos -= can_sell
            elif direction == 'sell':  # taker sells to us, we buy
                can_buy = min(vol, LIMIT - pos)
                if can_buy > 0:
                    total_profit += can_buy * 1  # buy at 9999, profit 1 per unit
                    pos += can_buy

        # Close remaining position at fair value (0 cost)
        print(f"    Penny-jump profit (9999/10001), intercepting taker events:")
        print(f"      Profit: {total_profit} (final pos: {pos})")
        print(f"      Note: this assumes we close remaining position at 10000 (0 cost)")

        # Same but with wider spread: 9998/10002
        pos = 0
        total_profit_wide = 0
        for direction, ts, vol in all_events:
            if direction == 'buy':
                can_sell = min(vol, LIMIT + pos)
                if can_sell > 0:
                    total_profit_wide += can_sell * 2
                    pos -= can_sell
            elif direction == 'sell':
                can_buy = min(vol, LIMIT - pos)
                if can_buy > 0:
                    total_profit_wide += can_buy * 2
                    pos += can_buy
        print(f"    Wide spread profit (9998/10002):")
        print(f"      Profit: {total_profit_wide} (final pos: {pos})")

        # 9997/10003
        pos = 0
        total_profit_wider = 0
        for direction, ts, vol in all_events:
            if direction == 'buy':
                can_sell = min(vol, LIMIT + pos)
                if can_sell > 0:
                    total_profit_wider += can_sell * 3
                    pos -= can_sell
            elif direction == 'sell':
                can_buy = min(vol, LIMIT - pos)
                if can_buy > 0:
                    total_profit_wider += can_buy * 3
                    pos += can_buy
        print(f"    Wider spread profit (9997/10003):")
        print(f"      Profit: {total_profit_wider} (final pos: {pos})")

    # ── 13. The REAL Constraint: Do Takers See Our Orders? ──────────
    print("\n" + "─" * 60)
    print("13. CRITICAL INSIGHT: ORDER EXECUTION MODEL")
    print("─" * 60)
    print("""
  In IMC Prosperity, OUR orders are processed LAST after all bot orders.
  This means:
    1. Bot makers post their book (9992/10008)
    2. Bot takers trade against the book
    3. OUR orders are processed against the REMAINING book

  So we CANNOT penny-jump to intercept bot taker events!
  Our orders only interact with what's LEFT after bots finish.

  The only way we profit on EMERALDS:
    a) TAKE: Buy at asks <= 9999, sell at bids >= 10001
       (only possible when book is anomalous)
    b) MAKE: Post orders, and OTHER player bots take from us
       (but in tutorial, we're the only player)
    c) MAKE: Post orders that the BOT SYSTEM matches against
       bot taker flow (we get filled as makers)

  The question becomes: does our penny-jump actually work because
  the matching engine processes our maker orders BEFORE bot takers?
  Or do we only see the residual book?

  Given current scores (~1,050 EMERALDS), something IS working.
  Let's reverse-engineer what's happening.
""")

    # ── 14. Reverse-engineer the 1,050 score ────────────────────────
    print("─" * 60)
    print("14. REVERSE-ENGINEERING THE ~1,050 EMERALDS SCORE")
    print("─" * 60)

    # If we make 1,050 per day with spread of 2 (buy 9999, sell 10001):
    # 1,050 / 2 = 525 units traded (round-trips)
    # 525 units / 50 limit = 10.5 full position cycles
    # 10,000 ticks / 10.5 cycles = ~950 ticks per cycle

    # If we make 1,050 per day with mixed spread:
    # Some at 1 profit (clear), some at higher

    print("  If profit = 1,050 and spread = 2 (buy@9999, sell@10001):")
    print(f"    Round-trip units: {1050/2:.0f}")
    print(f"    Full position cycles (50 units each): {1050/2/50:.1f}")
    print(f"    Ticks per cycle: {10000/(1050/2/50):.0f}")
    print()
    print("  If profit = 1,050 and avg edge = 1 per unit:")
    print(f"    Total units traded: 1,050")
    print(f"    Full position cycles: {1050/50:.1f}")
    print(f"    Ticks per cycle: {10000/(1050/50):.0f}")
    print()

    # The bot volume changes we observed tell us how many taker events happen
    for day in days:
        day_snaps = sorted([s for s in snaps if s['day'] == day], key=lambda x: x['ts'])
        total_vol_change = 0
        for i in range(1, len(day_snaps)):
            prev = day_snaps[i-1]
            curr = day_snaps[i]
            for p, v in prev['bids']:
                cv = dict(curr['bids']).get(p, 0)
                if cv < v:
                    total_vol_change += (v - cv)
            for p, v in prev['asks']:
                cv = dict(curr['asks']).get(p, 0)
                if cv < v:
                    total_vol_change += (v - cv)

        print(f"  Day {day}: total volume consumed from bot book: {total_vol_change}")

    # ── 15. The MAKE profit model ───────────────────────────────────
    print("\n" + "─" * 60)
    print("15. MAKE PROFIT MODEL: HOW PENNY-JUMPING WORKS")
    print("─" * 60)
    print("""
  When we penny-jump (post at 9993 bid / 10007 ask), here's what happens:

  The MATCHING ENGINE processes our orders against incoming market orders.
  Bot takers submit market orders to buy/sell.

  If we're at 10007 ask and the bot book is at 10008 ask:
    - A taker wanting to BUY hits OUR 10007 first (better price)
    - We sell at 10007, profit = 10007 - 10000 = 7

  If we're at 9993 bid and the bot book is at 9992 bid:
    - A taker wanting to SELL hits OUR 9993 first (better price for them)
    - We buy at 9993, profit = 10000 - 9993 = 7

  Wait... if our penny-jump bot posts at fair-1 / fair+1:
    - We buy at 9999, sell at 10001
    - Profit per unit: only 1 on each side
    - But we're way inside the spread, so more fills

  Wider spread = more profit per fill, fewer fills
  Narrower spread = less profit per fill, more fills

  CONCLUSION: The constraint is # of taker events * volume per event.
  Our profit ceiling = min(taker_volume * edge, position_cycling_capacity)
""")

    # ── 16. Estimate taker flow per day ─────────────────────────────
    print("─" * 60)
    print("16. TAKER FLOW ESTIMATION")
    print("─" * 60)

    for day in days:
        day_snaps = sorted([s for s in snaps if s['day'] == day], key=lambda x: x['ts'])

        # Track ALL volume changes more carefully
        # Volume can: decrease (consumption), increase (replenishment), stay same

        buy_flow = 0  # total units bought by takers (ask side consumed)
        sell_flow = 0  # total units sold by takers (bid side consumed)
        replenish_bid = 0
        replenish_ask = 0

        for i in range(1, len(day_snaps)):
            prev = day_snaps[i-1]
            curr = day_snaps[i]

            # Compare total volumes
            prev_total_bid = sum(v for _, v in prev['bids'])
            curr_total_bid = sum(v for _, v in curr['bids'])
            prev_total_ask = sum(v for _, v in prev['asks'])
            curr_total_ask = sum(v for _, v in curr['asks'])

            # If total dropped, taker consumed
            if curr_total_bid < prev_total_bid:
                sell_flow += (prev_total_bid - curr_total_bid)
            elif curr_total_bid > prev_total_bid:
                replenish_bid += (curr_total_bid - prev_total_bid)

            if curr_total_ask < prev_total_ask:
                buy_flow += (prev_total_ask - curr_total_ask)
            elif curr_total_ask > prev_total_ask:
                replenish_ask += (curr_total_ask - prev_total_ask)

        print(f"\n  Day {day}:")
        print(f"    Buy taker flow (ask consumed): {buy_flow} units")
        print(f"    Sell taker flow (bid consumed): {sell_flow} units")
        print(f"    Total taker flow: {buy_flow + sell_flow} units")
        print(f"    Bid replenishment: {replenish_bid} units")
        print(f"    Ask replenishment: {replenish_ask} units")

        # Now compute theoretical profits at various edges
        print(f"\n    Theoretical profit at various edges (no position constraint):")
        for edge in [1, 2, 3, 4, 5, 6, 7, 8]:
            profit = (buy_flow + sell_flow) * edge
            print(f"      Edge {edge} (post fair±{edge}): {profit}")

        # With position constraint of 50:
        print(f"\n    With position constraint (limit=50):")
        for edge in [1, 2, 3, 4, 7, 8]:
            # Simulate with position management
            pos = 0
            profit = 0
            missed_buy = 0
            missed_sell = 0

            for j in range(1, len(day_snaps)):
                prev2 = day_snaps[j-1]
                curr2 = day_snaps[j]

                prev_total_bid2 = sum(v for _, v in prev2['bids'])
                curr_total_bid2 = sum(v for _, v in curr2['bids'])
                prev_total_ask2 = sum(v for _, v in prev2['asks'])
                curr_total_ask2 = sum(v for _, v in curr2['asks'])

                # Buy taker event -> we sell
                if curr_total_ask2 < prev_total_ask2:
                    vol = prev_total_ask2 - curr_total_ask2
                    can_sell = min(vol, 50 + pos)
                    if can_sell > 0:
                        profit += can_sell * edge
                        pos -= can_sell
                    missed_sell += vol - can_sell

                # Sell taker event -> we buy
                if curr_total_bid2 < prev_total_bid2:
                    vol = prev_total_bid2 - curr_total_bid2
                    can_buy = min(vol, 50 - pos)
                    if can_buy > 0:
                        profit += can_buy * edge
                        pos += can_buy
                    missed_buy += vol - can_buy

            # Closing position cost (assume we close at fair, 0 cost)
            print(f"      Edge {edge}: profit={profit}, final_pos={pos}, missed_buy={missed_buy}, missed_sell={missed_sell}")

    # ── 17. The Volume Puzzle ───────────────────────────────────────
    print("\n" + "─" * 60)
    print("17. EVERY TICK DETAIL: FIRST 100 TICKS")
    print("─" * 60)
    print("  Showing first 100 ticks of Day -2 to understand the pattern:")

    day_snaps = sorted([s for s in snaps if s['day'] == -2], key=lambda x: x['ts'])
    prev_snap = None
    for i, s in enumerate(day_snaps[:100]):
        change = ""
        if prev_snap:
            for p, v in prev_snap['bids']:
                cv = dict(s['bids']).get(p, 0)
                if cv != v:
                    change += f"bid@{p}:{v}->{cv} "
            for p, v in prev_snap['asks']:
                cv = dict(s['asks']).get(p, 0)
                if cv != v:
                    change += f"ask@{p}:{v}->{cv} "
            new_prices = set(p for p,v in s['bids']) - set(p for p,v in prev_snap['bids'])
            for p in new_prices:
                change += f"NEW_BID@{p}:{dict(s['bids'])[p]} "
            new_prices = set(p for p,v in s['asks']) - set(p for p,v in prev_snap['asks'])
            for p in new_prices:
                change += f"NEW_ASK@{p}:{dict(s['asks'])[p]} "

        if change or i == 0:
            print(f"    ts={s['ts']:5d}: bids={s['bids']}, asks={s['asks']}, mid={s['mid']} {change}")
        prev_snap = s

    # ── 18. Summary ─────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("SUMMARY & RECOMMENDATIONS")
    print("=" * 80)


if __name__ == '__main__':
    main()
