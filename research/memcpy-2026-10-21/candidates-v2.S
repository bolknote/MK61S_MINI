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
 cmp r2,#2
 bhi .LnotTiny\@
 cmp r2,#0
 beq .LtinyRet\@
 ldrb r3,[r1]
 strb r3,[r0]
 cmp r2,#1
 beq .LtinyRet\@
 ldrb r3,[r1,#1]
 strb r3,[r0,#1]
.LtinyRet\@:
 bx lr
.LnotTiny\@:
 cmp r2,#8
 bhs .Llarge\@
 adr r3,.LsmallEnd\@
 lsls r2,r2,#2
 subs r3,r3,r2
 adds r3,#1
 bx r3
 .balign 4
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
.LsmallEnd\@:
 bx lr
.Llarge\@:
 mov r12,r0
 movs r3,r0
 eors r3,r1
 lsls r3,r3,#30
 bne .Lmismatch\@
 push {r4,r5,r6}
 lsls r3,r0,#31
 bpl .LalignHalf\@
 ldrb r3,[r1]
 strb r3,[r0]
 adds r0,#1
 adds r1,#1
 subs r2,#1
.LalignHalf\@:
 lsls r3,r0,#30
 bpl .Lwords\@
 ldrh r3,[r1]
 strh r3,[r0]
 adds r0,#2
 adds r1,#2
 subs r2,#2
 b .Lwords\@
.Lmismatch\@:
 cmp r2,#16
 blo .Lreverse\@
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
 cmp r3,#1
 beq .Lcase3\@
 cmp r3,#2
 bne .Lnot2\@
 b .Lcase2\@
.Lnot2\@:
 b .Lcase1\@
.Lreverse\@:
 subs r2,#1
 ldrb r3,[r1,r2]
 strb r3,[r0,r2]
 bne .Lreverse\@
 bx lr
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
end \name
.endm
m0copy own16,0
m0copy own64,1
#else
.cpu cortex-m4
/* align_source=0 uses aligned STM, align_source=1 uses aligned LDM.
 * Small spans use bounded head/tail copies; memcpy permits repeated writes. */
.macro block align_source
 .if \align_source
 ldmia r1!,{r3,r4,r5,r6}
 str r3,[r0]
 str r4,[r0,#4]
 str r5,[r0,#8]
 str r6,[r0,#12]
 adds r0,#16
 .else
 ldr r3,[r1]
 ldr r4,[r1,#4]
 ldr r5,[r1,#8]
 ldr r6,[r1,#12]
 adds r1,#16
 stmia r0!,{r3,r4,r5,r6}
 .endif
.endm
.macro m4copy name, align_source
function \name
 cmp r2,#4
 blo .Ltiny\@
 cmp r2,#32
 bhi .Llarge\@
 cmp r2,#8
 bhs .L8\@
 ldr r3,[r1]
 str r3,[r0]
 subs r2,#4
 ldr r3,[r1,r2]
 str r3,[r0,r2]
 bx lr
.L8\@:
 cmp r2,#16
 bhs .L16short\@
 ldr r3,[r1]
 str r3,[r0]
 ldr r3,[r1,#4]
 str r3,[r0,#4]
 subs r2,#8
 add r1,r2
 add r2,r0
 ldr r3,[r1]
 str r3,[r2]
 ldr r3,[r1,#4]
 str r3,[r2,#4]
 bx lr
.L16short\@:
 push {r4,r5}
 ldr r3,[r1]
 ldr r4,[r1,#4]
 ldr r5,[r1,#8]
 str r3,[r0]
 str r4,[r0,#4]
 str r5,[r0,#8]
 ldr r3,[r1,#12]
 str r3,[r0,#12]
 subs r2,#16
 add r1,r2
 add r2,r0
 ldr r3,[r1]
 ldr r4,[r1,#4]
 ldr r5,[r1,#8]
 str r3,[r2]
 str r4,[r2,#4]
 str r5,[r2,#8]
 ldr r3,[r1,#12]
 str r3,[r2,#12]
 pop {r4,r5}
 bx lr
.Llarge\@:
 mov r12,r0
 push {r4,r5,r6}
 .if \align_source
 ands r3,r1,#3
 .else
 ands r3,r0,#3
 .endif
 beq .Lbulk\@
 ldr r4,[r1]
 str r4,[r0]
 rsb r3,r3,#4
 add r0,r3
 add r1,r3
 subs r2,r3
.Lbulk\@:
 subs r2,#64
 blo .Lfix16\@
.L64\@:
 .rept 4
 block \align_source
 .endr
 subs r2,#64
 bhs .L64\@
.Lfix16\@:
 adds r2,#48
 blo .Ltail\@
.L16\@:
 block \align_source
 subs r2,#16
 bhs .L16\@
.Ltail\@:
 adds r2,#16
 pop {r4,r5,r6}
 cmp r2,#8
 blo .Lfour\@
 ldr r3,[r1],#4
 str r3,[r0],#4
 ldr r3,[r1],#4
 str r3,[r0],#4
 subs r2,#8
.Lfour\@:
 cmp r2,#4
 blo .Lbytes\@
 ldr r3,[r1],#4
 str r3,[r0],#4
 subs r2,#4
.Lbytes\@:
 cbz r2,.Ldone\@
 ldrb r3,[r1]
 strb r3,[r0]
 cmp r2,#1
 beq .Ldone\@
 ldrb r3,[r1,#1]
 strb r3,[r0,#1]
 cmp r2,#2
 beq .Ldone\@
 ldrb r3,[r1,#2]
 strb r3,[r0,#2]
.Ldone\@:
 mov r0,r12
 bx lr
.Ltiny\@:
 cbz r2,.Lret\@
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
