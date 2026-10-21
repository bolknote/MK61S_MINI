/* Bounded lexicographic comparison of unsigned bytes. Return value has the
 * ISO C sign; a mismatching word is byte-reversed before unsigned comparison.
 * ARMv6-M uses naturally aligned loads only. No source bytes are written. */
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
function runtime_compare
 ldr r3,=bench_runtime
 ldr r3,[r3]
 ldr r3,[r3,#100]
 bx r3
 .ltorg
end runtime_compare
function runtime_selected
 ldr r3,=bench_selected_runtime
 ldr r3,[r3]
 ldr r3,[r3,#100]
 bx r3
 .ltorg
end runtime_selected
function control_compare
 movs r0,#0
 bx lr
end control_compare

#if defined(__ARM_ARCH_6M__)
.cpu cortex-m0plus
.macro byte_pair tag,offset
 ldrb r3,[r0,#\offset]
 ldrb r4,[r1,#\offset]
 subs r3,r3,r4
 bne .LbyteDiff\tag
.endm
.macro word_pair tag
 ldmia r0!,{r3}
 ldmia r1!,{r4}
 cmp r3,r4
 bne .LwordDiff\tag
.endm
.macro merged_pair tag,h
 ldmia r0!,{r3}
 ldmia r1!,{r6}
 lsls r4,r6,#(\h*8)
 orrs r4,r5
 cmp r3,r4
 bne .LmergeDiff\tag\h
 lsrs r5,r6,#(32-\h*8)
.endm
.macro merge tag,h
.Lmerge\tag\h:
 push {r5,r6}
 .if \h==1
 ldrb r5,[r1]
 .elseif \h==2
 ldrh r5,[r1]
 .else
 ldrb r5,[r1]
 adds r1,#1
 ldrh r4,[r1]
 lsls r4,r4,#8
 orrs r5,r4
 .endif
 .if \h==3
 adds r1,#2
 .else
 adds r1,#\h
 .endif
 subs r2,#(4+\h)
 cmp r2,#12
 blo .LmergeWord\tag\h
 subs r2,#12
.Lmerge16\tag\h:
 .rept 4
 merged_pair \tag,\h
 .endr
 subs r2,#16
 bhs .Lmerge16\tag\h
 adds r2,#12
 bcc .LmergeTail\tag\h
.LmergeWord\tag\h:
 merged_pair \tag,\h
 subs r2,#4
 bhs .LmergeWord\tag\h
.LmergeTail\tag\h:
 /* The carry contains exactly h bytes already read inside the span. */
 .rept \h
 ldrb r3,[r0]
 uxtb r4,r5
 subs r3,r3,r4
 bne .LmergeByteDiff\tag\h
 adds r0,#1
 lsrs r5,r5,#8
 .endr
 adds r2,#4
 pop {r5,r6}
 b .Ltail\tag
.LmergeDiff\tag\h:
 pop {r5,r6}
 b .LwordDiff\tag
.LmergeByteDiff\tag\h:
 pop {r5,r6}
 b .LbyteDiff\tag
.endm
.macro compare name,words
function \name
 cmp r2,#0
 beq .Lzero\name
 cmp r0,r1
 beq .Lzero\name
 mov r12,r0
 ldrb r0,[r0]
 ldrb r3,[r1]
 subs r0,r0,r3
 bne .Lreturn\name
 cmp r2,#1
 beq .Lreturn\name
 mov r0,r12
 cmp r2,#8
 blo .Lsmall\name
 movs r3,r0
 eors r3,r1
 lsls r3,r3,#30
 beq .Lprepare\name
 .if \words>1
 cmp r2,#24
 bhs .Lprepare\name
 .endif
.Lsmall\name:
 push {r4}
 /* Byte zero was checked before any register save or word-loop setup. */
 adds r0,#1
 adds r1,#1
 subs r2,#1
 .if \words>1
 cmp r2,#4
 blo .LsmallTail\name
.LsmallFour\name:
 byte_pair \name,0
 byte_pair \name,1
 byte_pair \name,2
 byte_pair \name,3
 adds r0,#4
 adds r1,#4
 subs r2,#4
 cmp r2,#4
 bhs .LsmallFour\name
.LsmallTail\name:
 cmp r2,#0
 beq .Lequal\name
 .endif
.LsmallByte\name:
 byte_pair \name,0
 adds r0,#1
 adds r1,#1
 subs r2,#1
 bne .LsmallByte\name
.Lequal\name:
 movs r3,#0
.LbyteDiff\name:
 movs r0,r3
 pop {r4}
.Lreturn\name:
 bx lr
.Lzero\name:
 movs r0,#0
 bx lr
.Lprepare\name:
 push {r4}
 lsls r3,r0,#30
 beq .Laligned\name
 /* Skip the already checked first byte before aligning the left span. */
 adds r0,#1
 adds r1,#1
 subs r2,#1
 lsls r3,r0,#30
 beq .Laligned\name
.Lprefix\name:
 byte_pair \name,0
 adds r0,#1
 adds r1,#1
 subs r2,#1
 lsls r3,r0,#30
 bne .Lprefix\name
.Laligned\name:
 .if \words>1
 lsls r3,r1,#30
 beq .Lwords\name
 movs r3,#3
 ands r3,r1
 cmp r3,#1
 bne .Lnot3\name
 b .Lmerge\name\()3
.Lnot3\name:
 cmp r3,#2
 bne .Lnot2\name
 b .Lmerge\name\()2
.Lnot2\name:
 b .Lmerge\name\()1
 .else
 b .Lwords\name
 .endif
.LwordDiff\name:
 rev r0,r3
 rev r1,r4
 cmp r0,r1
 sbcs r0,r0
 movs r1,#1
 orrs r0,r1
 pop {r4}
 bx lr
.Lwords\name:
 .if \words>1
 cmp r2,#(4*\words)
 .if \words>4
 blo .Lmedium\name
 .else
 blo .Lword\name
 .endif
.Lbulk\name:
 .rept \words
 word_pair \name
 .endr
 subs r2,#(4*\words)
 cmp r2,#(4*\words)
 bhs .Lbulk\name
 .if \words>4
.Lmedium\name:
 cmp r2,#16
 blo .LwordCheck\name
.L16\name:
 .rept 4
 word_pair \name
 .endr
 subs r2,#16
 cmp r2,#16
 bhs .L16\name
.LwordCheck\name:
 .endif
 cmp r2,#4
 blo .Ltail\name
 .endif
.Lword\name:
 word_pair \name
 subs r2,#4
 cmp r2,#4
 bhs .Lword\name
.Ltail\name:
 cmp r2,#0
 beq .LwordEqual\name
.LtailByte\name:
 ldrb r3,[r0]
 ldrb r4,[r1]
 subs r3,r3,r4
 bne .LtailDiff\name
 adds r0,#1
 adds r1,#1
 subs r2,#1
 bne .LtailByte\name
.LwordEqual\name:
 movs r3,#0
.LtailDiff\name:
 movs r0,r3
 pop {r4}
 bx lr
 .if \words>1
 merge \name,3
 merge \name,2
 merge \name,1
 .endif
end \name
.endm
#else
.cpu cortex-m4
.macro word_pair tag,offset
 ldr r3,[r0,#\offset]
 ldr cmp_word,[r1,#\offset]
 cmp r3,cmp_word
 bne .LwordDiff\tag
.endm
.macro byte_pair tag,offset,tail=0
 ldrb r3,[r0,#\offset]
 ldrb r12,[r1,#\offset]
 subs r3,r3,r12
 .if \tail
 bne .LtailDiff\tag
 .else
 bne .LbyteDiff\tag
 .endif
.endm
.macro compare name,words,low=0
function \name
 .if \low
 cmp_word .req r4
 .else
 cmp_word .req r12
 .endif
 cbz r2,.Lzero\name
 cmp r0,r1
 beq .Lzero\name
 byte_pair \name,0
 cmp r2,#1
 beq .Lzero\name
 cmp r2,#4
 bhs .LheadWord\name
 byte_pair \name,1
 cmp r2,#2
 beq .Lzero\name
 byte_pair \name,2
.LbyteDiff\name:
 mov r0,r3
 bx lr
.Lzero\name:
 movs r0,#0
 bx lr
.LheadWord\name:
 .if \low
 push {r4}
 .endif
 /* Inspect the head before any bulk dispatch or alignment arithmetic. */
 word_pair \name,0
 cmp r2,#8
 bhs .LheadEight\name
 subs r2,#4
 beq .LwordZero\name
 ldr r3,[r0,r2]
 ldr cmp_word,[r1,r2]
 cmp r3,cmp_word
 beq .LwordZero\name
.LwordDiff\name:
 rev r0,r3
 rev r1,cmp_word
 cmp r0,r1
 sbcs r0,r0
 orr r0,r0,#1
 .if \low
 pop {r4}
 .endif
 bx lr
.LwordZero\name:
 movs r0,#0
 .if \low
 pop {r4}
 .endif
 bx lr
.LheadEight\name:
 word_pair \name,4
 cmp r2,#16
 bhi .Llarge\name
 /* Exact tail pair covers 8..16 together with the already checked head. */
 subs r2,#8
 beq .LwordZero\name
 ldr r3,[r0,r2]
 ldr cmp_word,[r1,r2]
 cmp r3,cmp_word
 bne .LwordDiff\name
 adds r2,#4
 ldr r3,[r0,r2]
 ldr cmp_word,[r1,r2]
 cmp r3,cmp_word
 bne .LwordDiff\name
 b .LwordZero\name
.Llarge\name:
 .if \words>1
 /* Align inside the checked head: duplicate at most three bytes, skip none. */
 and r3,r0,#3
 rsb r3,r3,#8
 adds r0,r0,r3
 adds r1,r1,r3
 subs r2,r2,r3
 .else
 adds r0,#8
 adds r1,#8
 subs r2,#8
 .endif
.Lwords\name:
 .if \words>1
 cmp r2,#(4*\words)
 .if \words>4
 blo .Lmedium\name
 .else
 blo .Lword\name
 .endif
.Lbulk\name:
 .set offset,0
 .rept \words
 word_pair \name,offset
 .set offset,offset+4
 .endr
 adds r0,#(4*\words)
 adds r1,#(4*\words)
 subs r2,#(4*\words)
 cmp r2,#(4*\words)
 bhs .Lbulk\name
 .if \words>4
.Lmedium\name:
 cmp r2,#16
 blo .LwordCheck\name
.L16\name:
 word_pair \name,0
 word_pair \name,4
 word_pair \name,8
 word_pair \name,12
 adds r0,#16
 adds r1,#16
 subs r2,#16
 cmp r2,#16
 bhs .L16\name
.LwordCheck\name:
 .endif
 cmp r2,#4
 blo .Ltail\name
 .endif
.Lword\name:
 word_pair \name,0
 adds r0,#4
 adds r1,#4
 subs r2,#4
 cmp r2,#4
 bhs .Lword\name
.Ltail\name:
 cmp r2,#0
 beq .LwordZero\name
 byte_pair \name,0,1
 cmp r2,#1
 beq .LwordZero\name
 byte_pair \name,1,1
 cmp r2,#2
 beq .LwordZero\name
 byte_pair \name,2,1
.LtailDiff\name:
 mov r0,r3
 .if \low
 pop {r4}
 .endif
 bx lr
 .unreq cmp_word
end \name
.endm
#endif
compare own4,1
compare own16,4
compare own64,16
#if !defined(__ARM_ARCH_6M__)
compare own_low64,16,1
#endif
.section .note.GNU-stack,"",%progbits
