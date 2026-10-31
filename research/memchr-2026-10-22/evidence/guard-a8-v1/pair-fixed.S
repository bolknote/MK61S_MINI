/* Align each two-word LDM to eight bytes. With an early match, n may extend
 * past the object: the pair must not straddle a readable-memory boundary.
 * The byte prefix stops at the first match. Candidate, not selected. */
.syntax unified
.thumb
.macro function name
.section .text.\name,"ax",%progbits
.balign 4
.global \name
.type \name,%function
.thumb_func
\name:
.endm
.macro probe_pair name,bulk=0
 ldmia r0!,{r3,r6}
#if defined(__ARM_ARCH_6M__)
 eors r3,r1
 movs r7,r3
 subs r7,r4
 bics r7,r3
 tst r7,r5
 bne .Lfirst\name
 eors r6,r1
 movs r7,r6
 subs r7,r4
 bics r7,r6
 tst r7,r5
 bne .Lsecond\name
#else
 eor r3,r3,r1
 eor r6,r6,r1
 usub8 r3,r3,r4
 sel r3,r5,r4
 usub8 r6,r6,r4
 /* If word two has no match in a lane, retain word one's mask. */
 sel r6,r3,r4
#if defined(MEMCHR_CBNZ)
 .if \bulk
 cbnz r6,.LpairHit\name
 .else
 cmp r6,#0
 bne .LpairHit\name
 .endif
#else
 cmp r6,#0
 bne .LpairHit\name
#endif
#endif
.endm
.macro search name,pairs
function \name
 cmp r2,#0
 beq .Lzero\name
 uxtb r1,r1
 ldrb r3,[r0]
 cmp r3,r1
 beq .Lreturn\name
#if defined(MEMCHR_BALANCED_PREFIX)
 /* Keep the original pointer/alignment for long spans, but exhaust n==1
  * before the length dispatch. Restore n only on the long path. */
 subs r2,#1
 beq .Lzero\name
 cmp r2,#7
 bhs .LalignCheck\name
 adds r0,#1
#elif defined(MEMCHR_FAST_PREFIX)
 /* Consume the checked byte before dispatch: n==1 returns immediately. */
 subs r2,#1
 beq .Lzero\name
 adds r0,#1
 cmp r2,#7
 bhs .Lprefix\name
#else
 cmp r2,#8
 bhs .LalignCheck\name
 adds r0,#1
 subs r2,#1
 beq .Lzero\name
#endif
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
#if defined(MEMCHR_BALANCED_PREFIX)
 adds r2,#1
#endif
 lsls r3,r0,#29
 beq .Laligned\name
 adds r0,#1
 subs r2,#1
.Lprefix\name:
 lsls r3,r0,#29
 beq .Laligned\name
 ldrb r3,[r0]
 cmp r3,r1
 beq .Lreturn\name
 adds r0,#1
 subs r2,#1
 b .Lprefix\name
.Laligned\name:
#if defined(__ARM_ARCH_6M__)
 push {r4,r5,r6,r7}
#else
 push {r4,r5,r6}
#endif
 ldr r4,=0x01010101
#if defined(__ARM_ARCH_6M__)
 lsls r5,r4,#7
 muls r1,r4
#else
 movs r5,#0
 mul r1,r1,r4
#endif
 .if \pairs>1
 cmp r2,#(8*\pairs)
 bhs .Lbulk\name
 b .LpairCheck\name
.Lbulk\name:
 .rept \pairs
 probe_pair \name,1
 .endr
 b .LbulkNext\name
 .endif
#if defined(__ARM_ARCH_6M__)
.Lfirst\name:
 subs r0,#8
 b .Lfound\name
.Lsecond\name:
 subs r0,#4
 b .Lfound\name
#else
.LpairHit\name:
 cmp r3,#0
 bne .Lfirst\name
 mov r3,r6
 subs r0,#4
 b .Lfound\name
.Lfirst\name:
 subs r0,#8
 b .Lfound\name
#endif
 .if \pairs>1
.LbulkNext\name:
 subs r2,#(8*\pairs)
 cmp r2,#(8*\pairs)
 blo .LpairCheck\name
 b .Lbulk\name
 .endif
.LpairCheck\name:
 cmp r2,#8
 blo .LwordCheck\name
.Lpair\name:
 probe_pair \name
 subs r2,#8
 cmp r2,#8
 bhs .Lpair\name
.LwordCheck\name:
 cmp r2,#4
 blo .LtailCheck\name
 ldr r3,[r0]
#if defined(__ARM_ARCH_6M__)
 eors r3,r1
 movs r7,r3
 subs r7,r4
 bics r7,r3
 tst r7,r5
#else
 eor r3,r3,r1
 usub8 r3,r3,r4
 sel r3,r5,r4
 cmp r3,#0
#endif
 bne .Lfound\name
 adds r0,#4
 subs r2,#4
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
 pop {r4,r5,r6,r7}
#else
 pop {r4,r5,r6}
#endif
 bx lr
.Lfound\name:
#if defined(__ARM_ARCH_6M__)
 uxtb r1,r1
.LfindByte\name:
 ldrb r3,[r0]
 cmp r3,r1
 beq .LsavedReturn\name
 adds r0,#1
 b .LfindByte\name
#else
 rbit r3,r3
 clz r3,r3
 add r0,r0,r3,lsr#3
 b .LsavedReturn\name
#endif
 .ltorg
.size \name,.-\name
.endm
search pair16,2
#if defined(MEMCHR_CBNZ)
search pair64,4
#else
search pair64,8
#endif
