"""Execute the relocated INT8 M3 module against an independent FP32 oracle."""
from pathlib import Path
import hashlib,importlib.util,json,random,struct,sys
ROOT=Path(__file__).resolve().parents[1]
R=ROOT/'research/picocalc-stm32-runtime-20261107'
sys.path.insert(0,str(R/'tests'))
spec=importlib.util.spec_from_file_location('integer_arm_vectors',R/'tests/arm_execution.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
v.B=v.B/'southbridge-runtime'
B=ROOT/'.build/mk61ai/m3-int8/module'
MAGIC=0x31494941
f32=lambda x:struct.unpack('<f',struct.pack('<f',x))[0]

def run(t,module,raw,out_bytes):
 for at in range(0,len(raw),252):t.request(5,struct.pack('<I',at)+raw[at:at+252])
 job=struct.unpack('<I',t.request(6,struct.pack('<III',module,len(raw),1000)))[0]
 for _ in range(18):
  status=struct.unpack('<7I',t.request(7,struct.pack('<I',job)))
  if status[1]==4:break
  assert status[1]==3,status
  t.call('harness_tick')
 assert status[1:3]==(4,0),status
 return t.request(8,struct.pack('<III',job,0,out_bytes))

t=v.Target();package=(B/'M3LINE.S3M').read_bytes();module=t.load(package)
assert t.module_range[0]!=0x20000000
rng=random.Random(0x49334d);rows_checked=0
for cols in (32,128,384,512):
 rows=min(2,(512-16)//(cols//2+cols//16))
 for sample in range(20):
  x=[(-128 if j&1 else 127)if sample<2 else rng.randrange(-128,128)for j in range(cols)]
  act=[f32((1+rng.randrange(1000))*2**-16)for _ in range(cols//32)]
  if sample==2:act=[0.0]*len(act)
  weights=[bytes(rng.randrange(256)for _ in range(cols//2))for _ in range(rows)]
  edges=[0,0x8000,1,0x83ff,0x400,0xbc00,0x3c00,0x7bff]
  scales=[[edges[sample]if sample<8 else rng.randrange(0x7800)^(rng.randrange(2)<<15)
           for _ in range(cols//32)]for _ in range(rows)]
  ack=run(t,module,struct.pack('<4I',MAGIC,1,cols,0),12)
  assert struct.unpack('<3I',ack)==(MAGIC,cols,0)
  vector=struct.pack('<'+'b'*cols,*x)+struct.pack('<'+'f'*len(act),*act)
  for at in range(0,len(vector),512):
   chunk=vector[at:at+512];ack=run(t,module,chunk,12)
   assert struct.unpack('<3I',ack)==(MAGIC,cols,at+len(chunk))
  raw=struct.pack('<4I',MAGIC,2,cols,rows)+b''.join(w+struct.pack('<'+'H'*len(s),*s)for w,s in zip(weights,scales))
  out=run(t,module,raw,rows*4);expected=[]
  for row in range(rows):
   total=0.0
   for g in range(cols//32):
    dot=sum((int((weights[row][j//2]>>(4*(j&1)))&15)-8)*x[j]for j in range(32*g,32*g+32))
    scale=struct.unpack('<e',struct.pack('<H',scales[row][g]))[0]
    total=f32(total+f32(f32(f32(dot)*scale)*act[g]))
   expected.append(total)
  assert out==struct.pack('<'+'f'*rows,*expected),(cols,sample,out,expected)
  rows_checked+=rows
t.request(10);assert t.call('harness_empty')==1
report=dict(status='M3_INT8_RELOCATED_ARM_PASS',physical_io=False,hardware_timing=False,
 package_sha256=hashlib.sha256(package).hexdigest(),independent_exact_rows=rows_checked,
 sbfx_actual_Thumb2=True,float_group_scaling_matches_oracle=True,module_instructions=t.module_instructions)
(B/'arm-verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
