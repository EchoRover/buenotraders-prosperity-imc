"""
TOMATOES Market-Making Simulation (fixed)
Properly models Prosperity order mechanics:
  - We place limit orders. Bots trade against us.
  - Our BID (buy order) gets filled if bot is willing to sell at our price
    i.e. our bid is attractive enough. In practice, we get filled when price moves through us.
  - Our ASK (sell order) gets filled similarly.

  Key insight: In Prosperity, we trade LAST after bots. Our orders sit in the book,
  and we get filled at our price. The question is: when does our price get hit?

  For market-making, we place:
    buy_order at some price below mid
    sell_order at some price above mid

  We get filled on our buy if the bot's ask drops to our level (or below).
  We get filled on our sell if the bot's bid rises to our level (or above).

  BUT actually, in Prosperity the mechanic is simpler:
  - We submit orders each tick
  - If our buy price >= bot's ask_price, trade happens at bot's ask_price
  - If our sell price <= bot's bid_price, trade happens at bot's bid_price

  So to BUY, we need to bid AT or ABOVE the bot's ask.
  To SELL, we need to ask AT or BELOW the bot's bid.

  For market-making, the strategy is:
  - Place buy at (mid - offset) hoping to get filled when price dips
  - Place sell at (mid + offset) hoping to get filled when price rises
  - The fill happens when bot's ask <= our buy price, or bot's bid >= our sell price
"""
import pandas as pd
import numpy as np

# Load data
dfs = []
for day in [-2, -1]:
    path = f"/Users/evantobias/repos/buenotraders-prosperity-imc/evan/data/round0/prices_round_0_day_{day}.csv"
    df = pd.read_csv(path, sep=";")
    dfs.append(df)
data = pd.concat(dfs, ignore_index=True)
tom = data[data["product"] == "TOMATOES"].copy().reset_index(drop=True)

tom["spread"] = tom["ask_price_1"] - tom["bid_price_1"]
tom["mid_price_calc"] = (tom["bid_price_1"] + tom["ask_price_1"]) / 2

print("=" * 70)
print("MARKET-MAKING SIMULATION (CORRECTED)")
print("=" * 70)
print()

# Strategy 1: Quote at fixed offset from mid price
# We place: buy at floor(mid - offset), sell at ceil(mid + offset)
# Fill: buy fills if our_bid >= ask_price_1, sell fills if our_ask <= bid_price_1
# Fill price: we trade at OUR price (limit order)

print("Strategy 1: Fixed offset from mid price")
print("  We place buy at round(mid - offset), sell at round(mid + offset)")
print("  Fill when: our buy >= bot ask (we overpay), or our sell <= bot bid (we undersell)")
print()

results = []
for offset in range(1, 15):
    total_pnl = 0
    total_buys = 0
    total_sells = 0
    position = 0
    pos_limit = 50
    inventory_cost = 0

    for _, row in tom.iterrows():
        mid = row["mid_price"]
        our_bid = int(round(mid - offset))
        our_ask = int(round(mid + offset))

        bot_ask = row["ask_price_1"]
        bot_bid = row["bid_price_1"]

        # Buy: our bid must be >= bot's ask
        # This means offset must be small enough that mid - offset >= ask
        # i.e., offset <= mid - ask = -(ask - mid) = -half_spread
        # Since half_spread ~6.5, offset needs to be <= -6.5 which is never true!
        #
        # So the CORRECT model for market-making is:
        # We quote INSIDE the spread, and we get filled because the bots
        # see our orders and trade against them.
        #
        # In Prosperity, the order matching works differently than a traditional exchange.
        # Let me reconsider...
        pass

    # The issue is clear: with a 13-14 spread, quoting at mid +/- anything < 6.5
    # means our bid < bot's ask and our ask > bot's bid. No fills.
    # With offset >= 7, our bid >= bot ask (we cross the spread), losing money per trade.

# Let me think about this differently.
# The ACTUAL market-making strategy in Prosperity:
# 1. We can place orders at ANY price
# 2. If our buy price >= bot's best ask, we buy at the bot's ask price (price improvement for us)
# 3. If our sell price <= bot's best bid, we sell at the bot's bid price
# 4. So we can "cross the spread" - buy at ask, sell at bid
# 5. The profit comes from MOVEMENT: buy when price is low, sell when high

# Strategy 2: Quote at the L1 prices (match the bots)
# This won't work either - we trade AFTER bots, so we'd just get residual fills

# Strategy 3: Cross the spread - aggressive orders
# Buy at ask_price_1, sell at bid_price_1
# We make money from price momentum, not from spread capture

# Strategy 4: Mean-reversion with the actual order book
# Use a fair value estimate, place orders relative to that

print("Strategy 2: Signal-based trading (L1 volume imbalance)")
print("  If imbalance > 0 (more bids), price likely to go up -> buy")
print("  If imbalance < 0 (more asks), price likely to go down -> sell")
print()

for threshold in [0, 1, 2, 3]:
    total_pnl = 0
    position = 0
    pos_limit = 50
    buys = 0
    sells = 0
    trades_value = 0

    for _, row in tom.iterrows():
        imb = row["bid_volume_1"] - row["ask_volume_1"]

        if imb > threshold and position < pos_limit:
            # Buy at ask
            qty = min(int(row["ask_volume_1"]), pos_limit - position)
            if qty > 0:
                position += qty
                total_pnl -= row["ask_price_1"] * qty
                buys += qty

        elif imb < -threshold and position > -pos_limit:
            # Sell at bid
            qty = min(int(row["bid_volume_1"]), position + pos_limit)
            if qty > 0:
                position -= qty
                total_pnl += row["bid_price_1"] * qty
                sells += qty

    # Mark to market
    total_pnl += position * tom.iloc[-1]["mid_price"]
    print(f"  threshold={threshold}: PnL={total_pnl:.0f}, buys={buys}, sells={sells}, final_pos={position}")

print()
print("Strategy 3: Mean-reversion (buy low, sell high relative to MA)")
print()

for ma_window in [10, 20, 50, 100]:
    tom[f"ma_{ma_window}"] = tom["mid_price"].rolling(ma_window).mean()

    for threshold_pct in [0.0, 0.05, 0.1, 0.15, 0.2]:
        total_pnl = 0
        position = 0
        pos_limit = 50
        buys = 0
        sells = 0

        for i, row in tom.iterrows():
            if pd.isna(row.get(f"ma_{ma_window}", np.nan)):
                continue

            ma = row[f"ma_{ma_window}"]
            dev = (row["mid_price"] - ma) / ma * 100  # deviation in %

            if dev < -threshold_pct and position < pos_limit:
                # Price below MA -> buy
                qty = min(int(row["ask_volume_1"]), pos_limit - position)
                if qty > 0:
                    position += qty
                    total_pnl -= row["ask_price_1"] * qty
                    buys += qty

            elif dev > threshold_pct and position > -pos_limit:
                # Price above MA -> sell
                qty = min(int(row["bid_volume_1"]), position + pos_limit)
                if qty > 0:
                    position -= qty
                    total_pnl += row["bid_price_1"] * qty
                    sells += qty

        total_pnl += position * tom.iloc[-1]["mid_price"]
        print(f"  MA-{ma_window}, thresh={threshold_pct:.2f}%: PnL={total_pnl:.0f}, "
              f"buys={buys}, sells={sells}, final_pos={position}")
    print()

print()
print("Strategy 4: Lag-1 mean reversion (fade the last move)")
print("  autocorr = -0.42, so if price went up, it's likely to go down")
print()

tom["mid_change"] = tom["mid_price"].diff()

for min_change in [0.0, 0.5, 1.0, 1.5, 2.0, 3.0]:
    total_pnl = 0
    position = 0
    pos_limit = 50
    buys = 0
    sells = 0

    for i in range(1, len(tom)):
        row = tom.iloc[i]
        prev_change = tom.iloc[i]["mid_change"]

        if pd.isna(prev_change):
            continue

        if prev_change > min_change and position > -pos_limit:
            # Price went up -> fade -> sell
            qty = min(int(row["bid_volume_1"]), position + pos_limit)
            if qty > 0:
                position -= qty
                total_pnl += row["bid_price_1"] * qty
                sells += qty

        elif prev_change < -min_change and position < pos_limit:
            # Price went down -> fade -> buy
            qty = min(int(row["ask_volume_1"]), pos_limit - position)
            if qty > 0:
                position += qty
                total_pnl -= row["ask_price_1"] * qty
                buys += qty

    total_pnl += position * tom.iloc[-1]["mid_price"]
    print(f"  min_change={min_change}: PnL={total_pnl:.0f}, buys={buys}, sells={sells}, final_pos={position}")

print()
print("Strategy 5: Combined (volume imbalance + mean reversion)")
print("  Use imbalance as short-term signal + MA deviation as medium-term")
print()

tom["ma_20"] = tom["mid_price"].rolling(20).mean()
tom["dev_20"] = tom["mid_price"] - tom["ma_20"]

for imb_thresh in [0, 1, 2]:
    for dev_thresh in [0, 1, 2, 3]:
        total_pnl = 0
        position = 0
        pos_limit = 50
        buys = 0
        sells = 0

        for i, row in tom.iterrows():
            imb = row["bid_volume_1"] - row["ask_volume_1"]
            dev = row.get("dev_20", np.nan)
            if pd.isna(dev):
                continue

            # Buy signal: imbalance bullish AND price below MA
            if imb > imb_thresh and dev < -dev_thresh and position < pos_limit:
                qty = min(int(row["ask_volume_1"]), pos_limit - position)
                if qty > 0:
                    position += qty
                    total_pnl -= row["ask_price_1"] * qty
                    buys += qty

            # Sell signal: imbalance bearish AND price above MA
            elif imb < -imb_thresh and dev > dev_thresh and position > -pos_limit:
                qty = min(int(row["bid_volume_1"]), position + pos_limit)
                if qty > 0:
                    position -= qty
                    total_pnl += row["bid_price_1"] * qty
                    sells += qty

        total_pnl += position * tom.iloc[-1]["mid_price"]
        if buys + sells > 0:
            print(f"  imb>{imb_thresh}, dev>{dev_thresh}: PnL={total_pnl:.0f}, "
                  f"buys={buys}, sells={sells}, final_pos={position}")

print()
print("=" * 70)
print("Strategy 6: PROPER Market-Making (quote inside the spread)")
print("=" * 70)
print()
print("  In Prosperity, we submit orders and bots trade against us.")
print("  If we place a buy at price P where bid_1 < P < ask_1,")
print("  a bot MIGHT sell to us if it wants to (depends on bot logic).")
print("  But the data doesn't tell us if bots would hit our quotes.")
print()
print("  Instead, let's model: we always quote at bid+1 and ask-1")
print("  (penny the spread). We get filled when the mid moves toward us.")
print("  Specifically, we assume we get filled when:")
print("    - Our buy at (bid_1 + k) gets filled when next tick's ask_1 <= our buy price")
print("    - Our sell at (ask_1 - k) gets filled when next tick's bid_1 >= our sell price")
print()

for k in range(1, 8):
    total_pnl = 0
    position = 0
    pos_limit = 50
    buys = 0
    sells = 0

    for i in range(len(tom) - 1):
        row = tom.iloc[i]
        next_row = tom.iloc[i + 1]

        our_bid = int(row["bid_price_1"]) + k
        our_ask = int(row["ask_price_1"]) - k

        if our_bid >= our_ask:
            continue  # Crossed quotes, skip

        # Check if we get filled next tick
        # Buy fill: next tick's ask drops to our level
        if next_row["ask_price_1"] <= our_bid and position < pos_limit:
            qty = min(5, pos_limit - position)  # conservative size
            position += qty
            total_pnl -= our_bid * qty
            buys += qty

        # Sell fill: next tick's bid rises to our level
        if next_row["bid_price_1"] >= our_ask and position > -pos_limit:
            qty = min(5, position + pos_limit)
            position -= qty
            total_pnl += our_ask * qty
            sells += qty

    total_pnl += position * tom.iloc[-1]["mid_price"]
    spread_quoted = f"bid+{k}/ask-{k}"
    print(f"  {spread_quoted}: PnL={total_pnl:.0f}, buys={buys}, sells={sells}, final_pos={position}")

print()
print("=" * 70)
print("Strategy 7: The REAL optimal -- what if we know the next mid price?")
print("=" * 70)
print("  Upper bound on profit: if we could perfectly predict direction")
print()

# Perfect foresight
total_pnl = 0
position = 0
pos_limit = 50
buys = 0
sells = 0
for i in range(len(tom) - 1):
    row = tom.iloc[i]
    next_mid = tom.iloc[i + 1]["mid_price"]
    curr_mid = row["mid_price"]

    if next_mid > curr_mid + row["ask_price_1"] - curr_mid:
        # Price going up enough to cover ask spread
        if position < pos_limit:
            qty = min(int(row["ask_volume_1"]), pos_limit - position)
            position += qty
            total_pnl -= row["ask_price_1"] * qty
            buys += qty
    elif next_mid < curr_mid - (curr_mid - row["bid_price_1"]):
        # Price going down enough to cover bid spread
        if position > -pos_limit:
            qty = min(int(row["bid_volume_1"]), position + pos_limit)
            position -= qty
            total_pnl += row["bid_price_1"] * qty
            sells += qty

total_pnl += position * tom.iloc[-1]["mid_price"]
print(f"  Perfect 1-step foresight: PnL={total_pnl:.0f}, buys={buys}, sells={sells}")

# Perfect foresight with 5-step horizon
total_pnl = 0
position = 0
buys = 0
sells = 0
for i in range(len(tom) - 5):
    row = tom.iloc[i]
    future_mid = tom.iloc[i + 5]["mid_price"]
    curr_ask = row["ask_price_1"]
    curr_bid = row["bid_price_1"]

    if future_mid > curr_ask + 1 and position < pos_limit:
        qty = min(int(row["ask_volume_1"]), pos_limit - position)
        position += qty
        total_pnl -= curr_ask * qty
        buys += qty
    elif future_mid < curr_bid - 1 and position > -pos_limit:
        qty = min(int(row["bid_volume_1"]), position + pos_limit)
        position -= qty
        total_pnl += curr_bid * qty
        sells += qty

total_pnl += position * tom.iloc[-1]["mid_price"]
print(f"  Perfect 5-step foresight: PnL={total_pnl:.0f}, buys={buys}, sells={sells}")

print()
print("=" * 70)
print("CRITICAL INSIGHT: TWO DISTINCT BOT POPULATIONS")
print("=" * 70)

# The bimodal spread distribution (5-9 and 13-14) suggests two bot types
# Let's characterize them

tom["spread"] = tom["ask_price_1"] - tom["bid_price_1"]
tight = tom[tom["spread"] < 10]
wide = tom[tom["spread"] >= 10]

print(f"\n  Tight-spread regime (spread < 10): {len(tight)} ticks ({len(tight)/len(tom)*100:.1f}%)")
print(f"    Spread distribution: {tight['spread'].value_counts().sort_index().to_dict()}")
print(f"    bid_vol_1: mean={tight['bid_volume_1'].mean():.1f}, {tight['bid_volume_1'].value_counts().sort_index().to_dict()}")
print(f"    ask_vol_1: mean={tight['ask_volume_1'].mean():.1f}")
print(f"    L2 present: bid={tight['bid_volume_3'].notna().mean()*100:.1f}%, ask={tight['ask_volume_3'].notna().mean()*100:.1f}%")

print(f"\n  Wide-spread regime (spread >= 10): {len(wide)} ticks ({len(wide)/len(tom)*100:.1f}%)")
print(f"    Spread distribution: {wide['spread'].value_counts().sort_index().to_dict()}")
print(f"    bid_vol_1: mean={wide['bid_volume_1'].mean():.1f}")
print(f"    ask_vol_1: mean={wide['ask_volume_1'].mean():.1f}")
print(f"    L2 present: bid={wide['bid_volume_3'].notna().mean()*100:.1f}%, ask={wide['ask_volume_3'].notna().mean()*100:.1f}%")

# What happens to mid price after tight spread?
print(f"\n  Price behavior around tight spread ticks:")
for horizon in [1, 3, 5, 10]:
    tight_idx = tight.index
    fwd_changes = []
    for idx in tight_idx:
        if idx + horizon < len(tom):
            fwd_changes.append(tom.iloc[idx + horizon]["mid_price"] - tom.iloc[idx]["mid_price"])
    if fwd_changes:
        fc = np.array(fwd_changes)
        print(f"    {horizon}-tick forward: mean={fc.mean():.3f}, std={fc.std():.3f}, "
              f"abs_mean={np.abs(fc).mean():.3f}")

# What predicts the tight spread?
print(f"\n  What precedes tight spreads?")
tight_idx = tight.index
prev_mids = []
prev_changes = []
for idx in tight_idx:
    if idx > 0:
        prev_mids.append(tom.iloc[idx - 1]["mid_price"])
        prev_changes.append(tom.iloc[idx]["mid_price"] - tom.iloc[idx - 1]["mid_price"])

if prev_changes:
    pc = np.array(prev_changes)
    print(f"    Change entering tight spread: mean={pc.mean():.3f}, std={pc.std():.3f}")
    print(f"    Abs change entering tight spread: {np.abs(pc).mean():.3f}")

# Vs random ticks
rand_idx = np.random.choice(wide.index[wide.index > 0], size=min(len(tight), len(wide)), replace=False)
rand_changes = [tom.iloc[idx]["mid_price"] - tom.iloc[idx - 1]["mid_price"] for idx in rand_idx]
rc = np.array(rand_changes)
print(f"    Change at random wide ticks: mean={rc.mean():.3f}, std={rc.std():.3f}")
print(f"    Abs change at random wide: {np.abs(rc).mean():.3f}")

# Volume analysis during tight spread
print(f"\n  Volume analysis:")
print(f"    Tight spread avg bid_vol_1: {tight['bid_volume_1'].mean():.2f}")
print(f"    Wide spread avg bid_vol_1: {wide['bid_volume_1'].mean():.2f}")

# Bid-ask spread decomposition
tom["bid_mid_gap"] = tom["mid_price"] - tom["bid_price_1"]
tom["ask_mid_gap"] = tom["ask_price_1"] - tom["mid_price"]
print(f"\n  Spread decomposition (is it symmetric?):")
print(f"    bid-to-mid gap: mean={tom['bid_mid_gap'].mean():.2f}, std={tom['bid_mid_gap'].std():.2f}")
print(f"    ask-to-mid gap: mean={tom['ask_mid_gap'].mean():.2f}, std={tom['ask_mid_gap'].std():.2f}")
tight_f = tom[tom["spread"] < 10]
wide_f = tom[tom["spread"] >= 10]
print(f"    Tight: bid_gap={tight_f['bid_mid_gap'].mean():.2f}, ask_gap={tight_f['ask_mid_gap'].mean():.2f}")
print(f"    Wide: bid_gap={wide_f['bid_mid_gap'].mean():.2f}, ask_gap={wide_f['ask_mid_gap'].mean():.2f}")

# L1-L2 price gap analysis
tom["bid_12_gap"] = tom["bid_price_1"] - tom["bid_price_2"]
tom["ask_12_gap"] = tom["ask_price_2"] - tom["ask_price_1"]
print(f"\n  L1-L2 gaps during tight vs wide:")

tight_12 = tom.loc[tom["spread"] < 10, "bid_12_gap"]
wide_12 = tom.loc[tom["spread"] >= 10, "bid_12_gap"]
print(f"    Tight bid L1-L2 gap: {tight_12.value_counts().sort_index().to_dict()}")
print(f"    Wide bid L1-L2 gap: {wide_12.value_counts().sort_index().to_dict()}")

print()
print("=" * 70)
print("TOTAL VOLUME IMBALANCE (L1+L2+L3) as SIGNAL")
print("=" * 70)
print()

# The total imbalance had VERY strong negative correlation (-0.58) with next move
# That seems counterintuitive... let's investigate

tom["total_bid_vol"] = tom["bid_volume_1"].fillna(0) + tom["bid_volume_2"].fillna(0) + tom["bid_volume_3"].fillna(0)
tom["total_ask_vol"] = tom["ask_volume_1"].fillna(0) + tom["ask_volume_2"].fillna(0) + tom["ask_volume_3"].fillna(0)
tom["total_imb"] = tom["total_bid_vol"] - tom["total_ask_vol"]
tom["next_mid_change"] = tom["mid_price"].diff().shift(-1)

# Break down what's happening
print("  Correlation breakdown:")
for col_pair in [
    ("bid_volume_1", "next_mid_change"),
    ("ask_volume_1", "next_mid_change"),
    ("bid_volume_2", "next_mid_change"),
    ("ask_volume_2", "next_mid_change"),
    ("total_bid_vol", "next_mid_change"),
    ("total_ask_vol", "next_mid_change"),
]:
    c = tom[col_pair[0]].corr(tom[col_pair[1]])
    print(f"    corr({col_pair[0]}, {col_pair[1]}) = {c:.4f}")

# The negative correlation means: MORE total bids -> price goes DOWN
# This is the "liquidity provision" effect: bots add bids AFTER price dropped (to catch the bounce)
# So high bid volume means price ALREADY dropped and will continue/mean-revert

# Let's check: is the total imbalance just reflecting the recent price level?
tom["ma_50"] = tom["mid_price"].rolling(50).mean()
tom["price_dev"] = tom["mid_price"] - tom["ma_50"]
print(f"\n  corr(total_imb, price_dev) = {tom['total_imb'].corr(tom['price_dev']):.4f}")
print(f"  corr(L1_imb, price_dev) = {(tom['bid_volume_1'] - tom['ask_volume_1']).corr(tom['price_dev']):.4f}")

# Partial correlation: does total_imb predict next move BEYOND what price_dev predicts?
valid = tom.dropna(subset=["total_imb", "next_mid_change", "price_dev"])
from numpy.linalg import lstsq

X = valid[["total_imb", "price_dev"]].values
y = valid["next_mid_change"].values
X_aug = np.column_stack([X, np.ones(len(X))])
coeffs, _, _, _ = lstsq(X_aug, y, rcond=None)
print(f"\n  Multiple regression: next_change = {coeffs[0]:.6f} * total_imb + {coeffs[1]:.6f} * price_dev + {coeffs[2]:.6f}")
y_pred = X_aug @ coeffs
r2 = 1 - np.sum((y - y_pred)**2) / np.sum((y - np.mean(y))**2)
print(f"  R-squared: {r2:.4f}")
