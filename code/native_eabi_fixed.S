/* Cortex-M4 little-endian binary64 primitives. Derived from GCC 14.2.0
 * libgcc/config/arm/{lib1funcs,ieee754-df}.S, GPL-3.0-or-later WITH
 * GCC-exception-3.1. Full copyright/license notices are preserved below;
 * the exception is in GCC_RUNTIME_EXCEPTION.txt, GPL text in ../LICENSE.
 * Fixed Thumb-2 configuration: no architecture dispatcher or VFP double.
 * Integer reciprocal division and u64 divmod are maintained separately.
 */
#if defined(MK61_NATIVE_RUNTIME) && MK61_NATIVE_RUNTIME && MK61_USE_NATIVE_EABI
.cpu cortex-m4
.thumb
@ libgcc routines for ARM cpu.
@ Division routines, written by Richard Earnshaw, (rearnsha@armltd.co.uk)
/* Copyright (C) 1995-2024 Free Software Foundation, Inc.

This file is free software; you can redistribute it and/or modify it
under the terms of the GNU General Public License as published by the
Free Software Foundation; either version 3, or (at your option) any
later version.

This file is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
General Public License for more details.

Under Section 7 of GPL version 3, you are granted additional
permissions described in the GCC Runtime Library Exception, version
3.1, as published by the Free Software Foundation.

You should have received a copy of the GNU General Public License and
a copy of the GCC Runtime Library Exception along with this program;
see the files COPYING3 and COPYING.RUNTIME respectively.  If not, see
<http://www.gnu.org/licenses/>.  */
/* Everything in this file should now use unified syntax.  */
 .syntax unified
/* An executable stack is *not* required for these functions.  */
/* Some attributes that are common to all routines in this file.  */
 /* Tag_ABI_align_needed: This code does not require 8-byte
	   alignment from the caller.  */
 /* .eabi_attribute 24, 0  -- default setting.  */
 /* Tag_ABI_align_preserved: This code preserves 8-byte
	   alignment in any callee.  */
 .eabi_attribute 25, 1
/* ------------------------------------------------------------------------ */
/* We need to know what prefix to add to function names.  */
/* ANSI concatenation macros.  */
/* Use the right prefix for global labels.  */
/* Function end macros.  Variants for interworking.  */
/* There are times when we might prefer Thumb1 code even if ARM code is
   permitted, for example, the code might be smaller, or there might be
   interworking problems with switching to ARM state if interworking is
   disabled.  */
/* How to return from a function call depends on the architecture variant.  */
/* Special precautions for interworking on armv4t.  */
.macro cfi_pop advance, reg, cfa_offset
 .pushsection .debug_frame
 .byte 0x4 /* DW_CFA_advance_loc4 */
 .4byte \advance
 .byte (0xc0 | \reg) /* DW_CFA_restore */
 .byte 0xe /* DW_CFA_def_cfa_offset */
 .uleb128 \cfa_offset
 .popsection
.endm
.macro cfi_push advance, reg, offset, cfa_offset
 .pushsection .debug_frame
 .byte 0x4 /* DW_CFA_advance_loc4 */
 .4byte \advance
 .byte (0x80 | \reg) /* DW_CFA_offset */
 .uleb128 (\offset / -4)
 .byte 0xe /* DW_CFA_def_cfa_offset */
 .uleb128 \cfa_offset
 .popsection
.endm
.macro cfi_start start_label, end_label
 .pushsection .debug_frame
.Lstart_frame:
 .4byte .Lend_cie - .Lstart_cie @ Length of CIE
.Lstart_cie:
        .4byte 0xffffffff @ CIE Identifier Tag
        .byte 0x1 @ CIE Version
        .ascii "\0" @ CIE Augmentation
        .uleb128 0x1 @ CIE Code Alignment Factor
        .sleb128 -4 @ CIE Data Alignment Factor
        .byte 0xe @ CIE RA Column
        .byte 0xc @ DW_CFA_def_cfa
        .uleb128 0xd
        .uleb128 0x0
 .align 2
.Lend_cie:
 .4byte .Lend_fde-.Lstart_fde @ FDE Length
.Lstart_fde:
 .4byte .Lstart_frame @ FDE CIE offset
 .4byte \start_label @ FDE initial location
 .4byte \end_label-\start_label @ FDE address range
 .popsection
.endm
.macro cfi_end end_label
 .pushsection .debug_frame
 .align 2
.Lend_fde:
 .popsection
\end_label:
.endm
/* Don't pass dirn, it's there just to get token pasting right.  */
.macro RETLDM regs=, cond=, unwind=, dirn=ia
 /* Caller is responsible for providing IT instruction.  */
 .ifc "\regs",""
 ldr\cond pc, [sp], #8
 .else
 pop\cond {\regs, pc}
 .endif
.endm
/* The Unified assembly syntax allows the same code to be assembled for both
   ARM and Thumb-2.  However this is only supported by recent gas, so define
   a set of macros to allow ARM code on older assemblers.  */
.macro do_it cond, suffix=""
 it\suffix \cond
.endm
.macro shift1 op, arg0, arg1, arg2
 \op \arg0, \arg1, \arg2
.endm
/* Perform an arithmetic operation with a variable shift operand.  This
   requires two instructions and a scratch register on Thumb-2.  */
.macro shiftop name, dest, src1, src2, shiftop, shiftreg, tmp
 \shiftop \tmp, \src2, \shiftreg
 \name \dest, \src1, \tmp
.endm
.macro ARM_LDIV0 name signed
 cmp r0, #0
 .ifc \signed, unsigned
 movne r0, #0xffffffff
 .else
 movgt r0, #0x7fffffff
 movlt r0, #0x80000000
 .endif
 b __aeabi_idiv0
.endm
.macro THUMB_LDIV0 name signed
 .syntax unified
 .ifc \signed, unsigned
 cbz r0, 1f
 mov r0, #0xffffffff
1:
 .else
 cmp r0, #0
 do_it gt
 movgt r0, #0x7fffffff
 do_it lt
 movlt r0, #0x80000000
 .endif
 b.w __aeabi_idiv0
.endm
.macro FUNC_END name
 .size __\name, . - __\name
.endm
.macro DIV_FUNC_END name signed
 cfi_start __\name, .Lend_div0
.Ldiv0:
 THUMB_LDIV0 \name \signed
 cfi_end .Lend_div0
 FUNC_END \name
.endm
.macro THUMB_FUNC_START name
 .globl \name
 .type \name,function
 .thumb_func
\name:
.endm
/* Function start macros.  Variants for ARM and Thumb.  */
.macro FUNC_START name
 .section .text.mk61_eabi_fixed,"ax",%progbits
 .globl __\name
 .type __\name,function
 .align 0
 .force_thumb
 .thumb_func

__\name:
.endm
.macro ARM_SYM_START name
       .type \name,function
       .align 0
\name:
.endm
.macro SYM_END name
       .size \name, . - \name
.endm
/* Special function that will always be coded in ARM assembly, even if
   in Thumb-only compilation.  */
/* For Thumb-2 we build everything in thumb mode.  */
.macro ARM_FUNC_START name
       FUNC_START \name
       .syntax unified
.endm
.macro ARM_CALL name
 bl __\name
.endm
.macro FUNC_ALIAS new old
 .globl __\new
 .thumb_set __\new, __\old
.endm
.macro ARM_FUNC_ALIAS new old
 .globl __\new
 .thumb_set __\new, __\old
.endm
.macro WEAK name
 .weak __\name
.endm
/* Register aliases.  */
work .req r4 @ XXXX is this safe ?
dividend .req r0
divisor .req r1
overdone .req r2
result .req r2
curbit .req r3
/* ------------------------------------------------------------------------ */
/*		Bodies of the division and modulo routines.		    */
/* ------------------------------------------------------------------------ */
.macro ARM_DIV_BODY dividend, divisor, result, curbit
 clz \curbit, \dividend
 clz \result, \divisor
 sub \curbit, \result, \curbit
 rsb \curbit, \curbit, #31
 adr \result, 1f
 add \curbit, \result, \curbit, lsl #4
 mov \result, #0
 mov pc, \curbit
.p2align 3
1:
 .set shift, 32
 .rept 32
 .set shift, shift - 1
 cmp.w \dividend, \divisor, lsl #shift
 nop.n
 adc.w \result, \result, \result
 it cs
 subcs.w \dividend, \dividend, \divisor, lsl #shift
 .endr
.endm
/* ------------------------------------------------------------------------ */
.macro ARM_DIV2_ORDER divisor, order
 clz \order, \divisor
 rsb \order, \order, #31
.endm
/* ------------------------------------------------------------------------ */
.macro ARM_MOD_BODY dividend, divisor, order, spare
 clz \order, \divisor
 clz \spare, \dividend
 sub \order, \order, \spare
 rsbs \order, \order, #31
 addne pc, pc, \order, lsl #3
 nop
 .set shift, 32
 .rept 32
 .set shift, shift - 1
 cmp \dividend, \divisor, lsl #shift
 subcs \dividend, \dividend, \divisor, lsl #shift
 .endr
.endm
/* ------------------------------------------------------------------------ */
.macro THUMB_DIV_MOD_BODY modulo
 @ Load the constant 0x10000000 into our work register.
 movs work, #1
 lsls work, #28
.Loop1:
 @ Unless the divisor is very big, shift it up in multiples of
 @ four bits, since this is the amount of unwinding in the main
 @ division loop. Continue shifting until the divisor is
 @ larger than the dividend.
 cmp divisor, work
 bhs .Lbignum
 cmp divisor, dividend
 bhs .Lbignum
 lsls divisor, #4
 lsls curbit, #4
 b .Loop1
.Lbignum:
 @ Set work to 0x80000000
 lsls work, #3
.Loop2:
 @ For very big divisors, we must shift it a bit at a time, or
 @ we will be in danger of overflowing.
 cmp divisor, work
 bhs .Loop3
 cmp divisor, dividend
 bhs .Loop3
 lsls divisor, #1
 lsls curbit, #1
 b .Loop2
.Loop3:
 @ Test for possible subtractions ...
  .if \modulo
 @ ... On the final pass, this may subtract too much from the dividend,
 @ so keep track of which subtractions are done, we can fix them up
 @ afterwards.
 movs overdone, #0
 cmp dividend, divisor
 blo .Lover1
 subs dividend, dividend, divisor
.Lover1:
 lsrs work, divisor, #1
 cmp dividend, work
 blo .Lover2
 subs dividend, dividend, work
 mov ip, curbit
 movs work, #1
 rors curbit, work
 orrs overdone, curbit
 mov curbit, ip
.Lover2:
 lsrs work, divisor, #2
 cmp dividend, work
 blo .Lover3
 subs dividend, dividend, work
 mov ip, curbit
 movs work, #2
 rors curbit, work
 orrs overdone, curbit
 mov curbit, ip
.Lover3:
 lsrs work, divisor, #3
 cmp dividend, work
 blo .Lover4
 subs dividend, dividend, work
 mov ip, curbit
 movs work, #3
 rors curbit, work
 orrs overdone, curbit
 mov curbit, ip
.Lover4:
 mov ip, curbit
  .else
 @ ... and note which bits are done in the result. On the final pass,
 @ this may subtract too much from the dividend, but the result will be ok,
 @ since the "bit" will have been shifted out at the bottom.
 cmp dividend, divisor
 blo .Lover1
 subs dividend, dividend, divisor
 orrs result, result, curbit
.Lover1:
 lsrs work, divisor, #1
 cmp dividend, work
 blo .Lover2
 subs dividend, dividend, work
 lsrs work, curbit, #1
 orrs result, work
.Lover2:
 lsrs work, divisor, #2
 cmp dividend, work
 blo .Lover3
 subs dividend, dividend, work
 lsrs work, curbit, #2
 orrs result, work
.Lover3:
 lsrs work, divisor, #3
 cmp dividend, work
 blo .Lover4
 subs dividend, dividend, work
 lsrs work, curbit, #3
 orrs result, work
.Lover4:
  .endif
 cmp dividend, #0 @ Early termination?
 beq .Lover5
 lsrs curbit, #4 @ No, any more bits to do?
 beq .Lover5
 lsrs divisor, #4
 b .Loop3
.Lover5:
  .if \modulo
 @ Any subtractions that we should not have done will be recorded in
 @ the top three bits of "overdone". Exactly which were not needed
 @ are governed by the position of the bit, stored in ip.
 movs work, #0xe
 lsls work, #28
 ands overdone, work
 beq .Lgot_result
 @ If we terminated early, because dividend became zero, then the
 @ bit in ip will not be in the bottom nibble, and we should not
 @ perform the additions below. We must test for this though
 @ (rather relying upon the TSTs to prevent the additions) since
 @ the bit in ip could be in the top two bits which might then match
 @ with one of the smaller RORs.
 mov curbit, ip
 movs work, #0x7
 tst curbit, work
 beq .Lgot_result
 mov curbit, ip
 movs work, #3
 rors curbit, work
 tst overdone, curbit
 beq .Lover6
 lsrs work, divisor, #3
 adds dividend, work
.Lover6:
 mov curbit, ip
 movs work, #2
 rors curbit, work
 tst overdone, curbit
 beq .Lover7
 lsrs work, divisor, #2
 adds dividend, work
.Lover7:
 mov curbit, ip
 movs work, #1
 rors curbit, work
 tst overdone, curbit
 beq .Lgot_result
 lsrs work, divisor, #1
 adds dividend, work
  .endif
.Lgot_result:
.endm
/* If performance is preferred, the following functions are provided.  */
/* ------------------------------------------------------------------------ */
/*		Start of the Real Functions				    */
/* ------------------------------------------------------------------------ */
/* ------------------------------------------------------------------------ */
/* ------------------------------------------------------------------------ */
/* ------------------------------------------------------------------------ */
/* ------------------------------------------------------------------------ */
/* ------------------------------------------------------------------------ */
/* ------------------------------------------------------------------------ */
/* Dword shift operations.  */
/* All the following Dword shift variants rely on the fact that
	shft xxx, Reg
   is in fact done as
	shft xxx, (Reg & 255)
   so for Reg value in (32...63) and (-1...-31) we will get zero (in the
   case of logical shifts) or the sign (for asr).  */
/* Prevent __aeabi double-word shifts from being produced on SymbianOS.  */
/* ------------------------------------------------------------------------ */
/* These next two sections are here despite the fact that they contain Thumb
   assembler because their presence allows interworked code to be linked even
   when the GCC library is this one.  */
/* Do not build the interworking functions when the target architecture does
   not support Thumb instructions.  (This can be a multilib option).  */
/* Don't bother with the old interworking routines for Thumb-2.  */
/* ??? Maybe only omit these on "m" variants.  */
/* Functions to support compact pic switch tables in thumb1 state.
   All these routines take an index into the table in r0.  The
   table is at LR & ~1 (but this must be rounded up in the case
   of 32-bit entires).  They are only permitted to clobber r12
   and r14 and r0 must be preserved on exit.  */
.macro CFI_START_FUNCTION
 .cfi_startproc
 .cfi_remember_state
.endm
.macro CFI_END_FUNCTION
 .cfi_restore_state
 .cfi_endproc
.endm
/* The condition here must match the one in gcc/config/arm/elf.h and
   libgcc/config/arm/t-elf.  */
/* ieee754-df.S double-precision floating point support for ARM

   Copyright (C) 2003-2024 Free Software Foundation, Inc.
   Contributed by Nicolas Pitre (nico@fluxnic.net)

   This file is free software; you can redistribute it and/or modify it
   under the terms of the GNU General Public License as published by the
   Free Software Foundation; either version 3, or (at your option) any
   later version.

   This file is distributed in the hope that it will be useful, but
   WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
   General Public License for more details.

   Under Section 7 of GPL version 3, you are granted additional
   permissions described in the GCC Runtime Library Exception, version
   3.1, as published by the Free Software Foundation.

   You should have received a copy of the GNU General Public License and
   a copy of the GCC Runtime Library Exception along with this program;
   see the files COPYING3 and COPYING.RUNTIME respectively.  If not, see
   <http://www.gnu.org/licenses/>.  */
/*
 * Notes:
 *
 * The goal of this code is to be as fast as possible.  This is
 * not meant to be easy to understand for the casual reader.
 * For slightly simpler code please see the single precision version
 * of this file.
 *
 * Only the default rounding mode is intended for best performances.
 * Exceptions aren't supported yet, but that can be added quite easily
 * if necessary without impacting performances.
 *
 * In the CFI related comments, 'previousOffset' refers to the previous offset
 * from sp used to compute the CFA.
 */
 .cfi_sections .debug_frame
ARM_FUNC_START aeabi_drsub
 CFI_START_FUNCTION
 eor r1, r1, #0x80000000 @ flip sign bit of first arg
 b 1f
ARM_FUNC_START subdf3
ARM_FUNC_ALIAS aeabi_dsub subdf3
 eor r3, r3, #0x80000000 @ flip sign bit of second arg
ARM_FUNC_START adddf3
ARM_FUNC_ALIAS aeabi_dadd adddf3
1: push {r4, r5, lr} @ sp -= 12
 .cfi_adjust_cfa_offset 12 @ CFA is now sp + previousOffset + 12
 .cfi_rel_offset r4, 0 @ Registers are saved from sp to sp + 8
 .cfi_rel_offset r5, 4
 .cfi_rel_offset lr, 8
 @ Look for zeroes, equal values, INF, or NAN.
 shift1 lsl, r4, r1, #1
 shift1 lsl, r5, r3, #1
 teq r4, r5
 do_it eq
 teqeq r0, r2
 do_it ne, ttt
 orrsne ip, r4, r0
 orrsne ip, r5, r2
 mvnsne ip, r4, asr #21
 mvnsne ip, r5, asr #21
 beq .Lad_s
 @ Compute exponent difference. Make largest exponent in r4,
 @ corresponding arg in r1-r0, and positive exponent difference in r5.
 shift1 lsr, r4, r4, #21
 rsbs r5, r4, r5, lsr #21
 do_it lt
 rsblt r5, r5, #0
 ble 1f
 add r4, r4, r5
 eor r2, r0, r2
 eor r3, r1, r3
 eor r0, r2, r0
 eor r1, r3, r1
 eor r2, r0, r2
 eor r3, r1, r3
1:
 @ If exponent difference is too large, return largest argument
 @ already in r1-r0. We need up to 54 bit to handle proper rounding
 @ of 0x1p54 - 1.1.
 cmp r5, #54
 do_it hi
 RETLDM "r4, r5" hi
 @ Convert mantissa to signed integer.
 tst r1, #0x80000000
 mov r1, r1, lsl #12
 mov ip, #0x00100000
 orr r1, ip, r1, lsr #12
 beq 1f
 negs r0, r0
 sbc r1, r1, r1, lsl #1
1:
 tst r3, #0x80000000
 mov r3, r3, lsl #12
 orr r3, ip, r3, lsr #12
 beq 1f
 negs r2, r2
 sbc r3, r3, r3, lsl #1
1:
 @ If exponent == difference, one or both args were denormalized.
 @ Since this is not common case, rescale them off line.
 teq r4, r5
 beq .Lad_d
@ CFI note: we're lucky that the branches to Lad_* that appear after this
@ function have a CFI state that's exactly the same as the one we're in at this
@ point. Otherwise the CFI would change to a different state after the branch,
@ which would be disastrous for backtracing.
.Lad_x:
 @ Compensate for the exponent overlapping the mantissa MSB added later
 sub r4, r4, #1
 @ Shift r3-r2 right per r5, add to r1-r0, keep leftover bits into ip.
 rsbs lr, r5, #32
 blt 1f
 shift1 lsl, ip, r2, lr
 shiftop adds r0 r0 r2 lsr r5 r2
 adc r1, r1, #0
 shiftop adds r0 r0 r3 lsl lr r2
 shiftop adcs r1 r1 r3 asr r5 r3
 b 2f
1: sub r5, r5, #32
 add lr, lr, #32
 cmp r2, #1
 shift1 lsl,ip, r3, lr
 do_it cs
 orrcs ip, ip, #2 @ 2 not 1, to allow lsr #1 later
 shiftop adds r0 r0 r3 asr r5 r3
 adcs r1, r1, r3, asr #31
2:
 @ We now have a result in r1-r0-ip.
 @ Keep absolute value in r1-r0-ip, sign in r5 (the n bit was set above)
 and r5, r1, #0x80000000
 bpl .Lad_p
 mov lr, #0
 negs ip, ip
 sbcs r0, lr, r0
 sbc r1, lr, r1
 @ Determine how to normalize the result.
.Lad_p:
 cmp r1, #0x00100000
 bcc .Lad_a
 cmp r1, #0x00200000
 bcc .Lad_e
 @ Result needs to be shifted right.
 movs r1, r1, lsr #1
 movs r0, r0, rrx
 mov ip, ip, rrx
 add r4, r4, #1
 @ Make sure we did not bust our exponent.
 mov r2, r4, lsl #21
 cmn r2, #(2 << 21)
 bcs .Lad_o
 @ Our result is now properly aligned into r1-r0, remaining bits in ip.
 @ Round with MSB of ip. If halfway between two numbers, round towards
 @ LSB of r0 = 0.
 @ Pack final result together.
.Lad_e:
 cmp ip, #0x80000000
 do_it eq
 movseq ip, r0, lsr #1
 adcs r0, r0, #0
 adc r1, r1, r4, lsl #20
 orr r1, r1, r5
 RETLDM "r4, r5"
 @ Result must be shifted left and exponent adjusted.
.Lad_a:
 movs ip, ip, lsl #1
 adcs r0, r0, r0
 adc r1, r1, r1
 subs r4, r4, #1
 do_it hs
 cmphs r1, #0x00100000
 bhs .Lad_e
 @ No rounding necessary since ip will always be 0 at this point.
.Lad_l:
 teq r1, #0
 do_it eq, t
 moveq r1, r0
 moveq r0, #0
 clz r3, r1
 do_it eq
 addeq r3, r3, #32
 sub r3, r3, #11
 @ determine how to shift the value.
 subs r2, r3, #32
 bge 2f
 adds r2, r2, #12
 ble 1f
 @ shift value left 21 to 31 bits, or actually right 11 to 1 bits
 @ since a register switch happened above.
 add ip, r2, #20
 rsb r2, r2, #12
 shift1 lsl, r0, r1, ip
 shift1 lsr, r1, r1, r2
 b 3f
 @ actually shift value left 1 to 20 bits, which might also represent
 @ 32 to 52 bits if counting the register switch that happened earlier.
1: add r2, r2, #20
2: do_it le
 rsble ip, r2, #32
 shift1 lsl, r1, r1, r2
 lsr ip, r0, ip
 itt le
 orrle r1, r1, ip
 lslle r0, r0, r2
 @ adjust exponent accordingly.
3: subs r4, r4, r3
 do_it ge, tt
 addge r1, r1, r4, lsl #20
 orrge r1, r1, r5
 RETLDM "r4, r5" ge
 @ Exponent too small, denormalize result.
 @ Find out proper shift value.
 mvn r4, r4
 subs r4, r4, #31
 bge 2f
 adds r4, r4, #12
 bgt 1f
 @ shift result right of 1 to 20 bits, sign is in r5.
 add r4, r4, #20
 rsb r2, r4, #32
 shift1 lsr, r0, r0, r4
 shiftop orr r0 r0 r1 lsl r2 r3
 shiftop orr r1 r5 r1 lsr r4 r3
 RETLDM "r4, r5"
 @ shift result right of 21 to 31 bits, or left 11 to 1 bits after
 @ a register switch from r1 to r0.
1: rsb r4, r4, #12
 rsb r2, r4, #32
 shift1 lsr, r0, r0, r2
 shiftop orr r0 r0 r1 lsl r4 r3
 mov r1, r5
 RETLDM "r4, r5"
 @ Shift value right of 32 to 64 bits, or 0 to 32 bits after a switch
 @ from r1 to r0.
2: shift1 lsr, r0, r1, r4
 mov r1, r5
 RETLDM "r4, r5"
 @ Adjust exponents for denormalized arguments.
 @ Note that r4 must not remain equal to 0.
.Lad_d:
 teq r4, #0
 eor r3, r3, #0x00100000
 do_it eq, te
 eoreq r1, r1, #0x00100000
 addeq r4, r4, #1
 subne r5, r5, #1
 b .Lad_x
.Lad_s:
 mvns ip, r4, asr #21
 do_it ne
 mvnsne ip, r5, asr #21
 beq .Lad_i
 teq r4, r5
 do_it eq
 teqeq r0, r2
 beq 1f
 @ Result is x + 0.0 = x or 0.0 + y = y.
 orrs ip, r4, r0
 do_it eq, t
 moveq r1, r3
 moveq r0, r2
 RETLDM "r4, r5"
1: teq r1, r3
 @ Result is x - x = 0.
 do_it ne, tt
 movne r1, #0
 movne r0, #0
 RETLDM "r4, r5" ne
 @ Result is x + x = 2x.
 movs ip, r4, lsr #21
 bne 2f
 movs r0, r0, lsl #1
 adcs r1, r1, r1
 do_it cs
 orrcs r1, r1, #0x80000000
 RETLDM "r4, r5"
2: adds r4, r4, #(2 << 21)
 do_it cc, t
 addcc r1, r1, #(1 << 20)
 RETLDM "r4, r5" cc
 and r5, r1, #0x80000000
 @ Overflow: return INF.
.Lad_o:
 orr r1, r5, #0x7f000000
 orr r1, r1, #0x00f00000
 mov r0, #0
 RETLDM "r4, r5"
 @ At least one of x or y is INF/NAN.
 @ if r1-r0 != INF/NAN: return r3-r2 (which is INF/NAN)
 @ if r3-r2 != INF/NAN: return r1-r0 (which is INF/NAN)
 @ if either is NAN: return NAN
 @ if opposite sign: return NAN
 @ otherwise return r1-r0 (which is INF or -INF)
.Lad_i:
 mvns ip, r4, asr #21
 do_it ne, te
 movne r1, r3
 movne r0, r2
 mvnseq ip, r5, asr #21
 do_it ne, t
 movne r3, r1
 movne r2, r0
 orrs r4, r0, r1, lsl #12
 do_it eq, te
 orrseq r5, r2, r3, lsl #12
 teqeq r1, r3
 orrne r1, r1, #0x00080000 @ quiet NAN
 RETLDM "r4, r5"
 CFI_END_FUNCTION
 FUNC_END aeabi_dsub
 FUNC_END subdf3
 FUNC_END aeabi_dadd
 FUNC_END adddf3
ARM_FUNC_START floatunsidf
ARM_FUNC_ALIAS aeabi_ui2d floatunsidf
 CFI_START_FUNCTION
 teq r0, #0
 do_it eq, t
 moveq r1, #0
 bxeq lr
 push {r4, r5, lr} @ sp -= 12
 .cfi_adjust_cfa_offset 12 @ CFA is now sp + previousOffset + 12
 .cfi_rel_offset r4, 0 @ Registers are saved from sp + 0 to sp + 8.
 .cfi_rel_offset r5, 4
 .cfi_rel_offset lr, 8
 mov r4, #0x400 @ initial exponent
 add r4, r4, #(52-1 - 1)
 mov r5, #0 @ sign bit is 0
 .ifnc r0, r0
 mov r0, r0
 .endif
 mov r1, #0
 b .Lad_l
 CFI_END_FUNCTION
 FUNC_END aeabi_ui2d
 FUNC_END floatunsidf
ARM_FUNC_START floatsidf
ARM_FUNC_ALIAS aeabi_i2d floatsidf
 CFI_START_FUNCTION
 teq r0, #0
 do_it eq, t
 moveq r1, #0
 bxeq lr
 push {r4, r5, lr} @ sp -= 12
 .cfi_adjust_cfa_offset 12 @ CFA is now sp + previousOffset + 12
 .cfi_rel_offset r4, 0 @ Registers are saved from sp + 0 to sp + 8.
 .cfi_rel_offset r5, 4
 .cfi_rel_offset lr, 8
 mov r4, #0x400 @ initial exponent
 add r4, r4, #(52-1 - 1)
 ands r5, r0, #0x80000000 @ sign bit in r5
 do_it mi
 rsbmi r0, r0, #0 @ absolute value
 .ifnc r0, r0
 mov r0, r0
 .endif
 mov r1, #0
 b .Lad_l
 CFI_END_FUNCTION
 FUNC_END aeabi_i2d
 FUNC_END floatsidf
ARM_FUNC_START extendsfdf2
ARM_FUNC_ALIAS aeabi_f2d extendsfdf2
 CFI_START_FUNCTION
 movs r2, r0, lsl #1 @ toss sign bit
 mov r1, r2, asr #3 @ stretch exponent
 mov r1, r1, rrx @ retrieve sign bit
 mov r0, r2, lsl #28 @ retrieve remaining bits
 do_it ne, ttt
 andsne r3, r2, #0xff000000 @ isolate exponent
 teqne r3, #0xff000000 @ if not 0, check if INF or NAN
 eorne r1, r1, #0x38000000 @ fixup exponent otherwise.
 bxne lr @ and return it.
 bics r2, r2, #0xff000000 @ isolate mantissa
 do_it eq @ if 0, that is ZERO or INF,
 bxeq lr @ we are done already.
 teq r3, #0xff000000 @ check for NAN
 do_it eq, t
 orreq r1, r1, #0x00080000 @ change to quiet NAN
 bxeq lr @ and return it.
 @ value was denormalized. We can normalize it now.
 push {r4, r5, lr}
 .cfi_adjust_cfa_offset 12 @ CFA is now sp + previousOffset + 12
 .cfi_rel_offset r4, 0 @ Registers are saved from sp + 0 to sp + 8.
 .cfi_rel_offset r5, 4
 .cfi_rel_offset lr, 8
 mov r4, #0x380 @ setup corresponding exponent
 and r5, r1, #0x80000000 @ move sign bit in r5
 bic r1, r1, #0x80000000
 b .Lad_l
 CFI_END_FUNCTION
 FUNC_END aeabi_f2d
 FUNC_END extendsfdf2
ARM_FUNC_START floatundidf
ARM_FUNC_ALIAS aeabi_ul2d floatundidf
 CFI_START_FUNCTION
 .cfi_remember_state @ Save the current CFA state.
 orrs r2, r0, r1
 do_it eq
 bxeq lr
 push {r4, r5, lr} @ sp -= 12
 .cfi_adjust_cfa_offset 12 @ CFA is now sp + previousOffset + 12
 .cfi_rel_offset r4, 0 @ Registers are saved from sp + 0 to sp + 8
 .cfi_rel_offset r5, 4
 .cfi_rel_offset lr, 8
 mov r5, #0
 b 2f
ARM_FUNC_START floatdidf
ARM_FUNC_ALIAS aeabi_l2d floatdidf
 .cfi_restore_state
 @ Restore the CFI state we saved above. If we didn't do this then the
 @ following instructions would have the CFI state that was set by the
 @ offset adjustments made in floatundidf.
 orrs r2, r0, r1
 do_it eq
 bxeq lr
 push {r4, r5, lr} @ sp -= 12
 .cfi_adjust_cfa_offset 12 @ CFA is now sp + previousOffset + 12
 .cfi_rel_offset r4, 0 @ Registers are saved from sp to sp + 8
 .cfi_rel_offset r5, 4
 .cfi_rel_offset lr, 8
 ands r5, r1, #0x80000000 @ sign bit in r5
 bpl 2f
 negs r0, r0
 sbc r1, r1, r1, lsl #1
2:
 mov r4, #0x400 @ initial exponent
 add r4, r4, #(52-1 - 1)
 @ If FP word order does not match integer word order, swap the words.
 .ifnc r1, r1
 mov ip, r0
 mov r1, r1
 mov r0, ip
 .endif
 movs ip, r1, lsr #22
 beq .Lad_p
 @ The value is too big. Scale it down a bit...
 mov r2, #3
 movs ip, ip, lsr #3
 do_it ne
 addne r2, r2, #3
 movs ip, ip, lsr #3
 do_it ne
 addne r2, r2, #3
 add r2, r2, ip, lsr #3
 rsb r3, r2, #32
 shift1 lsl, ip, r0, r3
 shift1 lsr, r0, r0, r2
 shiftop orr r0 r0 r1 lsl r3 lr
 shift1 lsr, r1, r1, r2
 add r4, r4, r2
 b .Lad_p
 CFI_END_FUNCTION
 FUNC_END floatdidf
 FUNC_END aeabi_l2d
 FUNC_END floatundidf
 FUNC_END aeabi_ul2d
@ Define multiplication as weak in _arm_muldf3.o so that it can be overriden
@ by the global definition in _arm_muldivdf3.o. This allows a program only
@ using multiplication to take the weak definition which does not contain the
@ division code. Programs using only division or both division and
@ multiplication will pull _arm_muldivdf3.o from which both the multiplication
@ and division are taken thanks to the override.
ARM_FUNC_START muldf3
ARM_FUNC_ALIAS aeabi_dmul muldf3
 CFI_START_FUNCTION
 push {r4, r5, r6, lr} @ sp -= 16
 .cfi_adjust_cfa_offset 16 @ CFA is now sp + previousOffset + 16
 .cfi_rel_offset r4, 0 @ Registers are saved from sp to sp + 12.
 .cfi_rel_offset r5, 4
 .cfi_rel_offset r6, 8
 .cfi_rel_offset lr, 12
 @ Mask out exponents, trap any zero/denormal/INF/NAN.
 mov ip, #0xff
 orr ip, ip, #0x700
 ands r4, ip, r1, lsr #20
 do_it ne, tte
 andsne r5, ip, r3, lsr #20
 teqne r4, ip
 teqne r5, ip
 bleq .Lml_s
 @ Add exponents together
 add r4, r4, r5
 @ Determine final sign.
 eor r6, r1, r3
 @ Convert mantissa to unsigned integer.
 @ If power of two, branch to a separate path.
 bic r1, r1, ip, lsl #21
 bic r3, r3, ip, lsl #21
 orrs r5, r0, r1, lsl #12
 do_it ne
 orrsne r5, r2, r3, lsl #12
 orr r1, r1, #0x00100000
 orr r3, r3, #0x00100000
 beq .Lml_1
 @ Here is the actual multiplication.
 @ This code works on architecture versions >= 4
 umull ip, lr, r0, r2
 mov r5, #0
 umlal lr, r5, r1, r2
 and r2, r6, #0x80000000
 umlal lr, r5, r0, r3
 mov r6, #0
 umlal r5, r6, r1, r3
 @ The LSBs in ip are only significant for the final rounding.
 @ Fold them into lr.
 teq ip, #0
 do_it ne
 orrne lr, lr, #1
 @ Adjust result upon the MSB position.
 sub r4, r4, #0xff
 cmp r6, #(1 << (20-11))
 sbc r4, r4, #0x300
 bcs 1f
 movs lr, lr, lsl #1
 adcs r5, r5, r5
 adc r6, r6, r6
1:
 @ Shift to final position, add sign to result.
 orr r1, r2, r6, lsl #11
 orr r1, r1, r5, lsr #21
 mov r0, r5, lsl #11
 orr r0, r0, lr, lsr #21
 mov lr, lr, lsl #11
 @ Check exponent range for under/overflow.
 subs ip, r4, #(254 - 1)
 do_it hi
 cmphi ip, #0x700
 bhi .Lml_u
 @ Round the result, merge final exponent.
 cmp lr, #0x80000000
 do_it eq
 movseq lr, r0, lsr #1
 adcs r0, r0, #0
 adc r1, r1, r4, lsl #20
 RETLDM "r4, r5, r6"
 @ Multiplication by 0x1p*: let''s shortcut a lot of code.
.Lml_1:
 and r6, r6, #0x80000000
 orr r1, r6, r1
 orr r0, r0, r2
 eor r1, r1, r3
 subs r4, r4, ip, lsr #1
 do_it gt, tt
 rsbsgt r5, r4, ip
 orrgt r1, r1, r4, lsl #20
 RETLDM "r4, r5, r6" gt
 @ Under/overflow: fix things up for the code below.
 orr r1, r1, #0x00100000
 mov lr, #0
 subs r4, r4, #1
.Lml_u:
 @ Overflow?
 bgt .Lml_o
 @ Check if denormalized result is possible, otherwise return signed 0.
 cmn r4, #(53 + 1)
 do_it le, tt
 movle r0, #0
 bicle r1, r1, #0x7fffffff
 RETLDM "r4, r5, r6" le
 @ Find out proper shift value.
 rsb r4, r4, #0
 subs r4, r4, #32
 bge 2f
 adds r4, r4, #12
 bgt 1f
 @ shift result right of 1 to 20 bits, preserve sign bit, round, etc.
 add r4, r4, #20
 rsb r5, r4, #32
 shift1 lsl, r3, r0, r5
 shift1 lsr, r0, r0, r4
 shiftop orr r0 r0 r1 lsl r5 r2
 and r2, r1, #0x80000000
 bic r1, r1, #0x80000000
 adds r0, r0, r3, lsr #31
 shiftop adc r1 r2 r1 lsr r4 r6
 orrs lr, lr, r3, lsl #1
 do_it eq
 biceq r0, r0, r3, lsr #31
 RETLDM "r4, r5, r6"
 @ shift result right of 21 to 31 bits, or left 11 to 1 bits after
 @ a register switch from r1 to r0. Then round.
1: rsb r4, r4, #12
 rsb r5, r4, #32
 shift1 lsl, r3, r0, r4
 shift1 lsr, r0, r0, r5
 shiftop orr r0 r0 r1 lsl r4 r2
 bic r1, r1, #0x7fffffff
 adds r0, r0, r3, lsr #31
 adc r1, r1, #0
 orrs lr, lr, r3, lsl #1
 do_it eq
 biceq r0, r0, r3, lsr #31
 RETLDM "r4, r5, r6"
 @ Shift value right of 32 to 64 bits, or 0 to 32 bits after a switch
 @ from r1 to r0. Leftover bits are in r3-r6-lr for rounding.
2: rsb r5, r4, #32
 shiftop orr lr lr r0 lsl r5 r2
 shift1 lsr, r3, r0, r4
 shiftop orr r3 r3 r1 lsl r5 r2
 shift1 lsr, r0, r1, r4
 bic r1, r1, #0x7fffffff
 shiftop bic r0 r0 r1 lsr r4 r2
 add r0, r0, r3, lsr #31
 orrs lr, lr, r3, lsl #1
 do_it eq
 biceq r0, r0, r3, lsr #31
 RETLDM "r4, r5, r6"
 @ One or both arguments are denormalized.
 @ Scale them leftwards and preserve sign bit.
.Lml_d:
 teq r4, #0
 bne 2f
 and r6, r1, #0x80000000
1: movs r0, r0, lsl #1
 adc r1, r1, r1
 tst r1, #0x00100000
 do_it eq
 subeq r4, r4, #1
 beq 1b
 orr r1, r1, r6
 teq r5, #0
 do_it ne
 bxne lr
2: and r6, r3, #0x80000000
3: movs r2, r2, lsl #1
 adc r3, r3, r3
 tst r3, #0x00100000
 do_it eq
 subeq r5, r5, #1
 beq 3b
 orr r3, r3, r6
 bx lr
.Lml_s:
 @ Isolate the INF and NAN cases away
 teq r4, ip
 and r5, ip, r3, lsr #20
 do_it ne
 teqne r5, ip
 beq 1f
 @ Here, one or more arguments are either denormalized or zero.
 orrs r6, r0, r1, lsl #1
 do_it ne
 orrsne r6, r2, r3, lsl #1
 bne .Lml_d
 @ Result is 0, but determine sign anyway.
.Lml_z:
 eor r1, r1, r3
 and r1, r1, #0x80000000
 mov r0, #0
 RETLDM "r4, r5, r6"
1: @ One or both args are INF or NAN.
 orrs r6, r0, r1, lsl #1
 do_it eq, te
 moveq r0, r2
 moveq r1, r3
 orrsne r6, r2, r3, lsl #1
 beq .Lml_n @ 0 * INF or INF * 0 -> NAN
 teq r4, ip
 bne 1f
 orrs r6, r0, r1, lsl #12
 bne .Lml_n @ NAN * <anything> -> NAN
1: teq r5, ip
 bne .Lml_i
 orrs r6, r2, r3, lsl #12
 do_it ne, t
 movne r0, r2
 movne r1, r3
 bne .Lml_n @ <anything> * NAN -> NAN
 @ Result is INF, but we need to determine its sign.
.Lml_i:
 eor r1, r1, r3
 @ Overflow: return INF (sign already in r1).
.Lml_o:
 and r1, r1, #0x80000000
 orr r1, r1, #0x7f000000
 orr r1, r1, #0x00f00000
 mov r0, #0
 RETLDM "r4, r5, r6"
 @ Return a quiet NAN.
.Lml_n:
 orr r1, r1, #0x7f000000
 orr r1, r1, #0x00f80000
 RETLDM "r4, r5, r6"
 CFI_END_FUNCTION
 FUNC_END aeabi_dmul
 FUNC_END muldf3
ARM_FUNC_START fixdfsi
ARM_FUNC_ALIAS aeabi_d2iz fixdfsi
 CFI_START_FUNCTION
 @ check exponent range.
 mov r2, r1, lsl #1
 adds r2, r2, #(1 << 21)
 bcs 2f @ value is INF or NAN
 bpl 1f @ value is too small
 mov r3, #(0xfffffc00 + 31)
 subs r2, r3, r2, asr #21
 bls 3f @ value is too large
 @ scale value
 mov r3, r1, lsl #11
 orr r3, r3, #0x80000000
 orr r3, r3, r0, lsr #21
 tst r1, #0x80000000 @ the sign bit
 shift1 lsr, r0, r3, r2
 do_it ne
 rsbne r0, r0, #0
 bx lr
1: mov r0, #0
 bx lr
2: orrs r0, r0, r1, lsl #12
 bne 4f @ x is NAN.
3: ands r0, r1, #0x80000000 @ the sign bit
 do_it eq
 moveq r0, #0x7fffffff @ maximum signed positive si
 bx lr
4: mov r0, #0 @ How should we convert NAN?
 bx lr
 CFI_END_FUNCTION
 FUNC_END aeabi_d2iz
 FUNC_END fixdfsi
ARM_FUNC_START fixunsdfsi
ARM_FUNC_ALIAS aeabi_d2uiz fixunsdfsi
 CFI_START_FUNCTION
 @ check exponent range.
 movs r2, r1, lsl #1
 bcs 1f @ value is negative
 adds r2, r2, #(1 << 21)
 bcs 2f @ value is INF or NAN
 bpl 1f @ value is too small
 mov r3, #(0xfffffc00 + 31)
 subs r2, r3, r2, asr #21
 bmi 3f @ value is too large
 @ scale value
 mov r3, r1, lsl #11
 orr r3, r3, #0x80000000
 orr r3, r3, r0, lsr #21
 shift1 lsr, r0, r3, r2
 bx lr
1: mov r0, #0
 bx lr
2: orrs r0, r0, r1, lsl #12
 bne 4f @ value is NAN.
3: mov r0, #0xffffffff @ maximum unsigned si
 bx lr
4: mov r0, #0 @ How should we convert NAN?
 bx lr
 CFI_END_FUNCTION
 FUNC_END aeabi_d2uiz
 FUNC_END fixunsdfsi
ARM_FUNC_START truncdfsf2
ARM_FUNC_ALIAS aeabi_d2f truncdfsf2
 CFI_START_FUNCTION
 @ check exponent range.
 mov r2, r1, lsl #1
 subs r3, r2, #((1023 - 127) << 21)
 do_it cs, t
 subscs ip, r3, #(1 << 21)
 rsbscs ip, ip, #(254 << 21)
 bls 2f @ value is out of range
1: @ shift and round mantissa
 and ip, r1, #0x80000000
 mov r2, r0, lsl #3
 orr r0, ip, r0, lsr #29
 cmp r2, #0x80000000
 adc r0, r0, r3, lsl #2
 do_it eq
 biceq r0, r0, #1
 bx lr
2: @ either overflow or underflow
 tst r1, #0x40000000
 bne 3f @ overflow
 @ check if denormalized value is possible
 adds r2, r3, #(23 << 21)
 do_it lt, t
 andlt r0, r1, #0x80000000 @ too small, return signed 0.
 bxlt lr
 @ denormalize value so we can resume with the code above afterwards.
 orr r1, r1, #0x00100000
 mov r2, r2, lsr #21
 rsb r2, r2, #24
 rsb ip, r2, #32
 lsls r3, r0, ip
 shift1 lsr, r0, r0, r2
 do_it ne
 orrne r0, r0, #1 @ fold r3 for rounding considerations.
 mov r3, r1, lsl #11
 mov r3, r3, lsr #11
 shiftop orr r0 r0 r3 lsl ip ip
 shift1 lsr, r3, r3, r2
 mov r3, r3, lsl #1
 b 1b
3: @ chech for NAN
 mvns r3, r2, asr #21
 bne 5f @ simple overflow
 orrs r3, r0, r1, lsl #12
 do_it ne, tt
 movne r0, #0x7f000000
 orrne r0, r0, #0x00c00000
 bxne lr @ return NAN
5: @ return INF with sign
 and r0, r1, #0x80000000
 orr r0, r0, #0x7f000000
 orr r0, r0, #0x00800000
 bx lr
 CFI_END_FUNCTION
 FUNC_END aeabi_d2f
 FUNC_END truncdfsf2
/* ieee754-sf.S single-precision floating point support for ARM

   Copyright (C) 2003-2024 Free Software Foundation, Inc.
   Contributed by Nicolas Pitre (nico@fluxnic.net)

   This file is free software; you can redistribute it and/or modify it
   under the terms of the GNU General Public License as published by the
   Free Software Foundation; either version 3, or (at your option) any
   later version.

   This file is distributed in the hope that it will be useful, but
   WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
   General Public License for more details.

   Under Section 7 of GPL version 3, you are granted additional
   permissions described in the GCC Runtime Library Exception, version
   3.1, as published by the Free Software Foundation.

   You should have received a copy of the GNU General Public License and
   a copy of the GCC Runtime Library Exception along with this program;
   see the files COPYING3 and COPYING.RUNTIME respectively.  If not, see
   <http://www.gnu.org/licenses/>.  */
/*
 * Notes:
 *
 * The goal of this code is to be as fast as possible.  This is
 * not meant to be easy to understand for the casual reader.
 *
 * Only the default rounding mode is intended for best performances.
 * Exceptions aren't supported yet, but that can be added quite easily
 * if necessary without impacting performances.
 *
 * In the CFI related comments, 'previousOffset' refers to the previous offset
 * from sp used to compute the CFA.
 */
/* Miscellaneous BPABI functions.

   Copyright (C) 2003-2024 Free Software Foundation, Inc.
   Contributed by CodeSourcery, LLC.

   This file is free software; you can redistribute it and/or modify it
   under the terms of the GNU General Public License as published by the
   Free Software Foundation; either version 3, or (at your option) any
   later version.

   This file is distributed in the hope that it will be useful, but
   WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
   General Public License for more details.

   Under Section 7 of GPL version 3, you are granted additional
   permissions described in the GCC Runtime Library Exception, version
   3.1, as published by the Free Software Foundation.

   You should have received a copy of the GNU General Public License and
   a copy of the GCC Runtime Library Exception along with this program;
   see the files COPYING3 and COPYING.RUNTIME respectively.  If not, see
   <http://www.gnu.org/licenses/>.  */
 .cfi_sections .debug_frame
/* Some attributes that are common to all routines in this file.  */
 /* Tag_ABI_align_needed: This code does not require 8-byte
	   alignment from the caller.  */
 /* .eabi_attribute 24, 0  -- default setting.  */
 /* Tag_ABI_align_preserved: This code preserves 8-byte
	   alignment in any callee.  */
 .eabi_attribute 25, 1
.macro test_div_by_zero signed
/* Tail-call to divide-by-zero handlers which may be overridden by the user,
   so unwinding works properly.  */
 cbnz r3, 2f
 cbnz r2, 2f
 cmp r1, #0
 .ifc \signed, unsigned
 do_it eq
 cmpeq r0, #0
 do_it ne, t
 movne r1, #0xffffffff
 movne r0, #0xffffffff
 .else
 do_it lt, tt
 movlt r0, #0
 movlt r1, #0x80000000
 blt 1f
 do_it eq
 cmpeq r0, #0
 do_it ne, t
 movne r1, #0x7fffffff
 movne r0, #0xffffffff
 .endif
1:
 b __aeabi_ldiv0
2:
.endm
/* we can use STRD/LDRD on v5TE and later, and any Thumb-2 architecture. */
/* set up stack from for call to __udivmoddi4. At the end of the macro the
   stack is arranged as follows:
		sp+12	/ space for remainder
		sp+8	\ (written by __udivmoddi4)
		sp+4	lr
		sp+0	sp+8 [rp (remainder pointer) argument for __udivmoddi4]

 */
.macro push_for_divide fname
 sub ip, sp, #8
 strd ip, lr, [sp, #-16]!
 .cfi_adjust_cfa_offset 16
 .cfi_offset 14, -12
.endm
/* restore stack */
.macro pop_for_divide
 ldr lr, [sp, #4]
 ldrd r2, r3, [sp, #8]
 add sp, sp, #16
 .cfi_restore 14
 .cfi_adjust_cfa_offset 0
.endm

.section .note.GNU-stack,"",%progbits
#endif
