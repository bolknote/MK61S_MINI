"""Strict bounded warm-up header for the sin/cos-only hardware comparison."""
import struct
from hil_m0_math_compare import decode


def decode_v5(raw,chunk,inputs,*,minimum_warmup_us=1000000,pairs_cap=32768):
    assert len(raw)>=48
    h=struct.unpack_from('<12I',raw)
    assert h[0:2]==(0x4D305250,5) and h[6]==12
    assert h[9]>=minimum_warmup_us and 0<h[10]<=pairs_cap and h[11]==0
    # The payload and first ten fields retain the qualified v4 contract.
    # Preserve the actual v5 bytes; this is only a pure HOST decoding view.
    legacy=raw[:4]+struct.pack('<I',4)+raw[8:40]+raw[48:]
    result=decode(legacy,chunk,inputs)
    result.update(actual_wire_version=5,warmup_pairs=h[10],warmup_pairs_cap=pairs_cap,
                  bounded_warmup_verified=True,actual_v5_bytes_not_rewritten=True)
    return result
