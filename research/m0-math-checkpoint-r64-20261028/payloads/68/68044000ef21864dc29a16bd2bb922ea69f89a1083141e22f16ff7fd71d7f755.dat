.macro reciprocal_seed_inline
.global mk61_m0_inline_seed_begin
mk61_m0_inline_seed_begin:
 lsrs r6,r1,#9
 subs r6,#128
 lsls r6,#1
 adr r4,.Linline_seed_table
 ldrh r6,[r4,r6]
 adds r4,r1,#1
 lsrs r4,#1
 muls r4,r6
 lsls r4,#1
 asrs r4,#17
 muls r4,r6
 asrs r4,#15
 subs r6,r4
 movs r7,r6
 muls r7,r1
 mvns r7,r7
 bmi .Linline_seed_high
 cmp r7,r1
 bcc .Linline_seed_done
 adds r6,#1
 subs r7,r1
 b .Linline_seed_done
.Linline_seed_high:
 subs r6,#1
 adds r7,r1
 bmi .Linline_seed_high
.Linline_seed_done:
.global mk61_m0_inline_seed_done
mk61_m0_inline_seed_done:
.endm
