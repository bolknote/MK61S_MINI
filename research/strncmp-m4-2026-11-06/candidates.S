.syntax unified
.cpu cortex-m4
.thumb
.text
.balign 4
.global sn_byte1
.type sn_byte1,%function
.thumb_func
sn_byte1:
cbz r2,.Lsn_byte1_zero
mov r12,r0
.Lsn_byte1_loop:
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_byte1_diff
cbz r0,.Lsn_byte1_return
subs r2,#1
bne .Lsn_byte1_loop
.Lsn_byte1_zero:
movs r0,#0
.Lsn_byte1_return:
bx lr
.Lsn_byte1_diff:
subs r0,r3,r0
bx lr
.size sn_byte1,.-sn_byte1
.balign 4
.global sn_byte2
.type sn_byte2,%function
.thumb_func
sn_byte2:
cbz r2,.Lsn_byte2_zero
mov r12,r0
.Lsn_byte2_loop:
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_byte2_diff
cbz r0,.Lsn_byte2_return
subs r2,#1
beq .Lsn_byte2_zero
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_byte2_diff
cbz r0,.Lsn_byte2_return
subs r2,#1
bne .Lsn_byte2_loop
.Lsn_byte2_zero:
movs r0,#0
.Lsn_byte2_return:
bx lr
.Lsn_byte2_diff:
subs r0,r3,r0
bx lr
.size sn_byte2,.-sn_byte2
.balign 4
.global sn_byte4
.type sn_byte4,%function
.thumb_func
sn_byte4:
cbz r2,.Lsn_byte4_zero
mov r12,r0
.Lsn_byte4_loop:
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_byte4_diff
cbz r0,.Lsn_byte4_return
subs r2,#1
beq .Lsn_byte4_zero
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_byte4_diff
cbz r0,.Lsn_byte4_return
subs r2,#1
beq .Lsn_byte4_zero
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_byte4_diff
cbz r0,.Lsn_byte4_return
subs r2,#1
beq .Lsn_byte4_zero
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_byte4_diff
cbz r0,.Lsn_byte4_return
subs r2,#1
bne .Lsn_byte4_loop
.Lsn_byte4_zero:
movs r0,#0
.Lsn_byte4_return:
bx lr
.Lsn_byte4_diff:
subs r0,r3,r0
bx lr
.size sn_byte4,.-sn_byte4
.balign 4
.global sn_dsp4
.type sn_dsp4,%function
.thumb_func
sn_dsp4:
cbnz r2,.Lsn_dsp4_start
movs r0,#0
bx lr
.Lsn_dsp4_start:
mov r12,r0
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_dsp4_diff
cmp r0,#0
beq .Lsn_dsp4_return
subs r2,#1
beq .Lsn_dsp4_zero
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_dsp4_diff
cmp r0,#0
beq .Lsn_dsp4_return
subs r2,#1
beq .Lsn_dsp4_zero
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_dsp4_diff
cmp r0,#0
beq .Lsn_dsp4_return
subs r2,#1
beq .Lsn_dsp4_zero
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_dsp4_diff
cmp r0,#0
beq .Lsn_dsp4_return
subs r2,#1
beq .Lsn_dsp4_zero
eor.w r3,r12,r1
tst r3,#3
bne .Lsn_dsp4_byte
.Lsn_dsp4_peel:
tst r12,#3
beq .Lsn_dsp4_words
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_dsp4_diff
cmp r0,#0
beq .Lsn_dsp4_return
subs r2,#1
beq .Lsn_dsp4_zero
b .Lsn_dsp4_peel
.Lsn_dsp4_words:
push {r4,r5}
mov r4,r12
mov.w r5,#0x01010101
.Lsn_dsp4_wordloop:
cmp r2,#4
blo .Lsn_dsp4_tail
ldr r3,[r4]
ldr r0,[r1]
cmp r3,r0
bne .Lsn_dsp4_tail
uqsub8 r12,r5,r3
cmp r12,#0
bne .Lsn_dsp4_tail
adds r4,#4
adds r1,#4
subs r2,#4
b .Lsn_dsp4_wordloop
.Lsn_dsp4_tail:
mov r12,r4
pop {r4,r5}
.Lsn_dsp4_byte:
cbz r2,.Lsn_dsp4_zero
.Lsn_dsp4_byteloop:
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_dsp4_diff
cbz r0,.Lsn_dsp4_return
subs r2,#1
bne .Lsn_dsp4_byteloop
.Lsn_dsp4_zero:
movs r0,#0
.Lsn_dsp4_return:
bx lr
.Lsn_dsp4_diff:
subs r0,r3,r0
bx lr
.size sn_dsp4,.-sn_dsp4
.balign 4
.global sn_dsp8
.type sn_dsp8,%function
.thumb_func
sn_dsp8:
cbnz r2,.Lsn_dsp8_start
movs r0,#0
bx lr
.Lsn_dsp8_start:
mov r12,r0
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_dsp8_diff
cmp r0,#0
beq .Lsn_dsp8_return
subs r2,#1
beq .Lsn_dsp8_zero
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_dsp8_diff
cmp r0,#0
beq .Lsn_dsp8_return
subs r2,#1
beq .Lsn_dsp8_zero
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_dsp8_diff
cmp r0,#0
beq .Lsn_dsp8_return
subs r2,#1
beq .Lsn_dsp8_zero
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_dsp8_diff
cmp r0,#0
beq .Lsn_dsp8_return
subs r2,#1
beq .Lsn_dsp8_zero
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_dsp8_diff
cmp r0,#0
beq .Lsn_dsp8_return
subs r2,#1
beq .Lsn_dsp8_zero
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_dsp8_diff
cmp r0,#0
beq .Lsn_dsp8_return
subs r2,#1
beq .Lsn_dsp8_zero
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_dsp8_diff
cmp r0,#0
beq .Lsn_dsp8_return
subs r2,#1
beq .Lsn_dsp8_zero
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_dsp8_diff
cmp r0,#0
beq .Lsn_dsp8_return
subs r2,#1
beq .Lsn_dsp8_zero
eor.w r3,r12,r1
tst r3,#3
bne .Lsn_dsp8_byte
.Lsn_dsp8_peel:
tst r12,#3
beq .Lsn_dsp8_words
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_dsp8_diff
cmp r0,#0
beq .Lsn_dsp8_return
subs r2,#1
beq .Lsn_dsp8_zero
b .Lsn_dsp8_peel
.Lsn_dsp8_words:
push {r4,r5}
mov r4,r12
mov.w r5,#0x01010101
.Lsn_dsp8_wordloop:
cmp r2,#4
blo .Lsn_dsp8_tail
ldr r3,[r4]
ldr r0,[r1]
cmp r3,r0
bne .Lsn_dsp8_tail
uqsub8 r12,r5,r3
cmp r12,#0
bne .Lsn_dsp8_tail
adds r4,#4
adds r1,#4
subs r2,#4
b .Lsn_dsp8_wordloop
.Lsn_dsp8_tail:
mov r12,r4
pop {r4,r5}
.Lsn_dsp8_byte:
cbz r2,.Lsn_dsp8_zero
.Lsn_dsp8_byteloop:
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_dsp8_diff
cbz r0,.Lsn_dsp8_return
subs r2,#1
bne .Lsn_dsp8_byteloop
.Lsn_dsp8_zero:
movs r0,#0
.Lsn_dsp8_return:
bx lr
.Lsn_dsp8_diff:
subs r0,r3,r0
bx lr
.size sn_dsp8,.-sn_dsp8
.balign 4
.global sn_dsp16
.type sn_dsp16,%function
.thumb_func
sn_dsp16:
cbnz r2,.Lsn_dsp16_start
movs r0,#0
bx lr
.Lsn_dsp16_start:
mov r12,r0
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_dsp16_diff
cmp r0,#0
beq .Lsn_dsp16_return
subs r2,#1
beq .Lsn_dsp16_zero
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_dsp16_diff
cmp r0,#0
beq .Lsn_dsp16_return
subs r2,#1
beq .Lsn_dsp16_zero
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_dsp16_diff
cmp r0,#0
beq .Lsn_dsp16_return
subs r2,#1
beq .Lsn_dsp16_zero
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_dsp16_diff
cmp r0,#0
beq .Lsn_dsp16_return
subs r2,#1
beq .Lsn_dsp16_zero
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_dsp16_diff
cmp r0,#0
beq .Lsn_dsp16_return
subs r2,#1
beq .Lsn_dsp16_zero
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_dsp16_diff
cmp r0,#0
beq .Lsn_dsp16_return
subs r2,#1
beq .Lsn_dsp16_zero
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_dsp16_diff
cmp r0,#0
beq .Lsn_dsp16_return
subs r2,#1
beq .Lsn_dsp16_zero
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_dsp16_diff
cmp r0,#0
beq .Lsn_dsp16_return
subs r2,#1
beq .Lsn_dsp16_zero
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_dsp16_diff
cmp r0,#0
beq .Lsn_dsp16_return
subs r2,#1
beq .Lsn_dsp16_zero
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_dsp16_diff
cmp r0,#0
beq .Lsn_dsp16_return
subs r2,#1
beq .Lsn_dsp16_zero
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_dsp16_diff
cmp r0,#0
beq .Lsn_dsp16_return
subs r2,#1
beq .Lsn_dsp16_zero
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_dsp16_diff
cmp r0,#0
beq .Lsn_dsp16_return
subs r2,#1
beq .Lsn_dsp16_zero
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_dsp16_diff
cmp r0,#0
beq .Lsn_dsp16_return
subs r2,#1
beq .Lsn_dsp16_zero
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_dsp16_diff
cmp r0,#0
beq .Lsn_dsp16_return
subs r2,#1
beq .Lsn_dsp16_zero
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_dsp16_diff
cmp r0,#0
beq .Lsn_dsp16_return
subs r2,#1
beq .Lsn_dsp16_zero
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_dsp16_diff
cmp r0,#0
beq .Lsn_dsp16_return
subs r2,#1
beq .Lsn_dsp16_zero
eor.w r3,r12,r1
tst r3,#3
bne .Lsn_dsp16_byte
.Lsn_dsp16_peel:
tst r12,#3
beq .Lsn_dsp16_words
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_dsp16_diff
cmp r0,#0
beq .Lsn_dsp16_return
subs r2,#1
beq .Lsn_dsp16_zero
b .Lsn_dsp16_peel
.Lsn_dsp16_words:
push {r4,r5}
mov r4,r12
mov.w r5,#0x01010101
.Lsn_dsp16_wordloop:
cmp r2,#4
blo .Lsn_dsp16_tail
ldr r3,[r4]
ldr r0,[r1]
cmp r3,r0
bne .Lsn_dsp16_tail
uqsub8 r12,r5,r3
cmp r12,#0
bne .Lsn_dsp16_tail
adds r4,#4
adds r1,#4
subs r2,#4
b .Lsn_dsp16_wordloop
.Lsn_dsp16_tail:
mov r12,r4
pop {r4,r5}
.Lsn_dsp16_byte:
cbz r2,.Lsn_dsp16_zero
.Lsn_dsp16_byteloop:
ldrb r3,[r12],#1
ldrb r0,[r1],#1
cmp r3,r0
bne .Lsn_dsp16_diff
cbz r0,.Lsn_dsp16_return
subs r2,#1
bne .Lsn_dsp16_byteloop
.Lsn_dsp16_zero:
movs r0,#0
.Lsn_dsp16_return:
bx lr
.Lsn_dsp16_diff:
subs r0,r3,r0
bx lr
.size sn_dsp16,.-sn_dsp16
.section .note.GNU-stack,"",%progbits
