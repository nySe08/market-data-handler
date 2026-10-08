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

## Book semantics

The handler keeps up to **N = 8 price levels per side**.

- `qty > 0` and price exists: update its quantity
- `qty > 0` and price is new: insert it (if the side is full, drop the worst level)
- `qty == 0`: remove that price level

## Outputs

| Signal          | Width | Meaning                                  |
|-----------------|-------|------------------------------------------|
| `tob_valid`     | 1     | One-cycle pulse when best bid/ask changed |
| `best_bid_px`   | 32    | Highest bid price (0 if bid side empty)  |
| `best_bid_qty`  | 32    |                                          |
| `best_ask_px`   | 32    | Lowest ask price (0 if ask side empty)   |
| `best_ask_qty`  | 32    |                                          |

## Latency definition

**Latency = clock cycles from the last byte of a message entering the handler
to `tob_valid` going high.** Report it in cycles and in nanoseconds at your
target clock (e.g. 250 MHz = 4 ns per cycle).
