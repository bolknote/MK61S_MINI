/* Same hidden sret ABI: r0=PowFastLog*, r1=ey, r2:r3=xb.
 * Placed beside pow_fast_log so its common small-y tail uses a direct
 * Thumb16 branch. The ordinary helper ignores ey. No stack frame. */
.section .m0_pow_log_selector,"ax",%progbits
.p2align 2
.hidden mk61_m0_pow_log_select
regular_func mk61_m0_pow_log_select
 cmp r1,#4
 blt .Llog_select_old
 mov r12,r1
 ldr r1,=0x3fefff80
 subs r1,r3,r1
 cmp r1,#192
 blo .Llog_select_near
 bhi .Llog_select_new
 cmp r2,#0
 beq .Llog_select_near
.Llog_select_new:
 ldr r1,=mk61_m0_pow_log_ordinary
 bx r1
.Llog_select_near:
 mov r1,r12
.Llog_select_old:
 b pow_fast_log
.ltorg
.size mk61_m0_pow_log_select,.-mk61_m0_pow_log_select
