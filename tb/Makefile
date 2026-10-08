# cocotb Makefile (cocotb 2.x + Icarus Verilog)
# Run:            make
# With waveforms: make WAVES=1   (then open the waveform file in GTKWave)

SIM ?= icarus
TOPLEVEL_LANG ?= verilog

# -g2012 enables SystemVerilog support in Icarus
COMPILE_ARGS += -g2012

VERILOG_SOURCES += $(PWD)/../rtl/counter.sv
COCOTB_TOPLEVEL = counter
COCOTB_TEST_MODULES = test_counter

include $(shell cocotb-config --makefiles)/Makefile.sim
