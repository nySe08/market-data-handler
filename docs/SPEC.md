# Specification

## Input interface (v1: 8-bit stream)

One byte per clock cycle, AXI-Stream style:

| Signal         | Width | Meaning                                    |
|----------------|-------|--------------------------------------------|
| `s_tvalid`     | 1     | `s_tdata` holds a valid byte this cycle    |
| `s_tdata`      | 8     | Frame byte (first byte = first dst MAC byte) |
| `s_tlast`      | 1     | High on the last byte of the frame         |

No backpressure in v1 (the handler must always accept data, like a real
line-rate feed). The FCS (Ethernet CRC) is already stripped.

## Frame format

| Offset | Size | Field                         | Handler must check            |
|--------|------|-------------------------------|-------------------------------|
| 0      | 6    | Destination MAC               | –                             |
| 6      | 6    | Source MAC                    | –                             |
| 12     | 2    | EtherType                     | `== 0x0800` (IPv4)            |
| 14     | 1    | Version / IHL                 | `== 0x45` (no IP options)     |
| 23     | 1    | IP protocol                   | `== 17` (UDP)                 |
| 36     | 2    | UDP destination port          | `== 26400`                    |
| 38     | 2    | UDP length (header + payload) | use it to find payload end    |
| 42     | N    | Payload: one or more messages |                               |

Frames failing any check are **dropped**. Frames shorter than 60 bytes are
zero-padded, so the payload end must come from the UDP length, not `s_tlast`.

## Message: Level Update (16 bytes, big-endian)

| Offset | Size | Field        | Notes                                   |
|--------|------|--------------|-----------------------------------------|
| 0      | 1    | `msg_type`   | `'U'` = 0x55                            |
| 1      | 1    | `side`       | `'B'` = 0x42 (bid), `'S'` = 0x53 (ask)  |
| 2      | 2    | `instrument` | single instrument (1) in v1             |
| 4      | 4    | `price`      | unsigned, in ticks                      |
| 8      | 4    | `qty`        | total quantity now at this price; **0 = remove level** |
| 12     | 4    | `seq`        | sequence number                         |

## Book semantics (v2: `price_book.sv`)

Each instrument has a **price window** `[base, base + W)` (W = 256 ticks by
default), configured at start of day through the `cfg_*` port. Writing a base
also clears that instrument's book. Up to `N_INSTR = 4` instruments
(`instrument` = 0..3).

Inside the window every price tick has its own slot, so there is **no limit on
the number of levels** and no level is ever lost.

- `qty > 0`: set the quantity at that price (insert or update)
- `qty == 0`: remove that price level (unknown price: ignored)
- unknown instrument (`>= N_INSTR`): rejected, `rej_reason = 1`
- price outside the window: rejected, `rej_reason = 2`

(v1, `order_book.sv`: 8 sorted levels per side, single instrument; a level
pushed out of a full book was lost. Kept in the repo for comparison.)

## Configuration port

| Signal           | Width | Meaning                                    |
|------------------|-------|--------------------------------------------|
| `cfg_valid`      | 1     | write a price window base                  |
| `cfg_instrument` | 16    | instrument to configure                    |
| `cfg_base_px`    | 32    | lowest price of that instrument's window   |

## Outputs

| Signal           | Width | Meaning                                         |
|------------------|-------|-------------------------------------------------|
| `tob_valid`      | 1     | 1-cycle pulse: this instrument's top of book changed |
| `tob_instrument` | 16    | which instrument                                |
| `best_bid_px`    | 32    | highest bid price (0 if bid side empty)         |
| `best_bid_qty`   | 32    |                                                 |
| `best_ask_px`    | 32    | lowest ask price (0 if ask side empty)          |
| `best_ask_qty`   | 32    |                                                 |
| `tob_crossed`    | 1     | best bid >= best ask (crossed or locked book)   |
| `rej_valid`      | 1     | 1-cycle pulse: a message was rejected           |
| `rej_reason`     | 2     | 1 = unknown instrument, 2 = price outside window |

## Latency definition

**Latency = clock cycles from the last byte of a message entering the handler
to `tob_valid` going high.** Report it in cycles and in nanoseconds at your
target clock (e.g. 250 MHz = 4 ns per cycle).
