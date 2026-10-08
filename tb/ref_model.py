"""
Golden reference model of the order book, in plain Python.

The RTL must behave EXACTLY like this. Tests apply the same messages to both
and compare. Keep it simple and obviously correct: clarity beats speed here.
"""


class BookSide:
    def __init__(self, is_bid: bool, n: int = 8):
        self.is_bid = is_bid
        self.n = n
        self.levels: dict[int, int] = {}   # price -> qty

    def _sorted_prices(self):
        return sorted(self.levels, reverse=self.is_bid)   # best first

    def best(self) -> tuple[int, int]:
        """(price, qty) of the best level, (0, 0) if empty."""
        if not self.levels:
            return (0, 0)
        p = self._sorted_prices()[0]
        return (p, self.levels[p])

    def apply(self, price: int, qty: int) -> None:
        if price in self.levels:
            if qty == 0:
                del self.levels[price]           # remove
            else:
                self.levels[price] = qty         # update
            return
        if qty == 0:
            return                               # remove unknown price: ignore
        if len(self.levels) < self.n:
            self.levels[price] = qty             # insert, room left
            return
        worst = self._sorted_prices()[-1]
        better = price > worst if self.is_bid else price < worst
        if better:                               # insert, evict the worst
            del self.levels[worst]
            self.levels[price] = qty
        # else: worse than all N levels -> ignore


class OrderBook:
    def __init__(self, n: int = 8):
        self.bid = BookSide(True, n)
        self.ask = BookSide(False, n)

    def top(self) -> tuple[int, int, int, int]:
        return (*self.bid.best(), *self.ask.best())

    def apply(self, is_bid: bool, price: int, qty: int) -> bool:
        """Apply one message. Returns True if the top of book changed."""
        before = self.top()
        (self.bid if is_bid else self.ask).apply(price, qty)
        return self.top() != before


class PriceBook:
    """Reference model for rtl/price_book.sv (v2): unlimited levels inside a
    price window, multiple instruments, crossed-book flag, rejects."""

    REJ_NONE, REJ_INSTR, REJ_RANGE = 0, 1, 2

    def __init__(self, n_instr: int = 4, w: int = 256):
        self.n_instr, self.w = n_instr, w
        self.base = [0] * n_instr
        self.bids = [dict() for _ in range(n_instr)]   # price -> qty
        self.asks = [dict() for _ in range(n_instr)]
        self.last_top = [(0, 0, 0, 0)] * n_instr

    def configure(self, instr: int, base: int) -> None:
        if instr < self.n_instr:
            self.base[instr] = base
            self.bids[instr].clear()
            self.asks[instr].clear()
            self.last_top[instr] = (0, 0, 0, 0)

    def top(self, instr: int) -> tuple[int, int, int, int]:
        b, a = self.bids[instr], self.asks[instr]
        bp = max(b) if b else 0
        ap = min(a) if a else 0
        return (bp, b.get(bp, 0), ap, a.get(ap, 0))

    def crossed(self, instr: int) -> bool:
        b, a = self.bids[instr], self.asks[instr]
        return bool(b) and bool(a) and max(b) >= min(a)

    def apply(self, is_bid: bool, instr: int, price: int, qty: int) -> dict:
        """Returns {"rej": reason, "changed": bool, "top": (...), "crossed": bool}."""
        if instr >= self.n_instr:
            return {"rej": self.REJ_INSTR, "changed": False}
        if not (self.base[instr] <= price < self.base[instr] + self.w):
            return {"rej": self.REJ_RANGE, "changed": False}
        side = self.bids[instr] if is_bid else self.asks[instr]
        if qty == 0:
            side.pop(price, None)
        else:
            side[price] = qty
        new_top = self.top(instr)
        changed = new_top != self.last_top[instr]
        self.last_top[instr] = new_top
        return {"rej": self.REJ_NONE, "changed": changed,
                "top": new_top, "crossed": self.crossed(instr)}
