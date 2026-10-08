"""End-to-end test: raw Ethernet frames in -> top of book out (v2 book).
Also MEASURES the latency of the whole pipeline."""
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge, ReadOnly
from cocotb.utils import get_sim_time

from packet_gen import build_frame, build_message, SIDE_BID, SIDE_ASK
from ref_model import PriceBook

CLK_NS = 4            # 250 MHz
N_INSTR, W = 4, 256
BASES = [10_000, 2_500, 77, 400_000]


async def setup(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_NS, unit="ns").start())
    for sig in (dut.cfg_valid, dut.cfg_instrument, dut.cfg_base_px,
                dut.s_tvalid, dut.s_tdata, dut.s_tlast):
        sig.value = 0
    dut.rst.value = 1
    await ClockCycles(dut.clk, 2)
    dut.rst.value = 0
    # start of day: configure price windows
    await FallingEdge(dut.clk)
    for i, b in enumerate(BASES):
        dut.cfg_valid.value = 1
        dut.cfg_instrument.value = i
        dut.cfg_base_px.value = b
        await FallingEdge(dut.clk)
    dut.cfg_valid.value = 0


def read_tob(dut):
    return (int(dut.tob_instrument.value),
            int(dut.best_bid_px.value), int(dut.best_bid_qty.value),
            int(dut.best_ask_px.value), int(dut.best_ask_qty.value),
            bool(dut.tob_crossed.value))


async def send_frame(dut, frame: bytes, mark_byte: int | None = None):
    """Drive a frame. If mark_byte is given, return the sim time (ns) at which
    that byte was put on the input (= start of the cycle it is presented in)."""
    t_mark = None
    for i, b in enumerate(frame):
        dut.s_tvalid.value = 1
        dut.s_tdata.value = b
        dut.s_tlast.value = int(i == len(frame) - 1)
        if i == mark_byte:
            t_mark = get_sim_time(unit="ns")
        await RisingEdge(dut.clk)
    dut.s_tvalid.value = 0
    dut.s_tlast.value = 0
    return t_mark


async def monitor(dut, tobs: list, rejs: list):
    while True:
        await RisingEdge(dut.clk)
        await ReadOnly()
        if dut.tob_valid.value == 1:
            tobs.append((get_sim_time(unit="ns"), read_tob(dut)))
        if dut.rej_valid.value == 1:
            rejs.append(int(dut.rej_reason.value))


@cocotb.test()
async def measure_latency(dut):
    """Cycles from the last message byte appearing on the input to tob_valid
    appearing on the output. 3 register stages -> expect 3 cycles."""
    await setup(dut)
    tobs, rejs = [], []
    cocotb.start_soon(monitor(dut, tobs, rejs))

    msg = build_message(SIDE_BID, price=10_050, qty=300, instrument=0)
    frame = build_frame([msg])
    t_in = await send_frame(dut, frame, mark_byte=42 + len(msg) - 1)
    await ClockCycles(dut.clk, 5)

    assert len(tobs) == 1, f"expected 1 tob event, got {len(tobs)}"
    t_out, tob = tobs[0]
    assert tob == (0, 10_050, 300, 0, 0, False), tob
    cycles = round((t_out - t_in) / CLK_NS)
    dut._log.info(f"LATENCY: {cycles} cycles = {cycles * CLK_NS} ns @ {1000 // CLK_NS} MHz")
    assert cycles == 3, f"expected 3 cycles, measured {cycles}"


@cocotb.test()
async def random_end_to_end(dut):
    """1,000 random frames over 4 instruments (some invalid frames, unknown
    instruments and out-of-window prices). Every top-of-book event and every
    reject must match the reference model, in order."""
    await setup(dut)
    tobs, rejs = [], []
    cocotb.start_soon(monitor(dut, tobs, rejs))

    rng = random.Random(99)
    model = PriceBook(N_INSTR, W)
    for i, b in enumerate(BASES):
        model.configure(i, b)
    exp_tobs, exp_rejs, seq = [], [], 0

    for _ in range(1000):
        msgs, parsed = [], []
        for _ in range(rng.randint(1, 4)):
            instr = rng.randrange(N_INSTR + 1)              # 4 = unknown
            base = BASES[instr] if instr < N_INSTR else 0
            is_bid = rng.random() < 0.5
            live = (model.bids[instr] if is_bid else model.asks[instr]) if instr < N_INSTR else {}
            r = rng.random()
            if r < 0.03:
                price, qty = base + W + rng.randint(0, 4), rng.randint(1, 1000)
            elif r < 0.40 and live:
                price, qty = rng.choice(sorted(live)), 0
            else:
                price = base + 100 + (-rng.randint(0, 8) if is_bid else rng.randint(0, 8))
                qty = rng.randint(1, 1000)
            msgs.append(build_message(SIDE_BID if is_bid else SIDE_ASK, price, qty,
                                      instrument=instr, seq=seq))
            parsed.append((is_bid, instr, price, qty))
            seq += 1

        if rng.random() < 0.15:                             # whole frame invalid
            frame = build_frame(msgs, dst_port=1234)
        else:
            frame = build_frame(msgs)
            for is_bid, instr, price, qty in parsed:
                e = model.apply(is_bid, instr, price, qty)
                if e["rej"]:
                    exp_rejs.append(e["rej"])
                elif e["changed"]:
                    exp_tobs.append((instr, *e["top"], e["crossed"]))

        await send_frame(dut, frame)

    await ClockCycles(dut.clk, 5)
    got = [t for _, t in tobs]
    assert got == exp_tobs, "top-of-book events differ from the model"
    assert rejs == exp_rejs, "rejects differ from the model"
    dut._log.info(f"{len(exp_tobs)} top-of-book updates and {len(exp_rejs)} rejects match the model")
