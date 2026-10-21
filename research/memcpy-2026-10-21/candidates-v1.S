/* Complete ISO C candidates; no reads or writes outside the requested spans. */
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
.macro end name
.size \name,.-\name
.endm
function runtime_copy
 ldr r3,=bench_runtime
 ldr r3,[r3]
 ldr r3,[r3,#88]
 bx r3
 .ltorg
end runtime_copy
function control_copy
 bx lr
end control_copy
#if defined(__ARM_ARCH_6M__)
.cpu cortex-m0plus
/* Mismatched alignment: align destination, gather the bounded leading
 * fragment, then combine aligned source words with its carried bytes.
 * The last word is loaded only when all four source bytes are available. */
.macro merge tag, k, unroll
.Lmerge\tag\@:
 movs r5,#0
 .if \k==3
 ldrb r5,[r1,#2]
 lsls r5,r5,#8
 .endif
 .if \k>=2
 ldrb r3,[r1,#1]
 orrs r5,r3
 lsls r5,r5,#8
 .endif
 ldrb r3,[r1]
 orrs r5,r3
 adds r1,#\k
 subs r2,#(4+\k)
 .if \unroll
 cmp r2,#12
 blo .Lmword\@
 subs r2,#12
.Lm16\@:
 .rept 4
 ldmia r1!,{r3}
 lsls r4,r3,#(\k*8)
 orrs r4,r5
 stmia r0!,{r4}
 lsrs r5,r3,#(32-\k*8)
 .endr
 subs r2,#16
 bhs .Lm16\@
 adds r2,#12
 bcc .Lmend\@
 .endif
.Lmword\@:
 ldmia r1!,{r3}
 lsls r4,r3,#(\k*8)
 orrs r4,r5
 stmia r0!,{r4}
 lsrs r5,r3,#(32-\k*8)
 subs r2,#4
 bhs .Lmword\@
.Lmend\@:
 .rept \k
 strb r5,[r0]
 adds r0,#1
 lsrs r5,r5,#8
 .endr
 adds r2,#4
 pop {r4,r5,r6}
 b .Lbytes\tag
.endm
.macro m0copy name, unroll
function \name
 cmp r2,#8
 bhs .Llarge\@
 b .Lsmall\@
.Llarge\@:
 mov r12,r0
 push {r4,r5,r6}
 movs r4,#3
.Lalign\@:
 tst r0,r4
 beq .Laligned\@
 ldrb r3,[r1]
 strb r3,[r0]
 adds r0,#1
 adds r1,#1
 subs r2,#1
 b .Lalign\@
.Laligned\@:
 movs r3,r1
 ands r3,r4
 beq .Lwords\@
 cmp r2,#8
 blo .Lpopbytes\@
 cmp r3,#1
 beq .Lcase3\@
 cmp r3,#2
 bne .Lnot2\@
 b .Lcase2\@
.Lnot2\@:
 b .Lcase1\@
.Lwords\@:
 subs r2,#16
 blo .Ltail\@
 .if \unroll
 cmp r2,#48
 blo .L16\@
 subs r2,#48
.L64\@:
 .rept 4
 ldmia r1!,{r3,r4,r5,r6}
 stmia r0!,{r3,r4,r5,r6}
 .endr
 subs r2,#64
 bhs .L64\@
 adds r2,#48
 bcc .Ltail\@
 .endif
.L16\@:
 ldmia r1!,{r3,r4,r5,r6}
 stmia r0!,{r3,r4,r5,r6}
 subs r2,#16
 bhs .L16\@
.Ltail\@:
 lsls r2,r2,#29
 bcc .Lfour\@
 ldmia r1!,{r3,r4}
 stmia r0!,{r3,r4}
.Lfour\@:
 lsls r2,r2,#1
 bcc .Lhalf\@
 ldmia r1!,{r3}
 stmia r0!,{r3}
.Lhalf\@:
 beq .Ldone\@
 lsls r2,r2,#1
 bcc .Lone\@
 ldrh r3,[r1]
 strh r3,[r0]
 beq .Ldone\@
 adds r0,#2
 adds r1,#2
.Lone\@:
 ldrb r3,[r1]
 strb r3,[r0]
.Ldone\@:
 pop {r4,r5,r6}
 mov r0,r12
 bx lr
.Lpopbytes\@:
 pop {r4,r5,r6}
.Lbytes\name:
 cmp r2,#0
 beq .Lreturn\@
.Lbyte\@:
 ldrb r3,[r1]
 strb r3,[r0]
 adds r0,#1
 adds r1,#1
 subs r2,#1
 bne .Lbyte\@
.Lreturn\@:
 mov r0,r12
 bx lr
.Lcase3\@:
 merge \name,3,\unroll
.Lcase2\@:
 merge \name,2,\unroll
.Lcase1\@:
 merge \name,1,\unroll
.Lsmall\@:
 cmp r2,#0
 beq .Lret\@
 cmp r2,#2
 bhi .Lcomputed\@
 ldrb r3,[r1]
 strb r3,[r0]
 cmp r2,#1
 beq .Lret\@
 ldrb r3,[r1,#1]
 strb r3,[r0,#1]
.Lret\@:
 bx lr
.Lcomputed\@:
 adr r3,.Lend\@
 lsls r2,r2,#2
 subs r3,r3,r2
 adds r3,#1
 bx r3
 .balign 4
 .rept 7
 /* Explicit sequence below; assembler has no descending .rept variable. */
 .endr
 ldrb r3,[r1,#6]
 strb r3,[r0,#6]
 ldrb r3,[r1,#5]
 strb r3,[r0,#5]
 ldrb r3,[r1,#4]
 strb r3,[r0,#4]
 ldrb r3,[r1,#3]
 strb r3,[r0,#3]
 ldrb r3,[r1,#2]
 strb r3,[r0,#2]
 ldrb r3,[r1,#1]
 strb r3,[r0,#1]
 ldrb r3,[r1]
 strb r3,[r0]
.Lend\@:
 bx lr
end \name
.endm
m0copy own16,0
m0copy own64,1
#else
.cpu cortex-m4
/* Both variants align destination for STM; source may be unaligned and is
 * read through ordinary LDRs. Variant 64 amortizes loop overhead fourfold. */
.macro m4copy name, unroll
function \name
 cmp r2,#4
 blo .Ltiny\@
 cmp r2,#16
 blo .Lshort\@
 mov r12,r0
 push {r4,r5,r6}
.Lalign\@:
 tst r0,#3
 beq .Lbulk\@
 ldrb r3,[r1],#1
 strb r3,[r0],#1
 subs r2,#1
 b .Lalign\@
.Lbulk\@:
 .if \unroll
 subs r2,#64
 blo .Lfix16\@
.L64\@:
 .rept 4
 ldr r3,[r1]
 ldr r4,[r1,#4]
 ldr r5,[r1,#8]
 ldr r6,[r1,#12]
 adds r1,#16
 stmia r0!,{r3,r4,r5,r6}
 .endr
 subs r2,#64
 bhs .L64\@
.Lfix16\@:
 adds r2,#48
 .else
 subs r2,#16
 .endif
 blo .Ltail\@
.L16\@:
 ldr r3,[r1]
 ldr r4,[r1,#4]
 ldr r5,[r1,#8]
 ldr r6,[r1,#12]
 adds r1,#16
 stmia r0!,{r3,r4,r5,r6}
 subs r2,#16
 bhs .L16\@
.Ltail\@:
 adds r2,#16
 pop {r4,r5,r6}
 b .Lwords\@
.Lshort\@:
 mov r12,r0
.Lwords\@:
 cmp r2,#4
 blo .Lbytes\@
.Lword\@:
 ldr r3,[r1],#4
 str r3,[r0],#4
 subs r2,#4
 cmp r2,#4
 bhs .Lword\@
.Lbytes\@:
 cbz r2,.Ldone\@
.Lbyte\@:
 ldrb r3,[r1],#1
 strb r3,[r0],#1
 subs r2,#1
 bne .Lbyte\@
.Ldone\@:
 mov r0,r12
 bx lr
.Ltiny\@:
 cmp r2,#0
 beq .Lret\@
 ldrb r3,[r1]
 strb r3,[r0]
 cmp r2,#1
 beq .Lret\@
 ldrb r3,[r1,#1]
 strb r3,[r0,#1]
 cmp r2,#2
 beq .Lret\@
 ldrb r3,[r1,#2]
 strb r3,[r0,#2]
.Lret\@:
 bx lr
end \name
.endm
m4copy own16,0
m4copy own64,1
#endif
