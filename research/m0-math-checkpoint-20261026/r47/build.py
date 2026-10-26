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
v=v.replace("int(c[start+16]['operands'].split()[0],16)==slow","int(c[start+16]['operands'].split()[0],16)==(e.symbols['mk61_m0_ddiv_numerator_guard_begin']&~1)")
p.write_text(v)
cpp_before='      if(e>Bias) return sign|Infinity;\n'
cpp_after=cpp_before+'      // A normalized quotient below the subnormal binade has only one\n      // possible nonzero rounding: e=-1075 and exact ratio greater than1.\n      if(e<Min-int(F))\n        return sign|U(e==Min-int(F)-1 && remainder!=denominator);\n'
p=W/'source/code/native_eabi_m0.cpp';old=p.read_text();assert old.count(cpp_before)==1;new=old.replace(cpp_before,cpp_after);p.write_text(new)
(W/'underflow-cpp.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='R45/native_eabi_m0.cpp',tofile='R47/native_eabi_m0.cpp')))
p=W/'source/code/native_eabi_m0_rp2040.S';old=p.read_text();new=old
first_before=' cmp r6, r7\n bhi .Lrp2040_div_slow\n subs r6, r5, #1\n'
first_after=first_before.replace('bhi .Lrp2040_div_slow','bhi .Lrp2040_div_num_entry')
assert new.count(first_before)==1;new=new.replace(first_before,first_after)
header_before=""" subs r6, r4, r5
 lsrs r5,r7,#1
 subs r5,#1                    @ 1021
 adds r6,r5
 subs r7,#2                    @ 2043
 cmp r6, r7
 bhi .Lrp2040_div_slow
"""
header_after=""" // Correct the packed subtraction's sign-difference bit, then its
 // arithmetic high20 shift is exactly Ea-Eb-(Ma<Mb).
 mov r4,r1
 eors r4,r3
 lsrs r4,#31
 lsls r4,#31
 mov r12,r4
 mov r6,r1
 cmp r0,r2
 sbcs r6,r3
 eors r6,r4
 asrs r6,#20
 ldr r5,=1022
 adds r6,r5
 cmp r6,r7                    // e+1022 in0..2045 => normal RNE result.
.global mk61_m0_ddiv_range_guard_call
.hidden mk61_m0_ddiv_range_guard_call
mk61_m0_ddiv_range_guard_call:
 bhi .Lrp2040_div_range_slow
 lsls r6,#20
 add r12,r6                   // (e+1022)<<20 plus result sign.
.global mk61_m0_ddiv_normal_range_join
.hidden mk61_m0_ddiv_normal_range_join
mk61_m0_ddiv_normal_range_join:
"""
assert new.count(header_before)==1;new=new.replace(header_before,header_after)
dyadic_before=' cmp r2, #0\n bne 88f\n lsls r7, r3, #15\n bne 88f\n'
dyadic_after=' lsls r7,r3,#15\n orrs r7,r2\n bne 88f\n'
assert new.count(dyadic_before)==1;new=new.replace(dyadic_before,dyadic_after)
small_before=""".Lrp2040_small_divisor:
 // R7 is index<<29; R6 is the guarded biased exponent addend.
 lsls r6,#20
 mov r12,r6
 mov r6,r1
 eors r6,r3
 lsrs r6,#31
 lsls r6,#31
 add r12,r6
"""
small_after=""".Lrp2040_small_divisor:
 // R7 is index<<29; R12 already has the normalized exponent/sign addend.
"""
assert new.count(small_before)==1;new=new.replace(small_before,small_after)
general_before=""".Lrp2040_general_divisor:
 lsls r6,#20
 mov r12,r6
 mov r7,r1
 eors r7,r3
 lsrs r7,#31                  @ result sign
 lsls r7,#31
 add r12,r7                   @ guarded biased exponent and sign
"""
general_after='.Lrp2040_general_divisor:\n'
assert new.count(general_before)==1;new=new.replace(general_before,general_after)
pack_before=""" movs r2,#1
 lsls r2,#20
 add r12,r12,r2                @ fix exponent; r3:r5 now effectively Q61
"""
assert new.count(pack_before)==1;new=new.replace(pack_before,' // Normalized exponent is already packed; r3:r5 effectively Q61.\n')
# Keep the short conditional dyadic branch close to its entry. Every moved
# block ends in an unconditional branch/return; no fall-through enters it.
small_start=new.index('.Lrp2040_small_divisor:\n');small_end=new.index('// Entry only from the second exponent rejection:',small_start)
small=new[small_start:small_end];new=new[:small_start]+new[small_end:]
assert new.count(' regular_func __aeabi_ddiv\n')==1;new=new.replace(' regular_func __aeabi_ddiv\n',small+' regular_func __aeabi_ddiv\n')
num_guard="""// Full exact zero predicate for a subnormal/zero numerator and a
// normal denominator. All declined paths retain R0..R3 unchanged.
.global mk61_m0_ddiv_numerator_guard_body
.hidden mk61_m0_ddiv_numerator_guard_body
mk61_m0_ddiv_numerator_guard_body:
.Lrp2040_div_num_body:
 bpl .Lrp2040_div_slow
 subs r6,r5,#1
 cmp r6,r7
 bhi .Lrp2040_div_slow
 ldr r7,=1076
 subs r7,r5
 ble .Lrp2040_div_num_zero
 cmp r7,#53
 bhi .Lrp2040_div_slow
 // N<=floor(M/2^k), k=1076-Eb, is exactly |a/b|<=2^-1075.
 lsls r5,r3,#12
 lsrs r5,r5,#12
 movs r6,#1
 lsls r6,#20
 orrs r5,r6
 cmp r7,#32
 bhs .Lrp2040_div_num_shift_high
 mov r6,r2
 lsrs r6,r7
 mov r4,r5
 lsrs r5,r7
 negs r7,r7
 adds r7,#32
 lsls r4,r7
 orrs r6,r4
 b .Lrp2040_div_num_compare
.Lrp2040_div_num_shift_high:
 subs r7,#32
 mov r6,r5
 lsrs r6,r7
 movs r5,#0
.Lrp2040_div_num_compare:
 lsls r4,r1,#12
 lsrs r4,r4,#12
 cmp r4,r5
 bhi .Lrp2040_div_slow
 blo .Lrp2040_div_num_zero
 cmp r0,r6
 bhi .Lrp2040_div_slow
.Lrp2040_div_num_zero:
 eors r1,r3
 lsrs r1,r1,#31
 lsls r1,r1,#31
 movs r0,#0
 pop {r4-r7,pc}
.global mk61_m0_ddiv_numerator_guard_end
.hidden mk61_m0_ddiv_numerator_guard_end
mk61_m0_ddiv_numerator_guard_end:
.global mk61_m0_ddiv_numerator_guard_begin
.hidden mk61_m0_ddiv_numerator_guard_begin
mk61_m0_ddiv_numerator_guard_begin:
.Lrp2040_div_num_entry:
 b .Lrp2040_div_num_body

"""
assert new.count('// Entry only from the second exponent rejection:')==1;new=new.replace('// Entry only from the second exponent rejection:',num_guard+'// Entry only from the second exponent rejection:')
range_guard="""// R6=e+1022, R12=sign only. Finite normal operands are already known.
.global mk61_m0_ddiv_range_guard_begin
.hidden mk61_m0_ddiv_range_guard_begin
mk61_m0_ddiv_range_guard_begin:
.Lrp2040_div_range_slow:
 bpl .Lrp2040_div_den_overflow
 movs r7,#53
 negs r7,r7
 cmp r6,r7
 blt .Lrp2040_div_range_zero
 bne .Lrp2040_div_slow
 // e=-1075: the normalized ratio equals1 iff the mantissas equal.
 mov r4,r0
 eors r4,r2
 lsls r5,r1,#12
 lsls r7,r3,#12
 eors r5,r7
 orrs r4,r5
 beq .Lrp2040_div_range_zero
 movs r0,#1
 mov r1,r12
 pop {r4-r7,pc}
.Lrp2040_div_range_zero:
 movs r0,#0
 mov r1,r12
 pop {r4-r7,pc}
.global mk61_m0_ddiv_range_guard_end
.hidden mk61_m0_ddiv_range_guard_end
mk61_m0_ddiv_range_guard_end:

"""
assert new.count('.Lrp2040_div_slow:\n')==1;new=new.replace('.Lrp2040_div_slow:\n',range_guard+'.Lrp2040_div_slow:\n');p.write_text(new)
edits=dict(cpp_before=cpp_before,cpp_after=cpp_after,first_before=first_before,first_after=first_after,header_before=header_before,header_after=header_after,dyadic_before=dyadic_before,dyadic_after=dyadic_after,small_before=small_before,small_after=small_after,general_before=general_before,general_after=general_after,pack_before=pack_before,small_block=small,num_guard=num_guard,range_guard=range_guard)
(W/'source-edits.json').write_text(json.dumps(edits,indent=2)+'\n')
(W/'normalized-div-asm.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='R45/native_eabi_m0_rp2040.S',tofile='R47/native_eabi_m0_rp2040.S')))
spec=importlib.util.spec_from_file_location('r47_fingerprint',ROOT/'research/m0-math-checkpoint-20261025-5/verify.py');fp=importlib.util.module_from_spec(spec);spec.loader.exec_module(fp)
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
result=dict(status='BUILT_R47_NORMALIZED_DIV_PENDING_PROOF_TESTS',images=images,commands=commands,outputs=outputs,parent_source_FROZEN_sha256=sha(P/'FROZEN.json'),unchanged_objects=unchanged,changed_allocated_sections=changed,all17_other_objects_M4default_exact=True,default_M0_M4_objects_exact=True,new_lookup_tables_RAM_libgcc_bytes=0,hardware_accessed=False,integration_GO=False,goal_complete=False)
(W/'link-result.json').write_text(json.dumps(result,indent=2)+'\n');print('R47 built',images['candidate'],'changed',changed,'unchanged',len(unchanged),flush=True)
