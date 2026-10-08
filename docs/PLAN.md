# Build plan (delete this file before you publish, or keep it as a dev log)

Rule: **write all RTL yourself.** Interviewers will ask about every line.

## M0 – Setup (day 1)
- [ ] Windows: install WSL2 Ubuntu 24.04 (PowerShell as admin: `wsl --install -d Ubuntu-24.04`)
- [ ] In Ubuntu:
      `sudo apt update && sudo apt install -y iverilog gtkwave make python3-venv git`
      `python3 -m venv ~/venv && source ~/venv/bin/activate && pip install cocotb`
- [ ] `cd tb && make` → both counter tests PASS
- [ ] `make WAVES=1` → open `sim_build/counter.fst` in GTKWave
- [ ] `python3 packet_gen.py` → prints an example frame
- [ ] Create a GitHub repo and push this skeleton

## M1 – Fundamentals (week 1)
- [ ] HDLBits: Verilog language, combinational, sequential, FSMs
- [ ] Understand: blocking vs non-blocking, sync reset, setup/hold, pipelining

## M2 – Header parser (week 2)
- [ ] `rtl/eth_ip_udp_parser.sv`: byte counter + checks from SPEC.md
- [ ] Outputs a payload byte stream (valid/data/last-of-payload)
- [ ] Tests: valid frame passes, wrong EtherType / protocol / port dropped, padding ignored

## M3 – Message decoder (week 2–3)
- [ ] `rtl/msg_decoder.sv`: assemble 16 bytes → side, price, qty, seq
- [ ] Support several messages in one packet

## M4 – Order book (week 3)
- [ ] `tb/ref_model.py`: Python model of the book (your "golden" reference)
- [ ] `rtl/book.sv`: 8 levels per side, update / insert / remove
- [ ] Randomised test: 10,000+ messages, compare RTL vs reference after every update

## M5 – Measure and document (week 4)
- [ ] Measure latency in cycles (cocotb: count clocks between events)
- [ ] Optional: synthesise in Vivado (free edition) for Fmax and LUT/FF usage
- [ ] Fill in README results table + architecture diagram

## Stretch goals (pick one if time allows)
- 64-bit datapath (8 bytes per cycle) for higher throughput
- IPv4 header checksum verification
- Sequence-gap detection (flag missed messages)
