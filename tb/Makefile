# cocotb Makefile (cocotb 2.x + Icarus Verilog)
#
# Run the parser tests (default):   make
# Run another module's tests:       make TOP=counter
# With waveforms:                   make WAVES=1   (sim_build/<TOP>/<TOP>.fst)

TOP ?= eth_ip_udp_parser

SIM ?= icarus
TOPLEVEL_LANG ?= verilog
COMPILE_ARGS += -g2012

# compile every RTL file; -s picks the top module
VERILOG_SOURCES = $(wildcard $(PWD)/../rtl/*.sv)
COCOTB_TOPLEVEL = $(TOP)
COCOTB_TEST_MODULES = test_$(TOP)
SIM_BUILD = sim_build/$(TOP)

include $(shell cocotb-config --makefiles)/Makefile.sim
