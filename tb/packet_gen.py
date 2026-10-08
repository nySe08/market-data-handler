"""
Packet generator for the market-data handler testbench.

Builds raw Ethernet / IPv4 / UDP frames carrying the simple market-data
messages defined in docs/SPEC.md. All multi-byte fields are big-endian
(network byte order).

Run `python3 packet_gen.py` to print an example frame as hex.
"""
import random
import struct

ETH_TYPE_IPV4 = 0x0800
IP_PROTO_UDP = 17
FEED_UDP_PORT = 26400  # the only UDP port the handler should accept

MSG_LEVEL_UPDATE = ord("U")  # 0x55
SIDE_BID = ord("B")          # 0x42
SIDE_ASK = ord("S")          # 0x53

MSG_LEN = 16


def ipv4_checksum(header: bytes) -> int:
    """Standard one's-complement sum over 16-bit words."""
    total = 0
    for i in range(0, len(header), 2):
        total += (header[i] << 8) | header[i + 1]
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def build_message(side: int, price: int, qty: int, instrument: int = 1, seq: int = 0) -> bytes:
    """16-byte Level Update message (see docs/SPEC.md)."""
    return struct.pack(">BBHIII", MSG_LEVEL_UPDATE, side, instrument, price, qty, seq)


def build_frame(messages: list[bytes], dst_port: int = FEED_UDP_PORT) -> bytes:
    """Wrap one or more messages in UDP, IPv4 and Ethernet headers."""
    payload = b"".join(messages)

    udp_len = 8 + len(payload)
    udp = struct.pack(">HHHH", 40000, dst_port, udp_len, 0)  # checksum 0 = unused (allowed in IPv4)

    ip_total_len = 20 + udp_len
    ip_wo_csum = struct.pack(
        ">BBHHHBBH4s4s",
        0x45, 0, ip_total_len,      # version/IHL, DSCP/ECN, total length
        0, 0,                       # identification, flags/fragment offset
        64, IP_PROTO_UDP, 0,        # TTL, protocol, checksum placeholder
        bytes([10, 0, 0, 1]),       # source IP
        bytes([239, 1, 1, 1]),      # destination IP (multicast, like real feeds)
    )
    csum = ipv4_checksum(ip_wo_csum)
    ip = ip_wo_csum[:10] + struct.pack(">H", csum) + ip_wo_csum[12:]

    eth = (
        bytes([0x01, 0x00, 0x5E, 0x01, 0x01, 0x01])   # dst MAC (multicast)
        + bytes([0x02, 0x00, 0x00, 0x00, 0x00, 0x01]) # src MAC
        + struct.pack(">H", ETH_TYPE_IPV4)
    )
    frame = eth + ip + udp + payload
    # Ethernet minimum frame size is 60 bytes (excluding FCS): short frames get
    # zero padding. Your parser must use the UDP length, NOT the frame length.
    if len(frame) < 60:
        frame += bytes(60 - len(frame))
    return frame


def random_message(seq: int, rng: random.Random) -> bytes:
    side = rng.choice([SIDE_BID, SIDE_ASK])
    price = rng.randint(9_900, 10_100)          # price in ticks
    qty = 0 if rng.random() < 0.2 else rng.randint(1, 500)  # qty 0 = remove level
    return build_message(side, price, qty, seq=seq)


def decode_message(msg: bytes) -> dict:
    """Helper for your reference model / debugging."""
    mtype, side, instr, price, qty, seq = struct.unpack(">BBHIII", msg)
    return {"type": chr(mtype), "side": chr(side), "instrument": instr,
            "price": price, "qty": qty, "seq": seq}


if __name__ == "__main__":
    rng = random.Random(42)
    msg = random_message(seq=1, rng=rng)
    frame = build_frame([msg])

    print(f"Frame length: {len(frame)} bytes (14 eth + 20 ip + 8 udp + 16 payload + padding)")
    for off in range(0, len(frame), 16):
        chunk = frame[off:off + 16]
        print(f"{off:04x}  " + " ".join(f"{b:02x}" for b in chunk))
    print("Decoded message:", decode_message(msg))

    # Sanity check: a valid IPv4 header checksums to zero
    assert ipv4_checksum(frame[14:34]) == 0, "IPv4 checksum error"
    print("IPv4 checksum OK")
