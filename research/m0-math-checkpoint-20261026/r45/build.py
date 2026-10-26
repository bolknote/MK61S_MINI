"""Private R44: reject certain binary64 quotient overflow before mantissa division."""
from pathlib import Path
import difflib,hashlib,importlib.util,json,shutil,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-math-unified-ddiv-overflow-r44-20261026'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(P/'FROZEN.json')=='ac14437a770763e7c46d8782a7f02506ecfcc3b0c2b598c5476e1d29324dfb3a'
assert not(W/'source').exists()
shutil.copytree(P/'source',W/'source');shutil.copytree(P/'timing-control',W/'timing-control')
for n in ['unified.ld','harness.py','verify-private-return.py','verify-guard-controls.py','verify-loader.py','verify-disabled.py','run-controls.py','verify-private-caller.py','verify-normalized-caller.py','verify-native-caller.py','helper.S.inc']:
    shutil.copyfile(P/n,W/n)
before=""" subs r6, r5, #1
 cmp r6, r7
 bhi .Lrp2040_div_slow
"""
after=""" subs r6, r5, #1
 cmp r6, r7
.global mk61_m0_ddiv_denominator_guard_call
.hidden mk61_m0_ddiv_denominator_guard_call
mk61_m0_ddiv_denominator_guard_call:
 bhi .Lrp2040_div_den_slow
"""
guard="""// Entry only from the second exponent rejection: numerator normal;
// CMP(Eb-1),2045 has N=1 for Eb0 and N=0 for Eb2047.
.global mk61_m0_ddiv_denominator_guard_begin
.hidden mk61_m0_ddiv_denominator_guard_begin
mk61_m0_ddiv_denominator_guard_begin:
.Lrp2040_div_den_slow:
 bpl .Lrp2040_div_slow
 // A normal finite numerator divided by signed zero is signed infinity.
 lsls r5,r3,#12
 orrs r5,r2
 beq .Lrp2040_div_den_overflow
 ldr r6,=1025
 subs r7,r6,r4             // k=1025-Ea
 ble .Lrp2040_div_den_overflow
 cmp r7,#53
 bhs .Lrp2040_div_slow
 // 1<=k<=52. Let M be the exact53-bit numerator significand;
 // denominator N is a subnormal coefficient. N<=M>>k implies
 // |a/b|>=2^1024. Retain all argument registers on every decline.
 lsls r5,r1,#12
 lsrs r5,r5,#12
 movs r6,#1
 lsls r6,r6,#20
 orrs r5,r6
 cmp r7,#32
 bhs .Lrp2040_div_den_shift_high
 mov r6,r0
 lsrs r6,r7
 mov r4,r5
 lsrs r5,r7
 negs r7,r7
 adds r7,#32
 lsls r4,r7
 orrs r6,r4
 b .Lrp2040_div_den_compare
.Lrp2040_div_den_shift_high:
 subs r7,#32
 mov r6,r5
 lsrs r6,r7
 movs r5,#0
.Lrp2040_div_den_compare:
 lsls r4,r3,#12
 lsrs r4,r4,#12
 cmp r4,r5
 bhi .Lrp2040_div_slow
 blo .Lrp2040_div_den_overflow
 cmp r2,r6
 bhi .Lrp2040_div_slow
.Lrp2040_div_den_overflow:
 eors r1,r3
 lsrs r1,r1,#31
 lsls r1,r1,#31
 ldr r0,=0x7ff00000
 orrs r1,r0
 movs r0,#0
 pop {r4-r7,pc}
.global mk61_m0_ddiv_denominator_guard_end
.hidden mk61_m0_ddiv_denominator_guard_end
mk61_m0_ddiv_denominator_guard_end:
 .ltorg

"""
p=W/'source/code/native_eabi_m0_rp2040.S';src=p.read_text();assert src.count(before)==1 and src.count('.Lrp2040_div_slow:\n')==1
new=src.replace(before,after).replace('.Lrp2040_div_slow:\n',guard+'.Lrp2040_div_slow:\n');p.write_text(new)
(W/'cold-den-overflow.patch').write_text(''.join(difflib.unified_diff(src.splitlines(True),new.splitlines(True),fromfile='R44/native_eabi_m0_rp2040.S',tofile='R45/native_eabi_m0_rp2040.S')))
spec=importlib.util.spec_from_file_location('r45_fingerprint',ROOT/'research/m0-math-checkpoint-20261025-5/verify.py');fp=importlib.util.module_from_spec(spec);spec.loader.exec_module(fp)
parent=json.loads((P/'link-result.json').read_bytes());commands=[];outputs={};unchanged=[];changed={}
allowed=['.text.mk61_rp2040_arithmetic']
for recorded in parent['commands']:
    command=[v.replace(str(P)+'/',str(W)+'/')for v in recorded];subprocess.run(command,cwd=W,check=True);commands.append(command)
    out=Path(command[command.index('-o')+1]);current=fp.image_fingerprint(out.read_bytes());outputs[out.name]=dict(sha256=sha(out),fingerprint=current)
    if '-c'not in command:continue
    previous=fp.image_fingerprint((P/out.name).read_bytes())
    if out.name!='RP-unified-native_eabi_m0_rp2040.S.o':assert current==previous,out.name;unchanged.append(out.name);continue
    a,b=[{r[0]:r for r in v['allocated']}for v in [current,previous]];diff=[n for n in sorted(a.keys()|b.keys())if a.get(n)!=b.get(n)];assert diff==allowed,diff
    assert[r for r in current['symbols']if r[-1]not in diff]==[r for r in previous['symbols']if r[-1]not in diff]
    assert[r for r in current['relocations']if r[0]not in diff]==[r for r in previous['relocations']if r[0]not in diff];changed[out.name]=diff
assert len(unchanged)==18 and changed=={'RP-unified-native_eabi_m0_rp2040.S.o':allowed}
sys.path.insert(0,str(ROOT/'tests'));from check_stm32_vectors import ElfImage
tc=Path(commands[0][0]).parent;images={}
for label in ['candidate','zero-control']:
    p=W/(label+'.elf');e=ElfImage(p);assert not subprocess.check_output([str(tc/'arm-none-eabi-nm'),'-u',str(p)])
    assert e.named_sections['.scratch_y'][5]==4080 and e.sizes['mk61_m0_div_seed_table']==256 and e.sizes['mk61_m0_public_div_seed8_table']==32
    images[label]=dict(ELF_sha256=sha(p),scratch_y_bytes=4080,all_undefined_symbols_resolved=True)
    with(W/(label+'.dis')).open('w')as f:subprocess.run([str(tc/'arm-none-eabi-objdump'),'-dr',str(p)],stdout=f,check=True)
result=dict(status='BUILT_R45_COLD_DIV_OVERFLOW_PENDING_PROOF_TESTS',images=images,commands=commands,outputs=outputs,parent_source_FROZEN_sha256=sha(P/'FROZEN.json'),unchanged_objects=unchanged,changed_allocated_sections=changed,all18_other_objects_including_full_RPASM_M4default_exact=True,default_M0_M4_objects_exact=True,new_lookup_tables_RAM_libgcc_bytes=0,hardware_accessed=False,integration_GO=False,goal_complete=False)
(W/'link-result.json').write_text(json.dumps(result,indent=2)+'\n');print('R45 built',images['candidate'],'changed',changed,'unchanged',len(unchanged),flush=True)
