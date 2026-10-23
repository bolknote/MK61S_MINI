"""Add30 MPFR-pinned public pow cases for the negative factor product path."""
from pathlib import Path
import hashlib
import json
import struct
import sys
root=Path.cwd();work=Path(__file__).resolve().parent
sys.path.insert(0,str(root/'tests'))
from m0_mpfr_oracle import Oracle,bits
cfg=json.loads((work/'benchmark.json').read_text());oracle=Oracle();rows=[]
for x in (1.00001,1.234567,3.141592,2.5,.123456,15.876):
    for y in (-.75,-.625,-.875,-.9375,-31/128):
        a,b=bits(x),bits(y);rows.append((a,b,oracle.reference('pow',a,b)))
prototype=cfg['chunks'][-1];index=119
blob=struct.pack('<8I',0x4d304246,1,index,0,len(rows),1,prototype['own_address'],prototype['qfplib_address'])+b''.join(struct.pack('<3Q',*r) for r in rows)
path=work/'inputs/119.bin';path.write_bytes(blob)
chunk=dict(index=index,stream_index=117,part=0,operation='pow',stream='negative_factor_path_canary',
    kind=0,cases=len(rows),loops=1,input=str(path),input_sha256=hashlib.sha256(blob).hexdigest(),
    own_symbol=prototype['own_symbol'],qfplib_symbol=prototype['qfplib_symbol'],
    own_address=prototype['own_address'],qfplib_address=prototype['qfplib_address'],role='verification_canary',
    reference_kind='qfplib_composition',reference_formula='exp(mul(y,ln(x)))')
cfg['verification_canaries']=[chunk]
(work/'benchmark.json').write_text(json.dumps(cfg,indent=2)+'\n')
(work/'canary-oracle.json').write_text(json.dumps(dict(status='PASS_MPFR_DIRECTED_BOUNDS',
    cases=len(rows),mpfr=oracle.version,description='Negative proper fractions with multiple selected bits to exercise factor64_multiply through public pow; supplementary correctness/path checks, outside117 performance groups.',
    input_sha256=chunk['input_sha256'],producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),indent=2)+'\n')
print('PASS:30 supplementary publicpow path canaries.')
