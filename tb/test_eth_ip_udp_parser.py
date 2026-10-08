"""Milestone 2: tests for rtl/eth_ip_udp_parser.sv"""
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, ReadOnly

from packet_gen import build_frame, random_message, SIDE_BID, build_message


# ---------------------------------------------------------------- helpers
async def setup(dut):
    """Start the clock and reset the DUT."""
    cocotb.start_soon(Clock(dut.clk, 4, unit="ns").start())   # 250 MHz
    dut.rst.value = 1
    dut.s_tvalid.value = 0
    dut.s_tdata.value = 0
    dut.s_tlast.value = 0
    await ClockCycles(dut.clk, 2)
    dut.rst.value = 0


async def send_frame(dut, frame: bytes):
    """Drive one frame into the DUT, one byte per clock cycle."""
    for i, b in enumerate(frame):
        dut.s_tvalid.value = 1
        dut.s_tdata.value = b
        dut.s_tlast.value = int(i == len(frame) - 1)
        await RisingEdge(dut.clk)
    dut.s_tvalid.value = 0
    dut.s_tlast.value = 0


async def collect_payloads(dut, out: list):
    """Monitor: record every payload the DUT outputs (split on m_tlast)."""
    current = bytearray()
    while True:
        await RisingEdge(dut.clk)
        await ReadOnly()
        if dut.m_tvalid.value == 1:
            current.append(int(dut.m_tdata.value))
            if dut.m_tlast.value == 1:
                out.append(bytes(current))
                current = bytearray()


def corrupt(frame: bytes, offset: int, value: int) -> bytes:
    f = bytearray(frame)
    f[offset] = value
    return bytes(f)


# ------------------------------------------------------------------ tests
@cocotb.test()
async def valid_frame_passes(dut):
    """A valid frame's payload comes out exactly; Ethernet padding does not."""
    await setup(dut)
    out = []
    cocotb.start_soon(collect_payloads(dut, out))

    msg = build_message(SIDE_BID, price=10_000, qty=300)
    frame = build_frame([msg])            # 58 bytes -> padded to 60
    assert len(frame) == 60

    await send_frame(dut, frame)
    await ClockCycles(dut.clk, 3)
    assert out == [msg], f"expected {msg.hex()}, got {[p.hex() for p in out]}"


@cocotb.test()
async def bad_headers_are_dropped(dut):
    """Wrong EtherType / IP version / protocol / port -> nothing comes out."""
    await setup(dut)
    out = []
    cocotb.start_soon(collect_payloads(dut, out))

    good = build_frame([build_message(SIDE_BID, 10_000, 300)])
    bad_frames = {
        "ethertype": corrupt(good, 12, 0x86),   # 0x86DD = IPv6
        "ip_ihl":    corrupt(good, 14, 0x46),   # IP options present
        "protocol":  corrupt(good, 23, 6),      # TCP
        "port":      build_frame([build_message(SIDE_BID, 10_000, 300)], dst_port=1234),
    }
    for name, f in bad_frames.items():
        await send_frame(dut, f)

    await ClockCycles(dut.clk, 3)
    assert out == [], f"bad frames leaked through: {[p.hex() for p in out]}"


@cocotb.test()
async def random_back_to_back(dut):
    """200 random frames, valid and invalid, sent with NO gaps between them."""
    await setup(dut)
    out = []
    cocotb.start_soon(collect_payloads(dut, out))

    rng = random.Random(1234)
    expected = []
    seq = 0
    for _ in range(200):
        msgs = []
        for _ in range(rng.randint(1, 4)):        # 1-4 messages per packet
            msgs.append(random_message(seq, rng))
            seq += 1
        frame = build_frame(msgs)

        if rng.random() < 0.25:                   # 25% invalid frames
            frame = corrupt(frame, rng.choice([12, 14, 23, 37]), 0xEE)
        else:
            expected.append(b"".join(msgs))

        await send_frame(dut, frame)              # back-to-back

    await ClockCycles(dut.clk, 3)
    assert len(out) == len(expected), f"got {len(out)} payloads, expected {len(expected)}"
    for i, (got, exp) in enumerate(zip(out, expected)):
        assert got == exp, f"payload {i}: got {got.hex()} expected {exp.hex()}"
    dut._log.info(f"{len(expected)} valid payloads checked, invalid frames dropped")
