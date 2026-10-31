#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,struct,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
OUT=ROOT/'.build/rp2040-interpolator-20261023/followon'
sys.path[:0]=[str(HERE),str(ROOT/'tests'),str(ROOT/'tools')]
from verify import Model,fixtures
from exact_oracle import root_oracle
from decode import decode
from build_picocalc import compiler_bin
from m0_math_compare_app_self_test import SHIM
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC

def main():
 manifest=json.loads((OUT/'app-manifest.json').read_text());shipping={};protocol={};tc=compiler_bin(None)
 for variant,app in manifest['apps'].items():
  m=Model(Path(app['elf']));uc=m.uc
  def cfg(base,off,val):uc.mem_write(base+off,struct.pack('<I',val))
  if variant=='lookup':
   cfg(0xd00000c0,44,8|(4<<5)|(11<<10));cfg(0xd00000c0,8,m.elf.symbols['_ZL9log_table'])
  elif variant in ('sqrt','rsqrt'):
   cfg(0xd0000080,44,1<<21);cfg(0xd0000080,48,7<<10);cfg(0xd0000080,8,0)
  cases=[b for row in fixtures() for b in row]
  if variant!='pop':
   for b in cases:
    names=('fo_ln_cpu','fo_ln_interp') if variant=='lookup' else tuple('fo_'+variant+'_'+x for x in ('base','new_cpu','new_interp'))
    outputs=[m.call(name,b)[0] for name in names];assert len(set(outputs))==1,(variant,hex(b),outputs)
    if variant!='lookup':assert outputs[0]==root_oracle(b,variant=='rsqrt'),(variant,hex(b),outputs)
  else:
   for group in (0,1):
    if not group:
     cfg(0xd0000080,44,(1<<18)|16|(5<<10));cfg(0xd0000080,48,(1<<18)|10|(6<<5)|(11<<10));cfg(0xd0000080,16,m.elf.symbols['_ZL4data'])
    else:
     cfg(0xd0000080,44,(1<<21)|14|(2<<5)|(9<<10));cfg(0xd0000080,48,(1<<16)|(1<<15)|8|(7<<10));cfg(0xd0000080,16,m.elf.symbols['_ZL4data']+4096)
    for j,n in enumerate((1,32,256,1024)):
     seed=0xaab1c3d451379bbc+j;outputs=[];returns=[]
     for name in (('fo_texture_cpu','fo_texture_pop') if not group else ('fo_audio_cpu','fo_audio_interp')):
      returns.append(m.call(name,seed,n)[0]);outputs.append(bytes(uc.mem_read(m.elf.symbols['fo_output'],n*(1+group))))
     assert outputs[0]==outputs[1] and returns[0]==returns[1],(variant,group,j)
  shipping[variant]=dict(actual_arm_calls=m.calls,elf_sha256=hashlib.sha256(Path(app['elf']).read_bytes()).hexdigest(),app_sha256=app['sha256'])
  print('Shipping kernels PASS '+variant,flush=True)
 # Reduced loops exercise the exact benchmark source and file/result path.
 dest=OUT/'protocol';dest.mkdir(exist_ok=True);(dest/'api.c').write_text(SHIM)
 flags=['-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-Os','-fno-builtin','-ffunction-sections','-fdata-sections','-I'+str(HERE),'-I'+str(ROOT/'sdk/portable/include'),'-I'+str(ROOT/'code')]
 for name,source in (('api',dest/'api.c'),('memory',ROOT/'sdk/portable/memory.c')):
  subprocess.run([str(tc/'arm-none-eabi-gcc'),*flags,'-c',str(source),'-o',str(dest/(name+'.o'))],check=True)
 for ident,variant in enumerate(manifest['apps'],1):
  obj=dest/(variant+'.o');elf=dest/(variant+'.elf')
  subprocess.run([str(tc/'arm-none-eabi-gcc'),*flags,'-DINTERP_VARIANT='+str(ident),'-DINTERP_SAMPLES=4','-DINTERP_ROUNDS=2','-c',str(HERE/'benchmark.c'),'-o',str(obj)],check=True)
  objects=[obj,dest/'api.o',dest/'memory.o',*[OUT/(name+'.o') for name in ('lookup.cpp','pop.cpp','roots.cpp','sqrt-full.S','divide.S')]]
  subprocess.run([str(tc/'arm-none-eabi-gcc'),*flags,'-nostdlib',*[str(x) for x in objects],'-Wl,-T,'+str(OUT/'kernels.ld'),'-Wl,-e,main','-lgcc','-o',str(elf)],check=True)
  m=Model(elf);m.instruction_budget=100000000;uc=m.uc
  for base in (0x40054000,0x40008000,0x40028000):uc.mem_map(base,4096)
  initial=[]
  for b in range(2):
   for off,v in zip((0,4,8,12,16,44,48),(0x12345678+b,0x89abcdef-b,123,456,789,15<<10,31<<10)):
    uc.mem_write(0xd0000080+b*64+off,struct.pack('<I',v));initial.append(v)
  uc.mem_write(0xd0000078,struct.pack('<I',1))
  for addr,v in zip((0x4000803c,0x40008040,0x40008044,0x40028000,0x40028004,0x40028008,0x4002800c),(1,256,2,0x80000001,0,125,(6<<16)|(2<<12))):uc.mem_write(addr,struct.pack('<I',v))
  ticks=0;writes=[]
  def timer(uc,access,address,size,value,user):
   nonlocal ticks
   ticks+=100;uc.mem_write(address,struct.pack('<I',ticks))
  uc.hook_add(UC_HOOK_MEM_READ,timer,begin=0x40054028,end=0x4005402b)
  operations=struct.unpack('<4I',uc.mem_read(m.elf.symbols['operations'],16))
  file_object=bytes(uc.mem_read(m.elf.symbols['file_object'],m.elf.sizes['file_object']))
  def callback(uc,address,size,user):
   r=[uc.reg_read(reg) for reg in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)];result=0
   if address==0x080e0020:result=m.elf.symbols['services']
   elif address==0x080e0010:
    if r[0]==operations[0]:result=operations[3]
    else:
     ptr=int.from_bytes(uc.mem_read(uc.reg_read(UC_ARM_REG_SP),4),'little')
     if r[0]==operations[1]:uc.mem_write(ptr,file_object)
     elif r[0]==operations[2]:
      name,data,length,_=struct.unpack('<4I',uc.mem_read(ptr,16));assert bytes(uc.mem_read(name,7))==b'RESULT\0'
      writes.append(bytes(uc.mem_read(data,length)));result=1
     else:raise AssertionError(r)
   else:assert address==0x080e0050
   uc.reg_write(UC_ARM_REG_R0,result);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
  for addr in (0x080e0010,0x080e0020,0x080e0050):
   uc.mem_write(addr,b'\x70\x47');uc.hook_add(UC_HOOK_CODE,callback,begin=addr,end=addr)
  returned=m.call('main',0)[0]&0xffffffff
  assert returned==0 and len(writes)==1,(variant,returned,len(writes))
  report=decode(writes[0],variant=variant,physical=False,expected_rounds=2,expected_samples=4)
  final=[int.from_bytes(uc.mem_read(0xd0000080+b*64+off,4),'little') for b in range(2) for off in (0,4,8,12,16,44,48)]
  assert initial==final
  rejected=0
  for off in (4,20,28,56,144,256+48+24*2):
   bad=bytearray(writes[0]);bad[off]^=128
   try:decode(bytes(bad),variant=variant,physical=False,expected_rounds=2,expected_samples=4)
   except AssertionError:rejected+=1
  assert rejected==6
  (dest/(variant+'-result.bin')).write_bytes(writes[0])
  protocol[variant]=dict(status='PASS',rows=report['rows'],negative_decoder_cases=rejected,timer_reads=ticks//100,elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest())
  print('APP protocol PASS '+variant,flush=True)
 report=dict(status='PASS',physical_timing=False,shipping=shipping,protocol=protocol)
 (OUT/'shipping-and-protocol.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
