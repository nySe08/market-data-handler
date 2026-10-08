# Low-Latency Market Data Handler (SystemVerilog)

An FPGA pipeline that parses Ethernet / IPv4 / UDP market-data packets and
maintains a top-of-book (best bid / best ask) with deterministic,
cycle-level latency.

> Status: 🚧 in progress — see `docs/PLAN.md`

## Overview

```
 byte stream ─► eth_ip_udp_parser ─► msg_decoder ─► book ─► best bid / ask
               (filter + strip       (16-byte msg    (8 levels
                headers)              → fields)       per side)
```

- **Input:** raw Ethernet frames, 8 bits per cycle (AXI-Stream style)
- **Filtering:** drops non-IPv4, non-UDP and wrong-port frames
- **Output:** best bid / ask price and quantity, pulsed on every change
- Full spec: [`docs/SPEC.md`](docs/SPEC.md)

## Results

| Metric                                   | Value |
|------------------------------------------|-------|
| Latency (last msg byte → top-of-book)    | TBD cycles (TBD ns @ 250 MHz) |
| Randomised test messages verified         | TBD   |
| Fmax (Vivado, Artix-7)                    | TBD   |
| Resources (LUT / FF)                      | TBD   |

## Verification

Testbenches use [cocotb](https://www.cocotb.org/) (Python):
`tb/packet_gen.py` builds real Ethernet/IPv4/UDP frames, and a Python
reference model checks the RTL after every update.

## Run it

```bash
# Ubuntu / WSL2
sudo apt install -y iverilog gtkwave make
pip install cocotb

cd tb
make            # run tests
make WAVES=1    # also dump waveforms (sim_build/*.fst)
```

## Design decisions

TBD: explain your choices here (why this book structure, how you
pipelined it, what limits latency and Fmax, what you would do next).
