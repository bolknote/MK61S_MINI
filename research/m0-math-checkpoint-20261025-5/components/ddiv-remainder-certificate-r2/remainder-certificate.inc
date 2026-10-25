// R4=base, R2=u, R0=v. R0/R1/R12/SP retained; R5/R6 temporary.
// hi32(u*v)-hi16(u)*hi16(v)+lowword_borrow lies in[0,131071].
// If the modular interval crosses zero or INT32_MIN, keep the exact path.
.macro remainder_certificate full,negative
 lsrs r5,r2,#16
 lsrs r6,r0,#16
 muls r5,r6
 subs r4,r5
 lsrs r6,r4,#17
 lsls r6,#18                   @ Z=uncertain band, C=sign of R4
 beq \full
 bcs \negative
.endm
