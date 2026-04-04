"""
IMC Prosperity 4 — Championship Trading Algorithm
===================================================
Data-driven multi-strategy algo for Round 0: EMERALDS & TOMATOES
Conforms to: https://imc-prosperity.notion.site/writing-an-algorithm-in-python

Strategy Summary (derived from CSV analysis of round_0 day_-1 & day_-2):
  EMERALDS: Stationary FV=10000, spread≈16, bid@9992/ask@10008 98%+ of time
            → Aggressive market making: take everything mispriced, post tight quotes
  TOMATOES: Trending with strong lag-1 mean reversion (AC≈-0.42), spread≈13
            L2 has bigger volume 99% of time (big-volume FV estimator)
            → Adaptive EMA fair-value + aggressive taking + inventory-skewed MM

Allowed imports: pandas, numpy, statistics, math, typing, jsonpickle
Return signature: (Dict[str, List[Order]], int, str)
Position limits: 80 per product
Timeout: <900ms per run() call
"""

from datamodel import OrderDepth, TradingState, Order
from typing import Dict, List
import jsonpickle
import math


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS — calibrated from prices_round_0_day_-1.csv & day_-2.csv
# ─────────────────────────────────────────────────────────────────────────────
POSITION_LIMITS = {
    "EMERALDS": 80,
    "TOMATOES": 80,
}

# EMERALDS: stationary asset, FV = 10000 (mid=10000 in 96.7% of ticks)
EMERALDS_FV = 10000
# We'll buy at <=9999 and sell at >=10001 for guaranteed profit
# Then post resting bids/asks tighter than the bot's 9992/10008
EMERALDS_TAKE_WIDTH = 1       # take anything that crosses FV (buy < 10000, sell > 10000)
EMERALDS_MM_SPREAD_HALF = 6   # post at FV±6 = 9994/10006 (optimized: wider = more profit per fill)

# TOMATOES: EMA alpha=0.30 gives MAE≈0.58, good for trending product
# Lag-1 autocorrelation ≈ -0.42 → tick-level mean reversion
# Grid-search optimized: take=3, mm=5, alpha=0.3 → ~27K combined PnL
TOMATOES_EMA_ALPHA = 0.30
TOMATOES_TAKE_WIDTH = 3       # take anything 3+ ticks from FV
TOMATOES_MM_SPREAD_HALF = 5   # post at FV±5 (optimized for profit per fill)


class Trader:
    """
    Main Trader class — the only required class.
    run() is called each iteration with the current TradingState.
    Must return (result, conversions, traderData).
    """

    def __init__(self):
        # These won't persist between uploads, we use traderData for state
        pass

    def run(self, state: TradingState):
        """
        Core method called every iteration.
        Ref: Notion — "The run function that takes a tradingstate as input"
        Returns: (Dict[str, List[Order]], int, traderData_str)
        """
        result: Dict[str, List[Order]] = {}
        conversions = 0

        # ── Restore persistent state from traderData (jsonpickle) ──
        trader_state = {}
        if state.traderData and state.traderData != "":
            try:
                trader_state = jsonpickle.decode(state.traderData)
            except Exception:
                trader_state = {}

        # ── Process each product ──
        for product in state.order_depths:
            if product == "EMERALDS":
                orders = self.trade_emeralds(state, product, trader_state)
            elif product == "TOMATOES":
                orders = self.trade_tomatoes(state, product, trader_state)
            else:
                # Future-proof: generic market-making fallback for unknown products
                orders = self.trade_generic(state, product, trader_state)

            result[product] = orders

        # ── Serialize state for next iteration ──
        trader_data_str = jsonpickle.encode(trader_state)

        return result, conversions, trader_data_str

    # ─────────────────────────────────────────────────────────────────────────
    # EMERALDS: Stationary Market Making (FV = 10000)
    # ─────────────────────────────────────────────────────────────────────────
    # Analysis: mid=10000 in 96.7% of ticks. Bot bids at 9992, asks at 10008.
    #   The bot spread (16 wide) is always wider than FV deviation.
    #   ALL profit comes from resting orders filled by market trades.
    # Strategy: (1) Take any ask < FV and any bid > FV (rare but free money)
    #           (2) Post resting at FV±6 = 9994/10006 (inside bot spread)
    #           (3) Inventory-skew quotes toward neutral
    # Optimized via grid search: mm_half=6 → ~27K combined PnL
    # ─────────────────────────────────────────────────────────────────────────
    def trade_emeralds(self, state: TradingState, product: str,
                       trader_state: dict) -> List[Order]:
        orders: List[Order] = []
        order_depth: OrderDepth = state.order_depths[product]
        position = state.position.get(product, 0)
        limit = POSITION_LIMITS.get(product, 50)
        fair_value = EMERALDS_FV

        buy_capacity = limit - position     # max we can buy
        sell_capacity = limit + position     # max we can sell (qty will be negative)

        # ── PHASE 1: Aggressive taking — sweep ALL mispriced levels ──
        # Buy everything offered below fair value (strictly < 10000)
        # sell_orders: Dict[price, qty] where qty is NEGATIVE
        if order_depth.sell_orders:
            for ask_price in sorted(order_depth.sell_orders.keys()):
                if ask_price < fair_value and buy_capacity > 0:
                    ask_vol = abs(order_depth.sell_orders[ask_price])
                    take_qty = min(ask_vol, buy_capacity)
                    if take_qty > 0:
                        orders.append(Order(product, ask_price, take_qty))
                        buy_capacity -= take_qty
                        position += take_qty

        # Sell into everything bid above fair value (strictly > 10000)
        if order_depth.buy_orders:
            for bid_price in sorted(order_depth.buy_orders.keys(), reverse=True):
                if bid_price > fair_value and sell_capacity > 0:
                    bid_vol = order_depth.buy_orders[bid_price]
                    take_qty = min(bid_vol, sell_capacity)
                    if take_qty > 0:
                        orders.append(Order(product, bid_price, -take_qty))
                        sell_capacity -= take_qty
                        position -= take_qty

        # ── PHASE 2: Market making — post resting orders ──
        # Inventory-adjusted: shift BOTH quotes to encourage mean reversion
        # If long (pos > 0), lower both bid & ask to sell more
        # If short (pos < 0), raise both to buy more
        # Optimized: factor=0.4, clamp=±2 ticks
        inv_adj = -int(position * 0.4)
        inv_adj = max(min(inv_adj, 2), -2)

        mm_bid = fair_value - EMERALDS_MM_SPREAD_HALF + inv_adj
        mm_ask = fair_value + EMERALDS_MM_SPREAD_HALF + inv_adj

        # Safety: never cross fair value
        mm_bid = min(mm_bid, fair_value - 1)
        mm_ask = max(mm_ask, fair_value + 1)

        # Recalculate capacities after taking phase
        buy_capacity = limit - position
        sell_capacity = limit + position

        # Post full remaining capacity at single level (simpler, more fill)
        if buy_capacity > 0:
            orders.append(Order(product, mm_bid, buy_capacity))

        if sell_capacity > 0:
            orders.append(Order(product, mm_ask, -sell_capacity))

        return orders

    # ─────────────────────────────────────────────────────────────────────────
    # TOMATOES: Adaptive EMA Market Making
    # ─────────────────────────────────────────────────────────────────────────
    # Analysis: Trending product (day-1: 5006→4957), lag-1 AC≈-0.42
    #   L2 volume > L1 volume 99% of time → big-vol weighted FV estimator
    #   EMA(alpha=0.30) gives MAE≈0.58 for next-tick prediction
    # Strategy: (1) Estimate FV from order book (weighted mid of big-vol levels)
    #           (2) Track with EMA for smoothness
    #           (3) Take mispriced orders aggressively
    #           (4) Post inventory-adjusted market-making quotes
    # ─────────────────────────────────────────────────────────────────────────
    def trade_tomatoes(self, state: TradingState, product: str,
                       trader_state: dict) -> List[Order]:
        orders: List[Order] = []
        order_depth: OrderDepth = state.order_depths[product]
        position = state.position.get(product, 0)
        limit = POSITION_LIMITS.get(product, 50)

        # ── Estimate fair value from order book ──
        fair_value = self._estimate_tomatoes_fv(order_depth, product, trader_state)

        buy_capacity = limit - position
        sell_capacity = limit + position

        # ── PHASE 1: Aggressive taking — sweep mispriced levels ──
        if order_depth.sell_orders:
            for ask_price in sorted(order_depth.sell_orders.keys()):
                if ask_price <= fair_value - TOMATOES_TAKE_WIDTH and buy_capacity > 0:
                    ask_vol = abs(order_depth.sell_orders[ask_price])
                    take_qty = min(ask_vol, buy_capacity)
                    if take_qty > 0:
                        orders.append(Order(product, ask_price, take_qty))
                        buy_capacity -= take_qty
                        position += take_qty

        if order_depth.buy_orders:
            for bid_price in sorted(order_depth.buy_orders.keys(), reverse=True):
                if bid_price >= fair_value + TOMATOES_TAKE_WIDTH and sell_capacity > 0:
                    bid_vol = order_depth.buy_orders[bid_price]
                    take_qty = min(bid_vol, sell_capacity)
                    if take_qty > 0:
                        orders.append(Order(product, bid_price, -take_qty))
                        sell_capacity -= take_qty
                        position -= take_qty

        # ── PHASE 2: Market Making with inventory management ──
        # Stronger inventory skew for TOMATOES because it trends
        inv_ratio = position / limit if limit > 0 else 0

        # Dynamic spread: wider when inventory is large
        dynamic_half_spread = TOMATOES_MM_SPREAD_HALF + int(abs(inv_ratio) * 3)

        # Skew: shift fair value toward reducing inventory
        fv_skew = -inv_ratio * 3  # if long, lower effective FV to sell more
        adj_fv = fair_value + fv_skew

        mm_bid = int(math.floor(adj_fv - dynamic_half_spread))
        mm_ask = int(math.ceil(adj_fv + dynamic_half_spread))

        # Don't cross the spread
        if mm_bid >= mm_ask:
            mm_bid = int(math.floor(adj_fv)) - 1
            mm_ask = int(math.ceil(adj_fv)) + 1

        # Recalculate capacities after taking
        buy_capacity = limit - position
        sell_capacity = limit + position

        # Post full remaining capacity (simpler = better fill rate)
        if buy_capacity > 0:
            orders.append(Order(product, mm_bid, buy_capacity))

        if sell_capacity > 0:
            orders.append(Order(product, mm_ask, -sell_capacity))

        return orders

    def _estimate_tomatoes_fv(self, order_depth: OrderDepth, product: str,
                              trader_state: dict) -> float:
        """
        Estimate TOMATOES fair value using:
        1. Big-volume weighted mid from order book
        2. EMA smoothing for trend tracking

        From CSV analysis:
        - L2 volume > L1 volume 99% of time
        - Average of big-vol bid/ask predicts next mid better than raw mid
        - EMA(alpha=0.3) MAE ≈ 0.58
        """
        # Extract order book levels
        buy_prices = sorted(order_depth.buy_orders.keys(), reverse=True)
        sell_prices = sorted(order_depth.sell_orders.keys())

        if not buy_prices or not sell_prices:
            # Fallback: use whatever side is available or last EMA
            ema_key = f"{product}_ema"
            return trader_state.get(ema_key, 5000)

        best_bid = buy_prices[0]
        best_ask = sell_prices[0]
        simple_mid = (best_bid + best_ask) / 2

        # Find big-volume levels (L2 typically has bigger volume)
        big_bid = best_bid
        big_bid_vol = order_depth.buy_orders.get(best_bid, 0)
        for p in buy_prices[1:]:
            vol = order_depth.buy_orders.get(p, 0)
            if vol > big_bid_vol:
                big_bid = p
                big_bid_vol = vol

        big_ask = best_ask
        big_ask_vol = abs(order_depth.sell_orders.get(best_ask, 0))
        for p in sell_prices[1:]:
            vol = abs(order_depth.sell_orders.get(p, 0))
            if vol > big_ask_vol:
                big_ask = p
                big_ask_vol = vol

        # Weighted mid from big-volume levels (better FV estimator)
        book_fv = (big_bid + big_ask) / 2.0

        # EMA smoothing
        ema_key = f"{product}_ema"
        if ema_key in trader_state:
            prev_ema = trader_state[ema_key]
            ema = TOMATOES_EMA_ALPHA * book_fv + (1 - TOMATOES_EMA_ALPHA) * prev_ema
        else:
            ema = book_fv

        trader_state[ema_key] = ema

        # Blend: use the order-book FV for immediate signal, EMA for trend
        # Weight more toward book_fv since lag-1 AC is strongly negative
        # (price reverts to book FV quickly)
        fair_value = 0.7 * book_fv + 0.3 * ema

        return fair_value

    # ─────────────────────────────────────────────────────────────────────────
    # GENERIC: Fallback for future products
    # ─────────────────────────────────────────────────────────────────────────
    def trade_generic(self, state: TradingState, product: str,
                      trader_state: dict) -> List[Order]:
        """
        Generic adaptive market-making for any unknown product.
        Uses EMA of mid-price as fair value and posts around it.
        """
        orders: List[Order] = []
        order_depth: OrderDepth = state.order_depths[product]
        position = state.position.get(product, 0)
        limit = POSITION_LIMITS.get(product, 50)

        buy_prices = sorted(order_depth.buy_orders.keys(), reverse=True)
        sell_prices = sorted(order_depth.sell_orders.keys())

        if not buy_prices or not sell_prices:
            return orders

        mid = (buy_prices[0] + sell_prices[0]) / 2

        # EMA fair value
        ema_key = f"{product}_ema"
        alpha = 0.2
        if ema_key in trader_state:
            ema = alpha * mid + (1 - alpha) * trader_state[ema_key]
        else:
            ema = mid
        trader_state[ema_key] = ema

        fair_value = ema
        buy_capacity = limit - position
        sell_capacity = limit + position

        # Take mispriced orders
        for ask_price in sorted(order_depth.sell_orders.keys()):
            if ask_price < fair_value - 1 and buy_capacity > 0:
                vol = abs(order_depth.sell_orders[ask_price])
                qty = min(vol, buy_capacity)
                orders.append(Order(product, ask_price, qty))
                buy_capacity -= qty

        for bid_price in sorted(order_depth.buy_orders.keys(), reverse=True):
            if bid_price > fair_value + 1 and sell_capacity > 0:
                vol = order_depth.buy_orders[bid_price]
                qty = min(vol, sell_capacity)
                orders.append(Order(product, bid_price, -qty))
                sell_capacity -= qty

        # Post resting orders
        spread_half = 3
        mm_bid = int(math.floor(fair_value - spread_half))
        mm_ask = int(math.ceil(fair_value + spread_half))

        if buy_capacity > 0:
            orders.append(Order(product, mm_bid, buy_capacity))
        sell_capacity = limit + position
        if sell_capacity > 0:
            orders.append(Order(product, mm_ask, -sell_capacity))

        return orders