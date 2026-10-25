"""Private BSD-derived ddiv clone: preserve READY; use exact seed17 for DIRTY."""
from pathlib import Path
import ast,difflib,hashlib,json,re,shlex,struct,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
BASE=ROOT/'.build/m0-pow-boundary128-20261025'
SEED=ROOT/'.build/m0-ddiv-soft-seed17-20261025'
assert not (W/'FROZEN.json').exists()
sys.path.insert(0,str(ROOT/'tests'));from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
source=(P/'source/code/native_eabi_m0_rp2040.S').read_text()
header=source[:source.index('#if')]
header=header.replace('fallback while SIO\'s divider is dirty.', 'an exact software seed continuation while SIO\'s divider is dirty.')
guard='#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI\n'
setup=guard+'.syntax unified\n.cpu cortex-m0plus\n.thumb\n.equ IOPORT,0xd0000000\n.equ DIV_UDIVIDEND,0x60\n.equ DIV_UDIVISOR,0x64\n.equ DIV_QUOTIENT,0x70\n'
macro=''
for name in ['mul32_32_64','muls32_32_64']:
 a=source.index('.macro '+name+' ');b=source.index('.endm',a)+len('.endm')
 macro+=source[a:b]+'\n'
start=source.index('.Lrp2040_small_divisor:');end=source.index('#include',start)
body=source[start:end]
entry='regular_func __aeabi_ddiv'
replacement='.global mk61_m0_hint_ddiv\n.hidden mk61_m0_hint_ddiv\n.type mk61_m0_hint_ddiv,%function\n.thumb_func\nmk61_m0_hint_ddiv:'
assert body.count(entry)==1
body=body.replace(entry,replacement)
tail_end=body.index('\n.align 2\n// Nearest-even')
body=body[:tail_end]+'\n.size mk61_m0_hint_ddiv,.-mk61_m0_hint_ddiv\n'+body[tail_end:]
bridge='''.Lrp2040_div_dirty_bridge:
 ldr r7,.Lrp2040_sw_target
 bx r7
.p2align 2
.Lrp2040_sw_target: .word mk61_m0_ddiv_sw_from_guard
.fill (12-(.-.Lrp2040_div_dirty_bridge))/2,2,0xbf00
'''
candidate=body.replace(' bcs .Lrp2040_div_slow',' bcs .Lrp2040_div_dirty_bridge')
assert candidate!=body and candidate.count('bcs .Lrp2040_div_dirty_bridge')==1
candidate=candidate.replace('.Lrp2040_div_slow:',bridge+'\n.Lrp2040_div_slow:')
sw=body[body.index('.Lrp2040_general_divisor:'):body.index('\n.size mk61_m0_hint_ddiv,')]
sw=sw.replace('.Lrp2040_general_divisor:', '.global mk61_m0_ddiv_sw_from_guard\n.hidden mk61_m0_ddiv_sw_from_guard\n.type mk61_m0_ddiv_sw_from_guard,%function\n.thumb_func\nmk61_m0_ddiv_sw_from_guard:')
sw=sw.replace('push {r0-r3}', 'push {r0-r3,r7}').replace('pop {r0-r3}', 'pop {r0-r3,r7}')
sw=sw.replace('bl __aeabi_uidiv              @ !!! this could (but apparently does not) trash R12','bl mk61_m0_ddiv_seed17        @ exact quotient, explicitly preserves R12')
assert '__aeabi_uidiv' not in sw
sw+='\n.size mk61_m0_ddiv_sw_from_guard,.-mk61_m0_ddiv_sw_from_guard\n.ltorg\n'
join=' muls r5,r6                    @ u0*x1 Q45'
assert body.count(join)==candidate.count(join)==sw.count(join)==1
body=body.replace(join,'.global mk61_m0_hint_join\nmk61_m0_hint_join:\n'+join)
candidate=candidate.replace(join,'.global mk61_m0_hint_join\nmk61_m0_hint_join:\n'+join)
sw=sw.replace(join,'.global mk61_m0_sw_join\nmk61_m0_sw_join:\n'+join)
for label,text in [('control',body),('candidate',candidate)]:
 (W/(label+'-ddiv.S')).write_text(header+setup+'.equ use_hw_div,1\n'+macro+'.section .m0_ddiv_hint_hw,"ax",%progbits\n.p2align 2\n'+text+'\n#endif\n')
(W/'software.S').write_text(header+setup+'.equ use_hw_div,0\n'+macro+'.section .m0_ddiv_hint_sw,"ax",%progbits\n.p2align 2\n'+sw+'\n#endif\n')
(W/'seed17.S').write_bytes((SEED/'seed17.S').read_bytes())
(W/'LICENSE.TXT').write_bytes((ROOT/'third_party/rp2040-softfloat/LICENSE.TXT').read_bytes())
prefix=(BASE/'candidate/native_eabi_m0_pow_root_prefix.inc').read_text()
assert prefix.count('\tbl\t__aeabi_ddiv\n')==1
changed=prefix.replace('\tbl\t__aeabi_ddiv\n','\tbl\tmk61_m0_hint_ddiv\n')
for label in ['control','candidate']:
 d=W/label;d.mkdir(exist_ok=True)
 (d/'native_eabi_m0_rp2040.S').write_bytes((BASE/'candidate/native_eabi_m0_rp2040.S').read_bytes())
 (d/'native_eabi_m0_pow_root_prefix.inc').write_text(changed)
(W/'root-call.patch').write_text(''.join(difflib.unified_diff(prefix.splitlines(True),changed.splitlines(True),fromfile='parent/root-prefix.inc',tofile='candidate/root-prefix.inc')))
(W/'dirty-only.patch').write_text(''.join(difflib.unified_diff(body.splitlines(True),candidate.splitlines(True),fromfile='control/ddiv.S',tofile='candidate/ddiv.S')))
entry=next(e for e in json.loads((P/'build/compile_commands.json').read_bytes())if e['file'].endswith('/code/native_eabi_m0_rp2040.S'))
flags=shlex.split(entry['command']);tc=Path(flags[0]).parent;commands=[]
tree=ast.parse((ROOT/'.build/m0-exp-cached-product-independent-20261024/bind_rebuild.py').read_text())
fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='relocs')
exec(compile(ast.Module(body=[fn],type_ignores=[]),__file__,'exec'),globals())
def run(cmd):subprocess.run(cmd,cwd=W,check=True);commands.append(cmd)
def alloc(e):return {n:(s[1],s[2],s[5],None if s[1]==8 else e.bytes_at(s))for n,s in e.named_sections.items()if s[2]&2 and s[5]}
for context in ['RP','generic_M0','M4_soft','M4_hard']:
 for label in ['control','candidate']:
  cmd=list(flags)
  if context!='RP':cmd=[s for s in cmd if s!='-DMK61_M0_RP2040_EABI=1']
  if context.startswith('M4'):
   cmd[cmd.index('-mcpu=cortex-m0plus')]='-mcpu=cortex-m4';cmd[cmd.index('-DMK61_USE_M0_EABI=1')]='-DMK61_USE_M0_EABI=0'
   if context=='M4_hard':cmd+=['-mfloat-abi=hard','-mfpu=fpv4-sp-d16']
  cmd[cmd.index(entry['file'])]=str(W/label/'native_eabi_m0_rp2040.S');cmd[cmd.index('-o')+1]=str(W/(context+'-'+label+'.o'))
  run(cmd)
 a,b=[ElfImage(W/(context+'-'+label+'.o'))for label in ['control','candidate']]
 assert alloc(a)==alloc(b)and relocs(a)==relocs(b)
 if context=='RP':
  parent=ElfImage(BASE/'RP-candidate.o');aa,bb=alloc(parent),alloc(a)
  assert aa.keys()==bb.keys()and aa==bb # only relocation target changes before link
  ra,rb=relocs(parent),relocs(a)
  changes=[(n,ra.get(n),rb.get(n))for n in aa if ra.get(n)!=rb.get(n)]
  assert len(changes)==1 and changes[0][0]=='.m0_pow_root_prefix'
  pairs=list(zip(ra['.m0_pow_root_prefix'],rb['.m0_pow_root_prefix']))
  delta=[(x,y)for x,y in pairs if x!=y]
  assert len(delta)==1 and delta[0][0][2]=='__aeabi_ddiv'and delta[0][1][2]=='mk61_m0_hint_ddiv'
  call_offset=delta[0][0][0]
for name in ['control-ddiv','candidate-ddiv','software','seed17']:
 run([str(tc/'arm-none-eabi-gcc'),'-mcpu=cortex-m0plus','-mthumb','-DMK61_USE_M0_EABI=1','-DMK61_M0_RP2040_EABI=1','-c',str(W/(name+'.S')),'-o',str(W/(name+'.o'))])
resident=ElfImage(P/'firmware/mk61s-picocalc-pico-h.elf')
kept={'.m0_pow_root_prefix','.m0_pow_boundary_exact','.m0_pow_tail_extra'}
obj=ElfImage(W/'RP-candidate.o');defined=set()
for s in obj.sections:
 if s[1]!=2:continue
 strings=obj.bytes_at(obj.sections[s[6]])
 for n,v,z,info,other,idx in struct.iter_unpack('<IIIBBH',obj.bytes_at(s)):
  if idx<len(obj.sections)and any(obj.sections[idx]==obj.named_sections[k]for k in kept):defined.add(obj.string(strings,n))
defs={n:a for n,a in resident.symbols.items()if re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*',n)and n not in defined}
defs['mk61_m0_boundary128']=0x101e0001
assign=''.join(n+' = '+hex(a)+';\n'for n,a in sorted(defs.items()))
meta={}
for label in ['control','candidate']:
 script=assign+'PHDRS { prefix PT_LOAD FLAGS(5); front PT_LOAD FLAGS(5); tail PT_LOAD FLAGS(5); div PT_LOAD FLAGS(5); }\nSECTIONS {\n'
 script+='.rootprefix 0x1014e668 : { KEEP(*(.m0_pow_root_prefix)) } :prefix\n.front 0x10150000 : { KEEP(*(.m0_pow_boundary_exact)) } :front\n.tail 0x10150280 : { KEEP(*(.m0_pow_tail_extra)) } :tail\n'
 script+='.ddiv 0x101e1000 : { KEEP(*(.m0_ddiv_hint_hw)) KEEP(*(.m0_ddiv_hint_sw)) KEEP(*(.m0_ddiv_seed17)) } :div\n/DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.note*) *(.ARM.attributes) } }\n'
 (W/(label+'.ld')).write_text(script)
 run([str(tc/'arm-none-eabi-ld'),'--gc-sections','-e','mk61_m0_hint_ddiv','-T',str(W/(label+'.ld')),str(W/('RP-'+label+'.o')),str(W/(label+'-ddiv.o')),str(W/'software.o'),str(W/'seed17.o'),'-o',str(W/(label+'.elf'))])
 e=ElfImage(W/(label+'.elf'))
 assert e.symbols['mk61_m0_hint_ddiv']%4==resident.symbols['__aeabi_ddiv']%4
 assert e.named_sections['.ddiv'][3]+e.named_sections['.ddiv'][5]<=0x10200000
 for secname in ['.rootprefix','.tail']:
  s=e.named_sections[secname];old=next(s0 for s0 in resident.named_sections.values()if s0[2]&2 and s0[3]<=s[3]and s[3]+s[5]<=s0[3]+s0[5])
  baseline=resident.bytes_at(old)[s[3]-old[3]:s[3]-old[3]+s[5]];actual=e.bytes_at(s)
  if secname=='.rootprefix':assert actual[:call_offset]==baseline[:call_offset]and actual[call_offset+4:]==baseline[call_offset+4:]
  else:assert actual==baseline
 for n in defined:
  if n in resident.symbols and e.sizes.get(n,0):assert e.symbols[n]==resident.symbols[n],n
 with (W/(label+'.dis')).open('w')as f:subprocess.run([str(tc/'arm-none-eabi-objdump'),'-d',str(W/(label+'.elf'))],stdout=f,check=True)
 meta[label]=dict(ELF_sha256=sha(W/(label+'.elf')),entry=e.symbols['mk61_m0_hint_ddiv'],software=e.symbols['mk61_m0_ddiv_sw_from_guard'],seed=e.symbols['mk61_m0_ddiv_seed17'],allocated={n:dict(address=s[3],bytes=s[5])for n,s in e.named_sections.items()if s[2]&2 and s[5]})
out=dict(status='BUILT_PRIVATE_DIRTY_DIVIDER_SEED_CONTINUATION_NOT_QUALIFIED',images=meta,commands=commands,
 source_parent=str(BASE.relative_to(ROOT)),source_parent_FROZEN_sha256=sha(BASE/'FROZEN.json'),
 exact_seed_proof_sha256=sha(SEED/'seed-proof.json'),root_call_relocation_offset=call_offset,
 only_root_call_changed_in_existing_resident_code=True,default_M0_M4_source_controls_equal=True,
 BSD_existing_kernel_own_seed_no_Qfplib_source_or_new_table_values=True,hardware_accessed=False)
(W/'build.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items()if k!='commands'},indent=2))
