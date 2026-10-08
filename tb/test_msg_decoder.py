"""Milestone 3: tests for rtl/msg_decoder.sv"""
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge, ReadOnly

from packet_gen import build_message, random_message, decode_message, SIDE_BID, SIDE_ASK


# ---------------------------------------------------------------- helpers
async def setup(dut):
    cocotb.start_soon(Clock(dut.clk, 4, unit="ns").start())   # 250 MHz
    dut.rst.value = 1
    dut.s_tvalid.value = 0
    dut.s_tdata.value = 0
    dut.s_tlast.value = 0
    await ClockCycles(dut.clk, 2)
    dut.rst.value = 0


async def send_payload(dut, payload: bytes):
    """Drive one payload (= what the parser outputs for one packet)."""
    for i, b in enumerate(payload):
        dut.s_tvalid.value = 1
        dut.s_tdata.value = b
        dut.s_tlast.value = int(i == len(payload) - 1)
        await RisingEdge(dut.clk)
    dut.s_tvalid.value = 0
    dut.s_tlast.value = 0


def read_outputs(dut) -> dict:
    return {
        "side": "B" if dut.msg_is_bid.value == 1 else "S",
        "instrument": int(dut.msg_instrument.value),
        "price": int(dut.msg_price.value),
        "qty": int(dut.msg_qty.value),
        "seq": int(dut.msg_seq.value),
    }


def expected_fields(msg: bytes) -> dict:
    d = decode_message(msg)
    del d["type"]
    return d


async def collect_messages(dut, out: list):
    """Monitor: record every decoded message."""
    while True:
        await RisingEdge(dut.clk)
        await ReadOnly()
        if dut.msg_valid.value == 1:
            out.append(read_outputs(dut))


# ------------------------------------------------------------------ tests
@cocotb.test()
async def single_message_and_latency(dut):
    """One message decodes correctly, 1 cycle after its last byte."""
    await setup(dut)
    msg = build_message(SIDE_ASK, price=10_050, qty=75, instrument=1, seq=42)

    for i, b in enumerate(msg):
        dut.s_tvalid.value = 1
        dut.s_tdata.value = b
        dut.s_tlast.value = int(i == len(msg) - 1)
        await RisingEdge(dut.clk)     # DUT samples byte i on this edge
        await FallingEdge(dut.clk)    # half a cycle later: outputs are stable
        if i < len(msg) - 1:
            assert dut.msg_valid.value == 0, f"msg_valid too early (byte {i})"

    # the same edge that sampled byte 15 registered the decoded message
    assert dut.msg_valid.value == 1, "msg_valid not high 1 cycle after last byte"
    assert read_outputs(dut) == expected_fields(msg)
    dut.s_tvalid.value = 0
    dut.s_tlast.value = 0


@cocotb.test()
async def bad_messages_are_dropped(dut):
    """Unknown msg_type or side -> no output; a good message after it still works."""
    await setup(dut)
    out = []
    cocotb.start_soon(collect_messages(dut, out))

    good = build_message(SIDE_BID, 9_990, 10, seq=1)
    bad_type = bytes([0x41]) + good[1:]            # 'A' instead of 'U'
    bad_side = good[:1] + bytes([0x58]) + good[2:] # 'X' instead of 'B'/'S'

    await send_payload(dut, bad_type + bad_side + good)   # 3 messages, 1 packet
    await ClockCycles(dut.clk, 3)
    assert out == [expected_fields(good)], f"got {out}"


@cocotb.test()
async def truncated_message_is_discarded(dut):
    """A packet ending mid-message must not corrupt the next packet."""
    await setup(dut)
    out = []
    cocotb.start_soon(collect_messages(dut, out))

    m1 = build_message(SIDE_BID, 10_000, 5, seq=1)
    m2 = build_message(SIDE_ASK, 10_010, 7, seq=2)

    await send_payload(dut, m1 + m2[:9])   # second message cut off after 9 bytes
    await send_payload(dut, m2)            # next packet: complete message
    await ClockCycles(dut.clk, 3)
    assert out == [expected_fields(m1), expected_fields(m2)], f"got {out}"


@cocotb.test()
async def random_stream(dut):
    """500 packets of 1-4 random messages, sent back to back."""
    await setup(dut)
    out = []
    cocotb.start_soon(collect_messages(dut, out))

    rng = random.Random(7)
    expected, seq = [], 0
    for _ in range(500):
        msgs = []
        for _ in range(rng.randint(1, 4)):
            msgs.append(random_message(seq, rng))
            seq += 1
        expected += [expected_fields(m) for m in msgs]
        await send_payload(dut, b"".join(msgs))

    await ClockCycles(dut.clk, 3)
    assert len(out) == len(expected), f"got {len(out)} messages, expected {len(expected)}"
    for i, (got, exp) in enumerate(zip(out, expected)):
        assert got == exp, f"message {i}: got {got}, expected {exp}"
    dut._log.info(f"{len(expected)} messages decoded correctly")
