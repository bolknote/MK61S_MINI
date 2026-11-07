"""Losslessly change Q4 bitplanes to paired-nibble layout; no requantization."""
from pathlib import Path
import hashlib,json,struct,sys,zlib
source=Path(sys.argv[1]);destination=Path(sys.argv[2]);data=bytearray(source.read_bytes())
h=list(struct.unpack_from('<32I',data));assert data[:8]==b'M61AI01\0'
assert zlib.crc32(data[:124])==h[31] and zlib.crc32(data[128:])==h[29]
groups=tensors=0
for i in range(2+11*h[4]):
    at=h[15]+32*i;rows,cols,bits,grid,offset,scale,count,scales=struct.unpack_from('<8I',data,at)
    if bits!=4 or not grid&256:continue
    assert count%16==0
    for start in range(offset,offset+count,16):
        p=data[start:start+16];out=bytearray(16)
        for j in range(32):
            quartet,lane=divmod(j,4);value=0
            for bit in range(4):value|=((p[4*bit+quartet//2]>>(4*(quartet%2)+lane))&1)<<bit
            out[j//2]|=value<<(4*(j%2))
        data[start:start+16]=out;groups+=1
    struct.pack_into('<I',data,at+12,grid&~256);tensors+=1
struct.pack_into('<I',data,29*4,zlib.crc32(data[128:]))
struct.pack_into('<I',data,31*4,zlib.crc32(data[:124]))
destination.write_bytes(data)
print(json.dumps(dict(lossless_repack=True,tensors=tensors,groups32=groups,bytes=len(data),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),sha256=hashlib.sha256(data).hexdigest())))
