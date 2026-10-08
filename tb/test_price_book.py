"""Tests for rtl/price_book.sv (v2 book)."""
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge

from ref_model import PriceBook

N_INSTR, W = 4, 256
B, S = True, False


# ---------------------------------------------------------------- helpers
async def setup(dut):
    cocotb.start_soon(Clock(dut.clk, 4, unit="ns").start())
    for sig in (dut.cfg_valid, dut.cfg_instrument, dut.cfg_base_px,
                dut.msg_valid, dut.msg_is_bid, dut.msg_instrument,
                dut.msg_price, dut.msg_qty):
        sig.value = 0
    dut.rst.value = 1
    await ClockCycles(dut.clk, 2)
    dut.rst.value = 0
    await FallingEdge(dut.clk)


async def configure(dut, instr: int, base: int):
    dut.cfg_valid.value = 1
    dut.cfg_instrument.value = instr
    dut.cfg_base_px.value = base
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.cfg_valid.value = 0


async def send(dut, is_bid, instr, price, qty) -> dict:
    """Apply one message; return what the DUT reported one cycle later."""
    dut.msg_valid.value = 1
    dut.msg_is_bid.value = int(is_bid)
    dut.msg_instrument.value = instr
    dut.msg_price.value = price
    dut.msg_qty.value = qty
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.msg_valid.value = 0
    return {
        "tob": bool(dut.tob_valid.value),
        "instr": int(dut.tob_instrument.value),
        "top": (int(dut.best_bid_px.value), int(dut.best_bid_qty.value),
                int(dut.best_ask_px.value), int(dut.best_ask_qty.value)),
        "crossed": bool(dut.tob_crossed.value),
        "rej": int(dut.rej_reason.value) if dut.rej_valid.value == 1 else 0,
    }


# ------------------------------------------------------------------ tests
@cocotb.test()
async def instruments_are_independent(dut):
    await setup(dut)
    await configure(dut, 0, 10_000)
    await configure(dut, 1, 500)

    r = await send(dut, B, 0, 10_005, 10)
    assert r["tob"] and r["instr"] == 0 and r["top"] == (10_005, 10, 0, 0)

    r = await send(dut, S, 1, 520, 7)
    assert r["tob"] and r["instr"] == 1 and r["top"] == (0, 0, 520, 7)

    # instrument 0 unchanged by instrument 1's update
    r = await send(dut, B, 0, 10_001, 3)          # worse bid -> no change
    assert not r["tob"]
    r = await send(dut, S, 0, 10_009, 4)
    assert r["tob"] and r["instr"] == 0 and r["top"] == (10_005, 10, 10_009, 4)


@cocotb.test()
async def no_level_is_ever_lost(dut):
    """The v1 limitation: 50 levels in, remove them one by one from the top,
    every single level must surface as the new best."""
    await setup(dut)
    await configure(dut, 2, 1_000)
    for k in range(50):
        await send(dut, B, 2, 1_000 + k, k + 1)     # prices 1000..1049

    for k in range(49, -1, -1):
        r = await send(dut, B, 2, 1_000 + k, 0)     # remove current best
        exp = (1_000 + k - 1, k, 0, 0) if k > 0 else (0, 0, 0, 0)
        assert r["tob"] and r["top"] == exp, f"removing {1_000 + k}: got {r['top']}"


@cocotb.test()
async def crossed_book_flag(dut):
    await setup(dut)
    await configure(dut, 0, 100)
    r = await send(dut, B, 0, 150, 5)
    r = await send(dut, S, 0, 152, 5)
    assert r["tob"] and not r["crossed"]
    r = await send(dut, B, 0, 152, 1)                # bid == ask -> crossed (locked)
    assert r["tob"] and r["crossed"]
    r = await send(dut, S, 0, 152, 0)                # remove ask at 152
    r = await send(dut, S, 0, 155, 2)                # ask back above bid
    assert r["tob"] and not r["crossed"], r


@cocotb.test()
async def rejects(dut):
    await setup(dut)
    await configure(dut, 0, 1_000)
    r = await send(dut, B, 7, 1_010, 5)               # instrument 7 >= N_INSTR
    assert r["rej"] == 1 and not r["tob"]
    r = await send(dut, B, 0, 999, 5)                 # below window
    assert r["rej"] == 2 and not r["tob"]
    r = await send(dut, B, 0, 1_000 + W, 5)           # just above window
    assert r["rej"] == 2 and not r["tob"]
    r = await send(dut, B, 0, 1_000 + W - 1, 5)       # last tick: accepted
    assert r["rej"] == 0 and r["tob"]


@cocotb.test()
async def random_vs_reference(dut):
    """20,000 random messages over 4 instruments (+ invalid ones),
    compared with the reference model after EVERY message."""
    await setup(dut)
    model = PriceBook(N_INSTR, W)
    rng = random.Random(42)
    bases = [10_000, 2_500, 77, 400_000]
    for i, b in enumerate(bases):
        await configure(dut, i, b)
        model.configure(i, b)

    n_tob = n_rej = n_cross = 0
    for n in range(20_000):
        instr = rng.randrange(N_INSTR + 1)            # sometimes invalid (= 4)
        base = bases[instr] if instr < N_INSTR else 0
        is_bid = rng.random() < 0.5
        mid = base + 100
        live = (model.bids[instr] if is_bid else model.asks[instr]) if instr < N_INSTR else {}
        r = rng.random()
        if r < 0.03:                                  # just outside the window
            price = base - rng.randint(1, 5) if rng.random() < 0.5 else base + W + rng.randint(0, 4)
            qty = rng.randint(1, 1000)
        elif r < 0.40 and live:                       # cancel an existing level
            price, qty = rng.choice(sorted(live)), 0
        elif r < 0.43:                                # aggressive: crosses the book
            price, qty = mid + (rng.randint(0, 2) if is_bid else -rng.randint(0, 2)), rng.randint(1, 1000)
        else:                                         # normal: bids below mid, asks above
            price = mid - rng.randint(1, 8) if is_bid else mid + rng.randint(1, 8)
            qty = rng.randint(1, 1000)

        exp = model.apply(is_bid, instr, price, qty)
        got = await send(dut, is_bid, instr, price, qty)

        ctx = f"msg {n} (bid={is_bid} instr={instr} px={price} qty={qty})"
        assert got["rej"] == exp["rej"], f"{ctx}: rej {got['rej']} != {exp['rej']}"
        assert got["tob"] == exp["changed"], f"{ctx}: tob {got['tob']} != {exp['changed']}"
        if exp["changed"]:
            assert got["instr"] == instr, ctx
            assert got["top"] == exp["top"], f"{ctx}: {got['top']} != {exp['top']}"
            assert got["crossed"] == exp["crossed"], ctx
            n_tob += 1
            n_cross += exp["crossed"]
        n_rej += exp["rej"] != 0

    dut._log.info(f"20,000 messages match the model: {n_tob} top-of-book updates, "
                  f"{n_cross} crossed, {n_rej} rejected")
