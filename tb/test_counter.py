"""Milestone 0: cocotb test for rtl/counter.sv."""
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, ReadOnly


@cocotb.test()
async def counts_when_enabled(dut):
    """Counter should increase by exactly 1 per enabled clock cycle."""
    cocotb.start_soon(Clock(dut.clk, 4, unit="ns").start())  # 250 MHz

    # Reset for 2 cycles
    dut.rst.value = 1
    dut.en.value = 0
    await ClockCycles(dut.clk, 2)
    dut.rst.value = 0

    # Enable for 10 cycles
    dut.en.value = 1
    await ClockCycles(dut.clk, 10)
    await ReadOnly()
    assert int(dut.count.value) == 10, f"expected 10, got {int(dut.count.value)}"


@cocotb.test()
async def holds_when_disabled(dut):
    """Counter should not change while en = 0."""
    cocotb.start_soon(Clock(dut.clk, 4, unit="ns").start())

    dut.rst.value = 1
    dut.en.value = 0
    await ClockCycles(dut.clk, 2)
    dut.rst.value = 0
    await ClockCycles(dut.clk, 5)
    await ReadOnly()
    assert int(dut.count.value) == 0
