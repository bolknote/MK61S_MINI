/* Exact-span memchr candidates. Only naturally aligned words are loaded.
 * The byte path needs no stack; the word path saves only its constants. */
.syntax unified
.thumb
#if defined(__ARM_ARCH_6M__)
.cpu cortex-m0plus
#else
.cpu cortex-m4
#endif
.macro function name
.section .text.\name,"ax",%progbits
.balign 4
.global \name
.type \name,%function
.thumb_func
\name:
.endm
.macro end name
.size \name,.-\name
.endm

function indirect_search
 ldr r3,=bench_search_runtime
 ldr r3,[r3]
 ldr r3,[r3,#104]
 bx r3
 .ltorg
end indirect_search
function control_search
 movs r0,#0
 bx lr
end control_search

function byte_search
 cmp r2,#0
 beq .LbyteZero
 uxtb r1,r1
.LbyteLoop:
 ldrb r3,[r0]
 cmp r3,r1
 beq .LbyteReturn
 adds r0,#1
 subs r2,#1
 bne .LbyteLoop
.LbyteZero:
 movs r0,#0
.LbyteReturn:
 bx lr
end byte_search

.macro probe name,offset,swar
 ldr r3,[r0,#\offset]
#if defined(__ARM_ARCH_6M__)
 eors r3,r1
 movs r6,r3
 subs r6,r4
 bics r6,r3
 tst r6,r5
#else
 eor r3,r3,r1
 .if \swar
 sub r12,r3,r4
 bic r12,r12,r3
 tst r12,r5
 .else
 usub8 r3,r3,r4
 sel r3,r5,r4
 cmp r3,#0
 .endif
#endif
 bne .Lhit\name\()_\offset
.endm
.macro hit name,offset
.Lhit\name\()_\offset:
 .if \offset
 adds r0,#\offset
 .endif
 b .Lfound\name
.endm
.macro search name,words,swar=0
function \name
 cmp r2,#0
 beq .Lzero\name
 uxtb r1,r1
 ldrb r3,[r0]
 cmp r3,r1
 beq .Lreturn\name
 cmp r2,#8
 bhs .LalignCheck\name
 /* Byte zero is already checked, including the one-byte case. */
 adds r0,#1
 subs r2,#1
 beq .Lzero\name
.Lsmall\name:
 ldrb r3,[r0]
 cmp r3,r1
 beq .Lreturn\name
 adds r0,#1
 subs r2,#1
 bne .Lsmall\name
.Lzero\name:
 movs r0,#0
.Lreturn\name:
 bx lr
.LalignCheck\name:
 lsls r3,r0,#30
 beq .Laligned\name
 adds r0,#1
 subs r2,#1
.Lprefix\name:
 lsls r3,r0,#30
 beq .Laligned\name
 ldrb r3,[r0]
 cmp r3,r1
 beq .Lreturn\name
 adds r0,#1
 subs r2,#1
 b .Lprefix\name
.Laligned\name:
#if defined(__ARM_ARCH_6M__)
 push {r4,r5,r6}
#else
 push {r4,r5}
#endif
 ldr r4,=0x01010101
#if defined(__ARM_ARCH_6M__)
 lsls r5,r4,#7
 muls r1,r4
#else
 .if \swar
 lsl r5,r4,#7
 .else
 movs r5,#0
 .endif
 mul r1,r1,r4
#endif
 .if \words>1
 cmp r2,#(4*\words)
 bhs .Lbulk\name
 b .LwordCheck\name
.Lbulk\name:
 .set offset,0
 .rept \words
 probe \name,%offset,\swar
 .set offset,offset+4
 .endr
 b .LbulkNext\name
 .set offset,0
 .rept \words
 hit \name,%offset
 .set offset,offset+4
 .endr
.LbulkNext\name:
 adds r0,#(4*\words)
 subs r2,#(4*\words)
 cmp r2,#(4*\words)
 blo .LwordCheck\name
 b .Lbulk\name
 .endif
.LwordCheck\name:
 cmp r2,#4
 blo .LtailCheck\name
.Lword\name:
 probe \name,0,\swar
 adds r0,#4
 subs r2,#4
 cmp r2,#4
 bhs .Lword\name
.LtailCheck\name:
 cmp r2,#0
 beq .LsavedZero\name
 uxtb r1,r1
.Ltail\name:
 ldrb r3,[r0]
 cmp r3,r1
 beq .LsavedReturn\name
 adds r0,#1
 subs r2,#1
 bne .Ltail\name
.LsavedZero\name:
 movs r0,#0
.LsavedReturn\name:
#if defined(__ARM_ARCH_6M__)
 pop {r4,r5,r6}
#else
 pop {r4,r5}
#endif
 bx lr
 .if \words==1
 hit \name,0
 .endif
.Lfound\name:
#if defined(__ARM_ARCH_6M__)
 uxtb r1,r1
.LfoundByte\name:
 ldrb r3,[r0]
 cmp r3,r1
 beq .LsavedReturn\name
 adds r0,#1
 b .LfoundByte\name
#else
 .if \swar
 and r3,r12,r5
 .endif
 rbit r3,r3
 clz r3,r3
 add r0,r0,r3,lsr#3
 b .LsavedReturn\name
#endif
 .ltorg
end \name
.endm
.altmacro
search own4,1
search own16,4
search own64,16
#if !defined(__ARM_ARCH_6M__)
search swar16,4,1
#endif
