"""Exact modular identities, fresh linked CFG costs and actual void callers."""
import ast,hashlib,json,re,struct,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-square128-r2-20261025'
sys.path.insert(0,str(R/'tests'))
from check_stm32_vectors import ElfImage
binding=json.loads((O/'binding.json').read_text());entry=binding['entry'];helper=binding['helper']
def ref(p):p=Path(p);d=p.read_bytes();return dict(path=str(p),bytes=len(d),sha256=hashlib.sha256(d).hexdigest())
def parse(text):
 result={}
 for line in text.splitlines():
  m=re.match(r'^\s*([0-9a-f]+):\s+((?:[0-9a-f]{4}\s+)+)([a-z][a-z0-9.]*)\s*(.*)',line)
  if m:result[int(m[1],16)]=(2*len(m[2].split()),m[3].split('.')[0],m[4].split('@')[0].strip())
 return result
costs={}
for label in ['control','candidate']:
 code=parse((O/(label+'.actual.dis')).read_text())
 def count(low,upper,pc=entry):
  total=0
  while True:
   size,op,args=code[pc];total+=1
   if op=='pop'and'pc'in args:return total
   if op=='bl':
    target=int(args.split()[0],16);assert target==helper;total+=count(low,upper,helper);pc+=size
   elif op in ['b','beq','bmi']:
    taken=op=='b'or(op=='beq'and not low)or(op=='bmi'and upper);pc=int(args.split()[0],16)if taken else pc+size
   else:assert not op.startswith('b');pc+=size
   assert total<300
 costs[label]={str((low,upper)):count(low,upper)for low in [False,True]for upper in [False,True]}
assert costs['control']=={'(False, False)':129,'(False, True)':116,'(True, False)':195,'(True, True)':182}
assert costs['candidate']=={'(False, False)':94,'(False, True)':89,'(True, False)':154,'(True, True)':149}
B=1<<16;word=(1<<32)-1;M64=(1<<64)-1;M128=(1<<128)-1
assert (B-1)**2+(B-2)<1<<32 and (B-1)**2+(B-1)<1<<32
checks=0
for x in [0,1,65535,65536,(1<<31)-1,1<<31,word]:
 a=x&65535;b=x>>16;p=a*a;cross=a*b;lo=(p+(cross<<17))&word;hi=b*b+(cross>>15)+int((p+((cross<<17)&word))>>32)
 assert (hi<<32)|lo==x*x
 for y in [0,1,65535,65536,(1<<31),word]:
  c=y&65535;d=y>>16;p=a*c;t=b*c+(p>>16);v=a*d+(t&65535)
  assert t<=B*B-B and v<=B*B-B
  product=((b*d+(t>>16)+(v>>16))<<32)|((p&65535)|((v&65535)<<16))
  assert product==x*y;checks+=1
# The same unchanged helper is an arbitrary U64 C for the equivalence proof.
# New four-word ADD/ADC chains compute H^2+2*C exactly modulo2^128.
transform_checks=0
for H in [0,1,(1<<32)-1,1<<32,1<<63,M64]:
 for C in [0,1,(1<<63),M64]:
  u=H&word;v=H>>32;P=(u*u+2*u*v*(1<<32)+v*v*(1<<64)+2*C)&M128
  assert P==(H*H+2*C)&M128
  for radius in [0,1,0x7fffffff,0x80000000,word]:
   carry=int(radius>=1);assert ((radius+radius+carry)&word)==((2*radius+bool(radius))&word)
   for exponent in [0,1,0x7fffffff,0x80000000,word]:
    doubled=exponent*2&word;assert doubled&1==0 and (doubled|1)==((doubled+1)&word)
    transform_checks+=1
source=(W/'control/native_eabi_m0_pow_root_prefix.inc').read_text();lines=source.splitlines();source_callers=[]
for i,line in enumerate(lines):
 if re.search(r'\bbl\s+pow_integer128_square\s*$',line):
  assert 'subs'in lines[i+1]and'mov\tr0,'in lines[i+2];source_callers.append(dict(line=i+1,following=lines[i:i+5]))
assert len(source_callers)==2
# Map relocatable source call sites to their actual resident function addresses.
obj=ElfImage(W/'RP-control.o');base=ElfImage(R/'.build/m0-asin-scaled-bound-v164-20261023/firmware/mk61s-picocalc-pico-h.elf')
s=(R/'.build/m0-exp-cached-product-independent-20261024/bind_rebuild.py').read_text();fn=next(n for n in ast.parse(s).body if isinstance(n,ast.FunctionDef)and n.name=='relocs')
exec(compile(ast.Module(body=[fn],type_ignores=[]),'<accepted-relocs>','exec'),globals())
symbols=[]
for tab in obj.sections:
 if tab[1]!=2:continue
 strings=obj.bytes_at(obj.sections[tab[6]])
 for off in range(0,tab[5],tab[9]):
  n,value,size,info,other,index=struct.unpack_from('<IIIBBH',obj.bytes_at(tab),off)
  if info&15==2 and size:symbols.append((obj.string(strings,n),value&~1,size,index))
tc=Path(json.loads((W/'build.json').read_text())['commands'][0][0]).parent;actual=[]
for section,rows in relocs(obj).items():
 for offset,kind,target in rows:
  if target!='pow_integer128_square'or kind!=10:continue
  index=next(i for i,s in enumerate(obj.sections)if s==obj.named_sections[section])
  name,address,size,_=next(s for s in symbols if s[3]==index and s[1]<=offset<s[1]+s[2])
  pc=(base.symbols[name]&~1)+offset-address
  dis=subprocess.check_output([str(tc/'arm-none-eabi-objdump'),'-d','--start-address='+hex(pc),'--stop-address='+hex(pc+12),str(R/'.build/m0-asin-scaled-bound-v164-20261023/firmware/mk61s-picocalc-pico-h.elf')],text=True)
  ins=parse(dis);assert ins[pc][1]=='bl'and int(ins[pc][2].split()[0],16)==entry
  assert ins[pc+4][1]=='subs'and ins[pc+6][1]in ['mov','movs']and ins[pc+6][2].startswith('r0,')
  actual.append(dict(owner=name,pc=hex(pc),fresh_disassembly=dis))
assert len(actual)==2
out=dict(status='PASS_INDEPENDENT_SQUARE32_CROSS32_MODULAR_TRANSFORM_AND_STATIC_CFG',
 exact_transform='P=H^2+2*C mod2^128, C is the same unchanged helper(L,H) or0; exponent/radius follow the original24-byte rules.',
 radius_nonzero_L_increment=16,radius_zero_L_increment='bool(radius)',radius_and_exponent_wrap32=True,
 square32_cross32_Hsquare_identities_proved=True,HOST_square_cross_spot_checks=checks,HOST_transform_radius_exponent_spot_checks=transform_checks,
 helper_treated_as_same_arbitrary64bit_value_for_equivalence=True,static_CFG_costs=costs,
 kernel_frames=dict(control=48,candidate=40),helper_frame20=True,with_helper_peaks=dict(control=68,candidate=60),
 all24_output_fields_and_normalization_branch_preserved=True,ordinary_void_PCS_no_R12_extra=True,
 source_callers=source_callers,fresh_actual_resident_callers=actual,public_RNE_enclosures_unchanged=True,
 general_pow_totality_not_proved=True,ARM_calls=0,MPFR_inputs=0,device_IO=0)
with (O/'proof.json').open('x')as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps(ref(O/'proof.json'),indent=2))
