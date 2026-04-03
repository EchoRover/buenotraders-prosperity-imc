"""
Minimal market-making Trader for IMC Prosperity 4 backtester verification.

Strategy:
- For EMERALDS (stable at ~10000): Quote tight around mid price.
- For TOMATOES (trending ~5000): Quote around mid price with a wider spread.

Both use simple midpoint-based market making with position limits to avoid
accumulating too much inventory.
"""

from prosperity4bt.datamodel import Order, OrderDepth, TradingState


POSITION_LIMITS = {
    "EMERALDS": 80,
    "TOMATOES": 80,
}


class Trader:
    def run(self, state: TradingState):
        result = {}

        for product in state.order_depths:
            order_depth: OrderDepth = state.order_depths[product]
            orders = []

            # Calculate mid price from best bid/ask
            best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else None
            best_ask = min(order_depth.sell_orders.keys()) if order_depth.sell_orders else None

            if best_bid is None or best_ask is None:
                result[product] = orders
                continue

            mid_price = (best_bid + best_ask) / 2
            position = state.position.get(product, 0)
            limit = POSITION_LIMITS.get(product, 50)

            # Set spread based on product
            if product == "EMERALDS":
                spread = 2  # Tight spread for stable product
            else:
                spread = 3  # Wider spread for trending product

            buy_price = int(mid_price - spread)
            sell_price = int(mid_price + spread)

            # Adjust quantity based on current position to stay within limits
            max_buy_qty = limit - position
            max_sell_qty = limit + position

            buy_qty = min(10, max_buy_qty)
            sell_qty = min(10, max_sell_qty)

            if buy_qty > 0:
                orders.append(Order(product, buy_price, buy_qty))
            if sell_qty > 0:
                orders.append(Order(product, sell_price, -sell_qty))

            result[product] = orders

        conversions = 0
        trader_data = ""

        return result, conversions, trader_data
