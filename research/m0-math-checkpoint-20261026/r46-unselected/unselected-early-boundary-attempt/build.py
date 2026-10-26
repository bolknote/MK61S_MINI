"""Private R46: exact normal-range admission and certain underflow shortcuts."""
from pathlib import Path
import ast,difflib,hashlib,importlib.util,json,shutil,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-math-unified-ddiv-cold-overflow-r45-20261026'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(P/'FROZEN.json')=='dbc455078837507acaeb750df1e3fb6800b923e2a9a880c9c6bcc2150ba3527a'
frozen=json.loads((P/'FROZEN.json').read_bytes())
for n,r in frozen['files'].items():
    p=P/n;assert p.stat().st_size==r['bytes'] and sha(p)==r['sha256'],n
assert not(W/'source').exists()
for n in ['source','timing-control']:shutil.copytree(P/n,W/n)
for n in ['unified.ld','harness.py','verify-private-return.py','verify-guard-controls.py','verify-loader.py','verify-disabled.py','run-controls.py','verify-private-caller.py','verify-normalized-caller.py','verify-native-caller.py','helper.S.inc','verify-div-guard.py']:
    shutil.copyfile(P/n,W/n)
# The old denominator guard is retained exactly, including its actual flags.
p=W/'verify-div-guard.py';v=p.read_text();v=v.replace("(W/'build.py').read_text()",f"(ROOT/{str(P.relative_to(ROOT))!r}/'build.py').read_text()")
p.write_text(v)
p=W/'source/code/native_eabi_m0.cpp';old=p.read_text()
before='      if(e>Bias) return sign|Infinity;\n'
after=before+'''      // Below the least-subnormal binade, only the exact half-way case
      // needs distinction: half rounds to zero; any greater ratio to one.
      if(e<Min-int(F))
        return sign|U(e==Min-int(F)-1 && remainder!=denominator);
'''
assert old.count(before)==1;new=old.replace(before,after);p.write_text(new)
(W/'underflow-cpp.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='R45/native_eabi_m0.cpp',tofile='R46/native_eabi_m0.cpp')))
p=W/'source/code/native_eabi_m0_rp2040.S';old=p.read_text()
before=''' subs r7,#2                    @ 2043
 cmp r6, r7
 bhi .Lrp2040_div_slow
 // Dyadic mantissas'''
after=''' subs r7,#1                    @ 2044: all quotients remain normal
 cmp r6, r7
.global mk61_m0_ddiv_range_guard_call
.hidden mk61_m0_ddiv_range_guard_call
mk61_m0_ddiv_range_guard_call:
 bhi .Lrp2040_div_range_slow
.global mk61_m0_ddiv_normal_range_join
.hidden mk61_m0_ddiv_normal_range_join
mk61_m0_ddiv_normal_range_join:
.Lrp2040_div_range_join:
 // Dyadic mantissas'''
assert old.count(before)==1;new=old.replace(before,after)
range_guard='''// Both operands normal; R6=Ea-Eb+1021; R7=2044. The unsigned
// CMP rejection distinguishes negative R6 by N=1 from R6>=2045 by N=0.
.global mk61_m0_ddiv_range_guard_begin
.hidden mk61_m0_ddiv_range_guard_begin
mk61_m0_ddiv_range_guard_begin:
.Lrp2040_div_range_slow:
 bpl .Lrp2040_div_range_upper
 adds r7,r6,#1
 beq .Lrp2040_div_range_lower
 movs r7,#55
 negs r7,r7
 cmp r6,r7
 ble .Lrp2040_div_range_zero
 b .Lrp2040_div_slow
.Lrp2040_div_range_upper:
 adds r7,#1                    // 2045; larger implies exponent>=1024.
 cmp r6,r7
 bhi .Lrp2040_div_den_overflow
 // R6=2045: ratio below1 has normalized exponent1023.
 lsls r4,r1,#12
 lsls r5,r3,#12
 cmp r4,r5
 bne .Lrp2040_div_range_upper_cmp
 cmp r0,r2
.Lrp2040_div_range_upper_cmp:
 blo .Lrp2040_div_range_join
 b .Lrp2040_div_den_overflow
.Lrp2040_div_range_lower:
 // R6=-1: ratio at least1 has normalized exponent-1022.
 lsls r4,r1,#12
 lsls r5,r3,#12
 cmp r4,r5
 bne .Lrp2040_div_range_lower_cmp
 cmp r0,r2
.Lrp2040_div_range_lower_cmp:
 blo .Lrp2040_div_slow
 b .Lrp2040_div_range_join
.Lrp2040_div_range_zero:
 // R6<=-55 means Ea-Eb<=-1076 and exact |a/b|<2^-1075.
 eors r1,r3
 lsrs r1,r1,#31
 lsls r1,r1,#31
 movs r0,#0
 pop {r4-r7,pc}
.global mk61_m0_ddiv_range_guard_end
.hidden mk61_m0_ddiv_range_guard_end
mk61_m0_ddiv_range_guard_end:

'''
assert new.count('.Lrp2040_small_divisor:\n')==1
new=new.replace('.Lrp2040_small_divisor:\n',range_guard+'.Lrp2040_small_divisor:\n');p.write_text(new)
(W/'normal-range-asm.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='R45/native_eabi_m0_rp2040.S',tofile='R46/native_eabi_m0_rp2040.S')))
(W/'range-guard-source.txt').write_text(range_guard)
spec=importlib.util.spec_from_file_location('r46_fingerprint',ROOT/'research/m0-math-checkpoint-20261025-5/verify.py');fp=importlib.util.module_from_spec(spec);spec.loader.exec_module(fp)
parent=json.loads((P/'link-result.json').read_bytes());commands=[];outputs={};unchanged=[];changed={}
allowed={'RP-merged-cpp.o':['.text._ZN7m0_eabi6BinaryILj52ELj11EE3divEyy'],'RP-unified-native_eabi_m0_rp2040.S.o':['.text.mk61_rp2040_arithmetic']}
for recorded in parent['commands']:
    command=[v.replace(str(P)+'/',str(W)+'/')for v in recorded];subprocess.run(command,cwd=W,check=True);commands.append(command)
    out=Path(command[command.index('-o')+1]);current=fp.image_fingerprint(out.read_bytes());outputs[out.name]=dict(sha256=sha(out),fingerprint=current)
    if '-c'not in command:continue
    previous=fp.image_fingerprint((P/out.name).read_bytes())
    if out.name not in allowed:assert current==previous,out.name;unchanged.append(out.name);continue
    a,b=[{r[0]:r for r in v['allocated']}for v in [current,previous]];diff=[n for n in sorted(a.keys()|b.keys())if a.get(n)!=b.get(n)];assert diff==allowed[out.name],diff
    assert[r for r in current['symbols']if r[-1]not in diff]==[r for r in previous['symbols']if r[-1]not in diff]
    assert[r for r in current['relocations']if r[0]not in diff]==[r for r in previous['relocations']if r[0]not in diff];changed[out.name]=diff
assert len(unchanged)==17 and changed==allowed
sys.path.insert(0,str(ROOT/'tests'));from check_stm32_vectors import ElfImage
tc=Path(commands[0][0]).parent;images={}
for label in ['candidate','zero-control']:
    p=W/(label+'.elf');e=ElfImage(p);assert not subprocess.check_output([str(tc/'arm-none-eabi-nm'),'-u',str(p)])
    assert e.named_sections['.scratch_y'][5]==4080 and e.sizes['mk61_m0_div_seed_table']==256 and e.sizes['mk61_m0_public_div_seed8_table']==32
    images[label]=dict(ELF_sha256=sha(p),scratch_y_bytes=4080,all_undefined_symbols_resolved=True)
    with(W/(label+'.dis')).open('w')as f:subprocess.run([str(tc/'arm-none-eabi-objdump'),'-dr',str(p)],stdout=f,check=True)
result=dict(status='BUILT_R46_DIV_BOUNDARIES_PENDING_PROOF_TESTS',images=images,commands=commands,outputs=outputs,parent_source_FROZEN_sha256=sha(P/'FROZEN.json'),unchanged_objects=unchanged,changed_allocated_sections=changed,all17_other_objects_M4default_exact=True,default_M0_M4_objects_exact=True,new_lookup_tables_RAM_libgcc_bytes=0,hardware_accessed=False,integration_GO=False,goal_complete=False)
(W/'link-result.json').write_text(json.dumps(result,indent=2)+'\n');print('R46 built',images['candidate'],'changed',changed,'unchanged',len(unchanged),flush=True)
