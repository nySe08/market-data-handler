"""Milestone 4: tests for rtl/order_book.sv (and book_side.sv)"""
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge

from ref_model import OrderBook


# ---------------------------------------------------------------- helpers
async def setup(dut):
    cocotb.start_soon(Clock(dut.clk, 4, unit="ns").start())   # 250 MHz
    dut.rst.value = 1
    dut.msg_valid.value = 0
    dut.msg_is_bid.value = 0
    dut.msg_price.value = 0
    dut.msg_qty.value = 0
    await ClockCycles(dut.clk, 2)
    dut.rst.value = 0
    await FallingEdge(dut.clk)


def read_top(dut) -> tuple[int, int, int, int]:
    return (int(dut.best_bid_px.value), int(dut.best_bid_qty.value),
            int(dut.best_ask_px.value), int(dut.best_ask_qty.value))


async def send(dut, is_bid: bool, price: int, qty: int) -> tuple[bool, tuple]:
    """Apply one message (we drive on the falling edge, DUT samples on the
    rising edge). Returns (tob_valid, top of book) one cycle later."""
    dut.msg_valid.value = 1
    dut.msg_is_bid.value = int(is_bid)
    dut.msg_price.value = price
    dut.msg_qty.value = qty
    await RisingEdge(dut.clk)        # DUT updates the book here
    await FallingEdge(dut.clk)       # outputs are stable now
    dut.msg_valid.value = 0
    return bool(dut.tob_valid.value), read_top(dut)


# ------------------------------------------------------------------ tests
@cocotb.test()
async def directed_basics(dut):
    """Insert, update, remove on both sides, step by step."""
    await setup(dut)
    B, S = True, False

    assert read_top(dut) == (0, 0, 0, 0), "book should start empty"

    # bids: best = highest
    assert await send(dut, B, 100, 5) == (True,  (100, 5, 0, 0))
    assert await send(dut, B, 102, 7) == (True,  (102, 7, 0, 0))   # new best
    assert await send(dut, B, 101, 3) == (False, (102, 7, 0, 0))   # not best -> no pulse
    assert await send(dut, B, 102, 9) == (True,  (102, 9, 0, 0))   # qty update of best
    assert await send(dut, B, 102, 0) == (True,  (101, 3, 0, 0))   # remove best
    assert await send(dut, B, 555, 0) == (False, (101, 3, 0, 0))   # remove unknown: ignored

    # asks: best = lowest
    assert await send(dut, S, 110, 4) == (True,  (101, 3, 110, 4))
    assert await send(dut, S, 108, 2) == (True,  (101, 3, 108, 2))
    assert await send(dut, S, 109, 1) == (False, (101, 3, 108, 2))


@cocotb.test()
async def full_book_eviction(dut):
    """9 bid levels into an 8-level book: the worst one must fall off."""
    await setup(dut)
    for p in range(1, 10):                 # 1..9, each new one is the best
        await send(dut, True, p, 10 * p)
    assert read_top(dut)[:2] == (9, 90)

    # remove from the top: 9, 8, ..., 2 -> then empty (level 1 was evicted)
    for p in range(9, 1, -1):
        _, top = await send(dut, True, p, 0)
        expected = (p - 1, 10 * (p - 1)) if p > 2 else (0, 0)
        assert top[:2] == expected, f"after removing {p}: got {top[:2]}"

    # a price worse than a FULL book is ignored
    for p in range(11, 19):                # fill with 11..18
        await send(dut, True, p, 1)
    tob, top = await send(dut, True, 5, 1)  # worse than all 8 -> ignored
    assert not tob and top[:2] == (18, 1)


@cocotb.test()
async def random_vs_reference(dut):
    """20,000 random messages; after EVERY one, compare with the Python model,
    including whether tob_valid should have pulsed."""
    await setup(dut)
    model = OrderBook(n=8)
    rng = random.Random(2026)

    for i in range(20_000):
        is_bid = rng.random() < 0.5
        # narrow price range -> lots of hits on existing levels
        price = rng.randint(9_990, 10_010)
        qty = 0 if rng.random() < 0.3 else rng.randint(1, 1000)

        exp_changed = model.apply(is_bid, price, qty)
        tob, top = await send(dut, is_bid, price, qty)

        assert top == model.top(), f"msg {i}: top {top} != model {model.top()}"
        assert tob == exp_changed, f"msg {i}: tob_valid={tob}, expected {exp_changed}"

    dut._log.info("20,000 random messages: RTL matches the reference model")
