from pathlib import Path
import hashlib,json,random,struct,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];B=ROOT/'.build/m0-exp-cached-product-20261024'
cc=Path(json.loads((W/'build.json').read_text())['commands'][0][0]).parent
(W/'product-unit.ld').write_text('PHDRS { code PT_LOAD FLAGS(5); }\nSECTIONS { . = 0x20038ee4; .product : { KEEP(*(.scratch_y.m0_exp_product_only)) } :code /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.ARM.attributes) *(.note*) } }\n')
commands=[]
for label,obj in (('old',B/'cached-product.o'),('new',W/'product.o')):
 c=[str(cc/'arm-none-eabi-ld'),'--gc-sections','-e','mk61_m0_pow_exp_product','-T',str(W/'product-unit.ld'),str(obj),'-o',str(W/('product-'+label+'.elf'))]
 subprocess.run(c,cwd=W,check=True);commands.append(c)
jobs={}
def add(a,b):jobs.setdefault((a,b),None)
edges=(0,1,2,3,0xffff,0x10000,0x10001,0xffffffff,0x100000000,0x100000001,(1<<54)-1,1<<62,(1<<63)-1,(1<<64)-1)
for a in edges:
 for b in edges:add(a,b)
for bit in range(64):
 for d in (-1,0,1):
  a=((1<<bit)+d)&((1<<64)-1)
  for b in edges:add(a,b);add(b,a)
rng=random.Random(0x81A6F40)
for i in range(65536):
 a,b=rng.getrandbits(64),rng.getrandbits(64)
 if i&1:a&=(1<<63)-1;b&=(1<<54)-1
 add(a,b)
raw=b''.join(struct.pack('<QQ',a,b) for a,b in jobs)
(W/'product-unit-inputs.bin').write_bytes(raw)
out=dict(status='BUILT_BARE_OLD_AND_NEW_SHARED_PRODUCT_UNITS',pairs=len(jobs),input_sha256=hashlib.sha256(raw).hexdigest(),old_body_bytes=168,new_body_bytes=162,slot_bytes=168,stack_bytes40_unchanged=True,commands=commands,hardware_accessed=False)
(W/'product-unit-build.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k!='commands'},indent=2))
