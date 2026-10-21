/* ARMv6-M experiments. ISO C memset: r0=destination, r1=value, r2=size.
 * No unaligned halfword/word stores. All functions preserve r4-r11 and SP. */
.syntax unified
.cpu cortex-m0plus
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

function runtime_old
 push {r4}
 ldr r4,=bench_runtime
 ldr r4,[r4]
 ldr r4,[r4,#92]
 mov r12,r4
 pop {r4}
 bx r12
 .ltorg
end runtime_old

function runtime_r3
 ldr r3,=bench_runtime
 ldr r3,[r3]
 ldr r3,[r3,#92]
 bx r3
 .ltorg
end runtime_r3

function rom_cached
 ldr r3,=bench_rom
 ldr r3,[r3]
 bx r3
 .ltorg
end rom_cached

function control_fill
 bx lr
end control_fill

/* Two identical dispatch/alignment/tail paths; only the bulk loop differs.
 * The 64-byte variant amortizes the branch over four STMIA instructions. */
.macro owned name, unroll
function \name
 cmp r2,#8
 blo .Lsmall\@
 mov r12,r0
 uxtb r1,r1
 lsls r3,r1,#8
 orrs r1,r3
 lsls r3,r0,#31
 bpl .Lhalf\@
 strb r1,[r0]
 adds r0,#1
 subs r2,#1
.Lhalf\@:
 lsls r3,r0,#30
 bpl .Lword\@
 strh r1,[r0]
 adds r0,#2
 subs r2,#2
.Lword\@:
 rev r3,r1
 orrs r1,r3
 movs r3,r1
 cmp r2,#16
 blo .Ltail\@
 push {r4,r5}
 movs r4,r1
 movs r5,r1
.if \unroll
 cmp r2,#64
 blo .Lbulk16\@
.Lbulk64\@:
 stmia r0!,{r1,r3,r4,r5}
 stmia r0!,{r1,r3,r4,r5}
 stmia r0!,{r1,r3,r4,r5}
 stmia r0!,{r1,r3,r4,r5}
 subs r2,#64
 cmp r2,#64
 bhs .Lbulk64\@
 cmp r2,#16
 blo .Lpop\@
.endif
.Lbulk16\@:
 stmia r0!,{r1,r3,r4,r5}
 subs r2,#16
 cmp r2,#16
 bhs .Lbulk16\@
.Lpop\@:
 pop {r4,r5}
.Ltail\@:
 lsls r2,r2,#29
 bcc .Lfour\@
 stmia r0!,{r1,r3}
.Lfour\@:
 lsls r2,r2,#1
 bcc .Ltwo\@
 stmia r0!,{r1}
.Ltwo\@:
 lsls r2,r2,#1
 bcc .Lone\@
 strh r1,[r0]
 adds r0,#2
.Lone\@:
 cmp r2,#0
 bpl .Ldone\@
 strb r1,[r0]
.Ldone\@:
 mov r0,r12
 bx lr
.Lsmall\@:
 cmp r2,#0
 beq .Lreturn\@
 strb r1,[r0]
 cmp r2,#1
 beq .Lreturn\@
 strb r1,[r0,#1]
 cmp r2,#2
 beq .Lreturn\@
 strb r1,[r0,#2]
 cmp r2,#3
 beq .Lreturn\@
 strb r1,[r0,#3]
 cmp r2,#4
 beq .Lreturn\@
 strb r1,[r0,#4]
 cmp r2,#5
 beq .Lreturn\@
 strb r1,[r0,#5]
 cmp r2,#6
 beq .Lreturn\@
 strb r1,[r0,#6]
.Lreturn\@:
 bx lr
end \name
.endm
owned own16,0
owned own64,1

/* Candidate selected for a second hardware pass: a pre-decremented loop
 * avoids comparing the count on every iteration. The short computed branch
 * jumps only into this function's bounded sequence of byte stores. */
function own_fast
 cmp r2,#8
 blo .Lfast_small
 mov r12,r0
 uxtb r1,r1
 lsls r3,r1,#8
 orrs r1,r3
 lsls r3,r0,#31
 bpl .Lfast_half
 strb r1,[r0]
 adds r0,#1
 subs r2,#1
.Lfast_half:
 lsls r3,r0,#30
 bpl .Lfast_word
 strh r1,[r0]
 adds r0,#2
 subs r2,#2
.Lfast_word:
 rev r3,r1
 orrs r1,r3
 movs r3,r1
 subs r2,#16
 blo .Lfast_tail
 push {r4,r5}
 movs r4,r1
 movs r5,r1
 cmp r2,#48
 blo .Lfast_16
 subs r2,#48
.Lfast_64:
 stmia r0!,{r1,r3,r4,r5}
 stmia r0!,{r1,r3,r4,r5}
 stmia r0!,{r1,r3,r4,r5}
 stmia r0!,{r1,r3,r4,r5}
 subs r2,#64
 bhs .Lfast_64
 adds r2,#48
 bcc .Lfast_pop
.Lfast_16:
 stmia r0!,{r1,r3,r4,r5}
 subs r2,#16
 bhs .Lfast_16
.Lfast_pop:
 pop {r4,r5}
.Lfast_tail:
 lsls r2,r2,#29
 bcc .Lfast_four
 stmia r0!,{r1,r3}
.Lfast_four:
 lsls r2,r2,#1
 bcc .Lfast_two
 stmia r0!,{r1}
.Lfast_two:
 beq .Lfast_done
 lsls r2,r2,#1
 bcc .Lfast_one
 strh r1,[r0]
 beq .Lfast_done
 adds r0,#2
.Lfast_one:
 strb r1,[r0]
.Lfast_done:
 mov r0,r12
 bx lr
.Lfast_small:
 cmp r2,#2
 bhi .Lfast_bytes
 cmp r2,#0
 beq .Lfast_return
 strb r1,[r0]
 cmp r2,#1
 beq .Lfast_return
 strb r1,[r0,#1]
.Lfast_return:
 bx lr
.Lfast_bytes:
 adr r3,.Lfast_end
 subs r3,r3,r2
 subs r3,r3,r2
 adds r3,#1
 bx r3
 .balign 4
 nop
 strb r1,[r0,#6]
 strb r1,[r0,#5]
 strb r1,[r0,#4]
 strb r1,[r0,#3]
 strb r1,[r0,#2]
 strb r1,[r0,#1]
 strb r1,[r0]
.Lfast_end:
 bx lr
end own_fast
