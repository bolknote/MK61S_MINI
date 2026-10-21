/* Bounded directional copies never overwrite unread source bytes.
 * Only naturally aligned accesses are used on ARMv6-M. */
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
function runtime_move
 ldr r3,=bench_runtime
 ldr r3,[r3]
 ldr r3,[r3,#96]
 bx r3
 .ltorg
end runtime_move
function runtime_selected
 ldr r3,=bench_selected_runtime
 ldr r3,[r3]
 ldr r3,[r3,#96]
 bx r3
 .ltorg
end runtime_selected
function control_move
 bx lr
end control_move
#if defined(__ARM_ARCH_6M__)
.cpu cortex-m0plus
.macro merge tag,k,back
.Lmerge\tag\@:
 movs r5,#0
 .if \back
 subs r1,#\k
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
 lsls r5,r5,#(32-\k*8)
 .else
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
 .endif
 subs r2,#(4+\k)
 cmp r2,#12
 blo .Lmword\@
 subs r2,#12
.Lm16\@:
 .rept 4
 .if \back
 subs r1,#4
 ldr r3,[r1]
 lsrs r4,r3,#(\k*8)
 orrs r4,r5
 subs r0,#4
 str r4,[r0]
 lsls r5,r3,#(32-\k*8)
 .else
 ldmia r1!,{r3}
 lsls r4,r3,#(\k*8)
 orrs r4,r5
 stmia r0!,{r4}
 lsrs r5,r3,#(32-\k*8)
 .endif
 .endr
 subs r2,#16
 bhs .Lm16\@
 adds r2,#12
 bcc .Lmend\@
.Lmword\@:
 .if \back
 subs r1,#4
 ldr r3,[r1]
 lsrs r4,r3,#(\k*8)
 orrs r4,r5
 subs r0,#4
 str r4,[r0]
 lsls r5,r3,#(32-\k*8)
 .else
 ldmia r1!,{r3}
 lsls r4,r3,#(\k*8)
 orrs r4,r5
 stmia r0!,{r4}
 lsrs r5,r3,#(32-\k*8)
 .endif
 subs r2,#4
 bhs .Lmword\@
.Lmend\@:
 .rept \k
 .if \back
 lsrs r3,r5,#24
 subs r0,#1
 strb r3,[r0]
 lsls r5,r5,#8
 .else
 strb r5,[r0]
 adds r0,#1
 lsrs r5,r5,#8
 .endif
 .endr
 adds r2,#4
 pop {r4,r5,r6}
 b .Lbytes\tag
.endm
.macro directional name,tag,back,unroll
 .if \back && !\unroll
 adds r0,r0,r2
 adds r1,r1,r2
 .endif
 cmp r2,#8
 .if !\back && \unroll
 blo .LbyteFast\tag
 .elseif \back && \unroll
 blo .LbyteStart\tag
 .else
 blo .Lbytes\tag
 .endif
 movs r3,r0
 eors r3,r1
 lsls r3,r3,#30
 bne .Lmismatch\tag
 push {r4,r5,r6}
 .if \back && \unroll
 adds r0,r0,r2
 adds r1,r1,r2
 .endif
 lsls r3,r0,#31
 bpl .LalignHalf\tag
 .if \back
 subs r0,#1
 subs r1,#1
 .endif
 ldrb r3,[r1]
 strb r3,[r0]
 .if !\back
 adds r0,#1
 adds r1,#1
 .endif
 subs r2,#1
.LalignHalf\tag:
 lsls r3,r0,#30
 bpl .Lwords\tag
 .if \back
 subs r0,#2
 subs r1,#2
 .endif
 ldrh r3,[r1]
 strh r3,[r0]
 .if !\back
 adds r0,#2
 adds r1,#2
 .endif
 subs r2,#2
 b .Lwords\tag
.Lmismatch\tag:
 cmp r2,#24
 .if !\back && \unroll
 blo .LbyteFast\tag
 .elseif \back && \unroll
 blo .LbyteStart\tag
 .else
 blo .Lbytes\tag
 .endif
 push {r4,r5,r6}
 .if \back && \unroll
 adds r0,r0,r2
 adds r1,r1,r2
 .endif
 movs r4,#3
.Lalign\tag:
 tst r0,r4
 beq .Laligned\tag
 .if \back
 subs r0,#1
 subs r1,#1
 .endif
 ldrb r3,[r1]
 strb r3,[r0]
 .if !\back
 adds r0,#1
 adds r1,#1
 .endif
 subs r2,#1
 b .Lalign\tag
.Laligned\tag:
 movs r3,r1
 ands r3,r4
 .if \back
 cmp r3,#3
 .else
 cmp r3,#1
 .endif
 bne .Lnot3\tag
 b .Lcase3\tag
.Lnot3\tag:
 cmp r3,#2
 bne .Lnot2\tag
 b .Lcase2\tag
.Lnot2\tag:
 b .Lcase1\tag
.Lwords\tag:
 subs r2,#16
 blo .Ltail\tag
 .if \unroll
 cmp r2,#48
 blo .L16\tag
 subs r2,#48
.L64\tag:
 .rept 4
 .if \back
 subs r1,#16
 ldmia r1!,{r3,r4,r5,r6}
 subs r1,#16
 subs r0,#16
 stmia r0!,{r3,r4,r5,r6}
 subs r0,#16
 .else
 ldmia r1!,{r3,r4,r5,r6}
 stmia r0!,{r3,r4,r5,r6}
 .endif
 .endr
 subs r2,#64
 bhs .L64\tag
 adds r2,#48
 bcc .Ltail\tag
 .endif
.L16\tag:
 .if \back
 subs r1,#16
 ldmia r1!,{r3,r4,r5,r6}
 subs r1,#16
 subs r0,#16
 stmia r0!,{r3,r4,r5,r6}
 subs r0,#16
 .else
 ldmia r1!,{r3,r4,r5,r6}
 stmia r0!,{r3,r4,r5,r6}
 .endif
 subs r2,#16
 bhs .L16\tag
.Ltail\tag:
 adds r2,#16
 cmp r2,#4
 blo .Lpop\tag
.Lword\tag:
 .if \back
 subs r1,#4
 ldr r3,[r1]
 subs r0,#4
 str r3,[r0]
 .else
 ldmia r1!,{r3}
 stmia r0!,{r3}
 .endif
 subs r2,#4
 cmp r2,#4
 bhs .Lword\tag
.Lpop\tag:
 pop {r4,r5,r6}
.Lbytes\tag:
 cmp r2,#0
 beq .Lreturn\tag
 .if \back && \unroll
 /* Indexing from the remaining span's start saves two pointer decrements.
  * LDRB/STRB preserve the flags from SUBS, so no extra CMP is necessary. */
 subs r0,r0,r2
 subs r1,r1,r2
.LbyteStart\tag:
.Lbyte\tag:
 subs r2,#1
 ldrb r3,[r1,r2]
 strb r3,[r0,r2]
 bne .Lbyte\tag
 .else
.Lbyte\tag:
 .if \back
 subs r0,#1
 subs r1,#1
 .endif
 ldrb r3,[r1]
 strb r3,[r0]
 .if !\back
 adds r0,#1
 adds r1,#1
 .endif
 subs r2,#1
 bne .Lbyte\tag
 .endif
.Lreturn\tag:
 mov r0,r12
 bx lr
 .if !\back && \unroll
 /* Only enter for complete small spans (n > 4), keeping the ordinary
  * 0..3-byte word-loop tails free of the four-byte loop setup. */
.LbyteFast\tag:
 subs r2,#4
.LbyteFour\tag:
 ldrb r3,[r1]
 strb r3,[r0]
 ldrb r3,[r1,#1]
 strb r3,[r0,#1]
 ldrb r3,[r1,#2]
 strb r3,[r0,#2]
 ldrb r3,[r1,#3]
 strb r3,[r0,#3]
 adds r1,#4
 adds r0,#4
 subs r2,#4
 bhs .LbyteFour\tag
 adds r2,#4
 b .Lbytes\tag
 .endif
.Lcase3\tag:
 merge \tag,3,\back
.Lcase2\tag:
 merge \tag,2,\back
.Lcase1\tag:
 merge \tag,1,\back
.endm
.macro move name,unroll
function \name
 cmp r2,#0
 beq .Lnoop\name
 cmp r0,r1
 bne .Lnonzero\name
.Lnoop\name:
 bx lr
.Lnonzero\name:
 .if \unroll
 cmp r2,#4
 bhi .Lstart\name
 cmp r2,#1
 beq .Lone\name
 cmp r2,#2
 beq .Ltwo\name
 cmp r2,#3
 beq .Lthree\name
 push {r4}
 ldrb r3,[r1]
 ldrb r2,[r1,#1]
 ldrb r4,[r1,#2]
 ldrb r1,[r1,#3]
 strb r3,[r0]
 strb r2,[r0,#1]
 strb r4,[r0,#2]
 strb r1,[r0,#3]
 pop {r4}
 bx lr
.Lthree\name:
 ldrb r3,[r1]
 ldrb r2,[r1,#1]
 ldrb r1,[r1,#2]
 strb r3,[r0]
 strb r2,[r0,#1]
 strb r1,[r0,#2]
 bx lr
.Ltwo\name:
 ldrb r3,[r1]
 ldrb r1,[r1,#1]
 strb r3,[r0]
 strb r1,[r0,#1]
 bx lr
.Lone\name:
 ldrb r3,[r1]
 strb r3,[r0]
 bx lr
 .endif
.Lstart\name:
 mov r12,r0
 cmp r0,r1
 blo .Lforward\name
 .if \unroll
 /* Disjoint spans can use the cheaper forward loop (including Flash input). */
 subs r3,r0,r1
 cmp r3,r2
 bhs .Lforward\name
 .endif
 b .Lbackward\name
.Lforward\name:
 directional \name,f\name,0,\unroll
.Lbackward\name:
 directional \name,b\name,1,\unroll
end \name
.endm
#else
.cpu cortex-m4
.macro block back
 .if \back
 ldmdb r1!,{r3,r4,r5,r6}
 subs r0,#16
 .else
 ldmia r1!,{r3,r4,r5,r6}
 .endif
 str r3,[r0]
 str r4,[r0,#4]
 str r5,[r0,#8]
 str r6,[r0,#12]
 .if !\back
 adds r0,#16
 .endif
.endm
.macro directional name,tag,back,unroll
 .if \back
 add r0,r2
 add r1,r2
 .endif
 tst r1,#1
 beq .Lhalf\tag
 .if \back
 ldrb r3,[r1,#-1]!
 strb r3,[r0,#-1]!
 .else
 ldrb r3,[r1],#1
 strb r3,[r0],#1
 .endif
 subs r2,#1
.Lhalf\tag:
 tst r1,#2
 beq .Lbulk\tag
 .if \back
 ldrh r3,[r1,#-2]!
 strh r3,[r0,#-2]!
 .else
 ldrh r3,[r1],#2
 strh r3,[r0],#2
 .endif
 subs r2,#2
.Lbulk\tag:
 .if \unroll
 subs r2,#64
 blo .Lfix16\tag
.L64\tag:
 .rept 4
 block \back
 .endr
 subs r2,#64
 bhs .L64\tag
.Lfix16\tag:
 adds r2,#48
 blo .Ltail\tag
 .else
 subs r2,#16
 blo .Ltail\tag
 .endif
.L16\tag:
 block \back
 subs r2,#16
 bhs .L16\tag
.Ltail\tag:
 adds r2,#16
 pop {r4,r5,r6}
 cmp r2,#4
 blo .Lbytes\tag
.Lword\tag:
 .if \back
 ldr r3,[r1,#-4]!
 str r3,[r0,#-4]!
 .else
 ldr r3,[r1],#4
 str r3,[r0],#4
 .endif
 subs r2,#4
 cmp r2,#4
 bhs .Lword\tag
.Lbytes\tag:
 cbz r2,.Lreturn\tag
.Lbyte\tag:
 .if \back
 ldrb r3,[r1,#-1]!
 strb r3,[r0,#-1]!
 .else
 ldrb r3,[r1],#1
 strb r3,[r0],#1
 .endif
 subs r2,#1
 bne .Lbyte\tag
.Lreturn\tag:
 mov r0,r12
 bx lr
.endm
.macro move name,unroll
function \name
 cbz r2,.Lnoop\name
 cmp r0,r1
 beq .Lnoop\name
 cmp r2,#4
 blo .Ltiny\name
 cmp r2,#8
 bhi .Lmedium\name
 ldr r3,[r1]
 subs r2,#4
 ldr r1,[r1,r2]
 str r3,[r0]
 str r1,[r0,r2]
 bx lr
.Ltiny\name:
 cmp r2,#1
 beq .Lone\name
 ldrh r3,[r1]
 cmp r2,#2
 beq .Ltwo\name
 ldrb r1,[r1,#2]
 strb r1,[r0,#2]
.Ltwo\name:
 strh r3,[r0]
 bx lr
.Lone\name:
 ldrb r3,[r1]
 strb r3,[r0]
.Lnoop\name:
 bx lr
.Lmedium\name:
 push {r4,r5,r6}
 cmp r2,#16
 bhi .Lwide\name
 ldr r3,[r1]
 ldr r4,[r1,#4]
 subs r2,#8
 add r1,r2
 ldr r5,[r1]
 ldr r6,[r1,#4]
 add r2,r0
 str r3,[r0]
 str r4,[r0,#4]
 str r5,[r2]
 str r6,[r2,#4]
 pop {r4,r5,r6}
 bx lr
.Lwide\name:
 cmp r2,#33
 bhi .Llarge\name
 /* Head/tail words plus the middle byte cover 17..33 bytes. All are
  * captured before stores, including when the source overlaps by one byte. */
 push {r7,r8,r9,r10}
 ldrb r12,[r1,#16]
 ldr r3,[r1]
 ldr r4,[r1,#4]
 ldr r5,[r1,#8]
 ldr r6,[r1,#12]
 subs r2,#16
 add r1,r2
 ldr r7,[r1]
 ldr r8,[r1,#4]
 ldr r9,[r1,#8]
 ldr r10,[r1,#12]
 add r2,r0
 str r3,[r0]
 str r4,[r0,#4]
 str r5,[r0,#8]
 str r6,[r0,#12]
 str r7,[r2]
 str r8,[r2,#4]
 str r9,[r2,#8]
 str r10,[r2,#12]
 strb r12,[r0,#16]
 pop {r7,r8,r9,r10}
 pop {r4,r5,r6}
 bx lr
.Llarge\name:
 mov r12,r0
 cmp r0,r1
 bhi .Lbackward\name
 directional \name,f\name,0,\unroll
.Lbackward\name:
 directional \name,b\name,1,\unroll
end \name
.endm
#endif
move own16,0
move own64,1
