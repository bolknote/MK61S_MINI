"""Execute the exact ARM loader and independently compiled Thumb-2 module.

No serial ports, GPIO devices, flashers, or physical timing are used.
"""
from pathlib import Path
import binascii,hashlib,json,random,struct,sys
R=Path(__file__).resolve().parents[1];ROOT=R.parents[1];B=ROOT/'.build/stm32-module-runtime-20261107'
sys.path.insert(0,str(R/'tools'));sys.path.insert(0,str(ROOT/'tests'))
from elf32 import ELF
from unicorn_runtime import Uc
from unicorn import UC_ARCH_ARM,UC_MODE_MCLASS,UC_MODE_THUMB,UC_HOOK_CODE
from unicorn.arm_const import *

def encode(data):
 out=bytearray([0]);code_at=0;code=1
 for x in data:
  if x==0:out[code_at]=code;code_at=len(out);out.append(0);code=1
  else:
   out.append(x);code+=1
   if code==255:out[code_at]=code;code_at=len(out);out.append(0);code=1
 out[code_at]=code;return bytes(out)
def decode(data):
 out=bytearray();i=0
 while i<len(data):
  code=data[i];i+=1;assert code and i+code-1<=len(data)
  part=data[i:i+code-1];assert 0 not in part;out.extend(part);i+=code-1
  if code<255 and i<len(data):out.append(0)
 return bytes(out)
class Target:
 def __init__(self,elf_path=None,mmio=False):
  self.elf=ELF(elf_path or B/'arm-harness/harness.elf');self.u=Uc(UC_ARCH_ARM,UC_MODE_MCLASS|UC_MODE_THUMB)
  self.u.mem_map(0x08000000,0x10000);self.u.mem_map(0x20000000,0x5000)
  if mmio:self.u.mem_map(0x40000000,0x30000);self.u.mem_map(0xe000e000,0x2000)
  for s in self.elf.segments:
   if s['data']:self.u.mem_write(s['address'],s['data'])
  self.return_pc=0x0800fff0;self.scratch=0x20003400;self.seq=0;self.module_instructions=0;self.module_range=None
  def executed(uc,address,size,unused):
   if self.module_range and self.module_range[0]<=address<self.module_range[1]:self.module_instructions+=1
  self.u.hook_add(UC_HOOK_CODE,executed)
  self.call('harness_init')
 def call(self,name,*args):
  for reg,value in zip([UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3],args):self.u.reg_write(reg,value)
  self.u.reg_write(UC_ARM_REG_SP,0x20004ff0);self.u.reg_write(UC_ARM_REG_LR,self.return_pc|1)
  saved=[UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11]
  for i,reg in enumerate(saved):self.u.reg_write(reg,0x10000000+i*0x1111)
  self.u.emu_start(self.elf.symbols[name]['value']|1,self.return_pc,timeout=5000000,count=1000000)
  assert self.u.reg_read(UC_ARM_REG_PC)==self.return_pc,'Guest instruction/time bound or wrong return: '+name
  assert self.u.reg_read(UC_ARM_REG_SP)==0x20004ff0,'Guest stack not restored'
  assert all(self.u.reg_read(reg)==0x10000000+i*0x1111 for i,reg in enumerate(saved)),'Callee-saved register changed'
  return self.u.reg_read(UC_ARM_REG_R0)
 def send(self,frame):
  for x in frame:self.call('harness_feed',x)
  out=bytearray()
  while True:
   n=self.call('harness_transmit',self.scratch,272)
   if not n:break
   out.extend(self.u.mem_read(self.scratch,n))
  return bytes(out)
 def request(self,cmd,data=b'',expected=0):
  self.seq=(self.seq+1)&65535
  raw=struct.pack('<BBHHH',1,cmd,self.seq,len(data),0)+data;raw+=struct.pack('<I',binascii.crc32(raw))
  self.last_frame=b'\0'+encode(raw)+b'\0';response=self.send(self.last_frame)
  assert response.endswith(b'\0');decoded=decode(response[:-1]);v,op,seq,n,flags=struct.unpack_from('<BBHHH',decoded)
  assert(v,op,seq,flags)==(1,cmd|128,self.seq,0)and len(decoded)==12+n
  assert binascii.crc32(decoded[:-4])==struct.unpack_from('<I',decoded,len(decoded)-4)[0]
  status=struct.unpack_from('<I',decoded,8)[0];assert status==expected,(cmd,status,expected)
  self.last_reply=response;return decoded[12:-4]
 def load(self,package,expected=0):
  self.request(2,struct.pack('<I',len(package)))
  for at in range(0,len(package),252):self.request(3,struct.pack('<I',at)+package[at:at+252])
  result=self.request(4,expected=expected)
  if not expected:
   self.module_range=(self.call('harness_module_base'),self.call('harness_module_base')+struct.unpack_from('<I',package,16)[0])
   return struct.unpack('<I',result)[0]
def fix(package):
 data=bytearray(package);struct.pack_into('<I',data,48,binascii.crc32(data[64:]));struct.pack_into('<I',data,60,binascii.crc32(data[:60]));return bytes(data)

def main():
 t=Target();package=(B/'module/q4_dot.s3m').read_bytes();hello=t.request(1)
 baud,capabilities=struct.unpack_from('<II',hello,28)
 assert baud==2250000 and capabilities&3==3
 module=t.load(package);assert t.module_range[0]!=0x20000000,'Must relocate away from link address'
 rng=random.Random(0x53334d);checked=0;native_runs=0
 for test in range(40):
  rows=1+test%16;xs=[rng.randint(-32768,32767)for _ in range(32)];ws=[[rng.randint(-8,7)for _ in range(32)]for _ in range(rows)]
  raw=struct.pack('<III32h',0x31544451,rows,32,*xs)+bytes((w[i]+8)|((w[i+1]+8)<<4)for w in ws for i in range(0,32,2))
  for at in range(0,len(raw),252):t.request(5,struct.pack('<I',at)+raw[at:at+252])
  start=t.request(6,struct.pack('<III',module,len(raw),1000));job=struct.unpack('<I',start)[0];native_runs+=1
  # Lost reply: identical START replay must not increment the module's run count.
  if test==0:assert t.send(t.last_frame)==t.last_reply
  for _ in range(rows):t.call('harness_tick')
  status=struct.unpack('<7I',t.request(7,struct.pack('<I',job)));assert status[1:4]==(4,0,rows)
  result=t.request(8,struct.pack('<III',job,0,8+4*rows));nr,runs=struct.unpack_from('<II',result)
  assert nr==rows and runs==native_runs,'BSS state/replay changed'
  actual=struct.unpack_from('<'+'i'*rows,result,8);expected=[sum(a*b for a,b in zip(xs,w))for w in ws];assert list(actual)==expected
  checked+=rows
 # Cancellation is cooperative at a module-step boundary.
 job=struct.unpack('<I',t.request(6,struct.pack('<III',module,len(raw),1000)))[0]
 t.request(9,struct.pack('<I',job));assert t.call('harness_state')==5
 t.request(10);assert t.call('harness_empty')==1
 module=t.load(package)
 raw=struct.pack('<III32h',0x31544451,1,32,*([32767]*32))+bytes([0x00]*16)
 t.request(5,struct.pack('<I',0)+raw);job=struct.unpack('<I',t.request(6,struct.pack('<III',module,len(raw),1000)))[0]
 t.call('harness_tick');out=t.request(8,struct.pack('<III',job,0,12));assert struct.unpack('<IIi',out)==(1,1,-8388352),'BSS not zero after reload'
 t.request(10);assert t.call('harness_empty')==1
 before=t.module_instructions
 for change,error in [(4,6),(56,6),(24,5),(52,5)]:
  bad=bytearray(package);struct.pack_into('<I',bad,change,0x12345678)
  t.load(fix(bad),expected=error);assert t.module_instructions==before;t.request(10)
 # CRC/noise drop and recovery use independent Python framing.
 frame=t.last_frame;noise=bytearray(frame);noise[3]^=0x20;assert t.send(bytes(noise))==b''
 hello=t.request(1);assert struct.unpack_from('<I',hello,20)[0]>0
 assert t.module_instructions>0
 report=dict(status='ARM_EMULATION_PASS',target='Cortex-M3 Thumb-2',physical_io=False,physical_timing=False,rows_checked=checked+1,random_jobs=40,actual_module_instructions=t.module_instructions,relocated_module_base=hex(t.module_range[0]),link_base='0x20000000',duplicate_start_idempotent=True,cancel=True,reload_bss_zero=True,malformed_packages_rejected_before_execution=4,crc_noise_recovery=True,stack_and_callee_saved_checked=True,module_sha256=hashlib.sha256(package).hexdigest())
 (B/'arm-execution.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
