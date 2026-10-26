"""Compose the checked CPP guard with an exact pre-normalization denominator guard."""
from pathlib import Path
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-math-unified-ddiv-overflow-r44-20261026'
old=(P/'build.py').read_text();head=old[:old.index("before='''")];tail=old[old.index('spec=importlib.util.spec_from_file_location'):]
head=head.replace('m0-math-unified-pow-rsqrt-nativeq8-r43-20261026','m0-math-unified-ddiv-overflow-r44-20261026').replace('170cd77a62244459c526ea2817f964652f4355c31e7824defc7b0195a6a5b22b','ac14437a770763e7c46d8782a7f02506ecfcc3b0c2b598c5476e1d29324dfb3a')
tail=tail.replace('r44_fingerprint','r45_fingerprint').replace("allowed=['.text._ZN7m0_eabi6BinaryILj52ELj11EE3divEyy']","allowed=['.text.mk61_rp2040_arithmetic']").replace("'RP-merged-cpp.o'","'RP-unified-native_eabi_m0_rp2040.S.o'").replace('BUILT_R44_EARLY_DIV_OVERFLOW_PENDING_PROOF_TESTS','BUILT_R45_COLD_DIV_OVERFLOW_PENDING_PROOF_TESTS').replace('R44 built','R45 built')
edit=r'''before=""" subs r6, r5, #1
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
'''
assert not(W/'build.py').exists();(W/'build.py').write_text(head+edit+tail);compile((W/'build.py').read_text(),str(W/'build.py'),'exec');print('R45 composed private build prepared.')
