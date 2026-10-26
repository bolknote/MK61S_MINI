"""Generate the R47 source-built candidate from the immutable selected R45."""
from pathlib import Path
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
old=(ROOT/'.build/m0-math-unified-ddiv-boundaries-r46-20261026/build.py').read_text()
head=old[:old.index("p=W/'source/code/native_eabi_m0.cpp'")]
tail=old[old.index('spec=importlib.util.spec_from_file_location'):].replace('r46_fingerprint','r47_fingerprint').replace('R46_DIV_BOUNDARIES','R47_NORMALIZED_DIV').replace('R46 built','R47 built')
edit=r'''cpp_before='      if(e>Bias) return sign|Infinity;\n'
cpp_after=cpp_before+''' + repr('''      // A normalized quotient below the subnormal binade has only one
      // possible nonzero rounding: e=-1075 and exact ratio greater than1.
      if(e<Min-int(F))
        return sign|U(e==Min-int(F)-1 && remainder!=denominator);
''') + r'''
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
'''
assert not(W/'build.py').exists();(W/'build.py').write_text(head+edit+tail);compile((W/'build.py').read_text(),str(W/'build.py'),'exec');print('R47 private build prepared.')
