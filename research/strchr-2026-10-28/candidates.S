/* Research only: ordinary little-endian SRAM/Flash, unsigned-char target.
 * Word candidates never read before p; each aligned four-byte word is
 * checked before the next. The final word may extend three bytes past NUL.
 * ST_VARIANT exports one candidate as strchr for real standalone SDK APPs.
 */
.syntax unified
.thumb
.macro entry name
 .section .text.\name,"ax",%progbits
 .balign 4
 .global \name
 .type \name,%function
 .thumb_func
\name:
.endm
.macro finish name
 .size \name,.-\name
.endm

.macro byte1 name
 entry \name
 uxtb r1,r1
.Lbyte\@:
 ldrb r2,[r0]
 cmp r2,r1
 beq .Lreturn\@
 adds r0,#1
 cmp r2,#0
 bne .Lbyte\@
 movs r0,#0
.Lreturn\@:
 bx lr
 finish \name
.endm

/* A small fully unrolled byte body; each byte precedes its NUL test. */
.macro bytes4 name
 entry \name
 uxtb r1,r1
.Lloop\@:
 ldrb r2,[r0]
 cmp r2,r1
 beq .Lreturn\@
 cmp r2,#0
 beq .Lzero\@
 ldrb r2,[r0,#1]
 cmp r2,r1
 beq .Lone\@
 cmp r2,#0
 beq .Lzero\@
 ldrb r2,[r0,#2]
 cmp r2,r1
 beq .Ltwo\@
 cmp r2,#0
 beq .Lzero\@
 ldrb r2,[r0,#3]
 cmp r2,r1
 beq .Lthree\@
 cmp r2,#0
 beq .Lzero\@
 adds r0,#4
 b .Lloop\@
.Lthree\@:
 adds r0,#1
.Ltwo\@:
 adds r0,#1
.Lone\@:
 adds r0,#1
.Lreturn\@:
 bx lr
.Lzero\@:
 movs r0,#0
 bx lr
 finish \name
.endm

.macro word name,steps
 entry \name
 uxtb r1,r1
.Lprefix\@:
 ldrb r2,[r0]
 cmp r2,r1
 beq .Lreturn\@
 cmp r2,#0
 beq .Lzero\@
 movs r3,#3
 tst r0,r3
 beq .Laligned\@
 adds r0,#1
 b .Lprefix\@
.Lzero\@:
 movs r0,#0
.Lreturn\@:
 bx lr
.Laligned\@:
 push {r4,r5}
 ldr r4,.Lones\@
 lsls r5,r4,#7
 muls r1,r4
.Lloop\@:
 .rept \steps
 ldr r2,[r0]
 movs r3,r2
 subs r3,r3,r4
 bics r3,r2
 tst r3,r5
 bne .Ltail\@
 eors r2,r1
 movs r3,r2
 subs r3,r3,r4
 bics r3,r2
 tst r3,r5
 bne .Ltail\@
 adds r0,#4
 .endr
 b .Lloop\@
.Ltail\@:
 uxtb r1,r1
 pop {r4,r5}
.Lbyte\@:
 ldrb r2,[r0]
 cmp r2,r1
 beq .Lreturn\@
 adds r0,#1
 cmp r2,#0
 bne .Lbyte\@
 b .Lzero\@
 .balign 4
.Lones\@:
 .word 0x01010101
 finish \name
.endm

#if defined(__ARM_ARCH_7EM__)
.macro dsp name,steps
 entry \name
 uxtb r1,r1
.Lprefix\@:
 ldrb r2,[r0]
 cmp r2,r1
 beq .Lreturn\@
 cmp r2,#0
 beq .Lzero\@
 lsls r3,r0,#30
 beq .Laligned\@
 adds r0,#1
 b .Lprefix\@
.Lzero\@:
 movs r0,#0
.Lreturn\@:
 bx lr
.Laligned\@:
 push {r4,r5}
 ldr r4,.Lones\@
 mul r1,r1,r4
.Lloop\@:
 .rept \steps
 ldr r3,[r0]
 uqsub8 r2,r4,r3
 eor r12,r3,r1
 uqsub8 r12,r4,r12
 orrs r2,r2,r12
 bne .Lfound\@
 adds r0,#4
 .endr
 b .Lloop\@
.Lfound\@:
 rbit r2,r2
 clz r2,r2
 add r0,r0,r2,lsr#3
 uxtb r1,r1
 ldrb r2,[r0]
 cmp r2,r1
 beq .Lsaved\@
 movs r0,#0
.Lsaved\@:
 pop {r4,r5}
 bx lr
 .balign 4
.Lones\@:
 .word 0x01010101
 finish \name
.endm
#endif

#if !defined(ST_VARIANT)
 byte1 byte1_strchr
 bytes4 byte4_strchr
 word word1_strchr,1
 word word2_strchr,2
#if defined(__ARM_ARCH_7EM__)
 dsp dsp1_strchr,1
 dsp dsp2_strchr,2
#endif
#elif ST_VARIANT == 1
 byte1 strchr
#elif ST_VARIANT == 2
 bytes4 strchr
#elif ST_VARIANT == 3
 word strchr,1
#elif ST_VARIANT == 4
 word strchr,2
#elif ST_VARIANT == 5 && defined(__ARM_ARCH_7EM__)
 dsp strchr,1
#elif ST_VARIANT == 6 && defined(__ARM_ARCH_7EM__)
 dsp strchr,2
#else
#error Unsupported research strchr variant
#endif
