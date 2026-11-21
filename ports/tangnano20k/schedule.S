    .option norvc
    .text
    .globl _start
_start:
    lw    t0, 0(zero)       # time of one step
    lw    t1, 4(zero)       # time of a two-position verification
    lw    t2, 8(zero)       # probability that the draft matches, in Q0.8
    bgeu  t0, t1, pair
    sub   t1, t1, t0
    slli  t1, t1, 8
    addi  gp, zero, 0
multiply:
    andi  tp, t2, 1
    beq   tp, zero, next_bit
    add   gp, gp, t0
next_bit:
    srli  t2, t2, 1
    slli  t0, t0, 1
    bne   t2, zero, multiply
    bgeu  t1, gp, single
pair:
    addi  gp, zero, 2
    sw    gp, 12(zero)
single:
    addi  gp, zero, 1
    sw    gp, 12(zero)
