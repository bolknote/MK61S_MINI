/* Research candidates. Contract: n >= 16, writable ordinary memory only.
 * ISO C argument order. Short paths continue to belong to the resident code.
 */
void* local_bulk_style(void*, int, size_t);
void* local_bulk_edges(void*, int, size_t);
void* local_bulk_edges_loop(void*, int, size_t);

/* Backward aligned stores like the ROM routine, with its tiny-input path
 * removed and register assignment changed to avoid an ABI adapter.
 */
__asm__(
  ".syntax unified\n.thumb\n"
  ".section .text.local_bulk_style,\"ax\",%progbits\n.balign 4\n"
  ".global local_bulk_style\n.type local_bulk_style,%function\n.thumb_func\n"
  "local_bulk_style:\n"
  "bfi r1,r1,#8,#8\n"
  "bfi r1,r1,#16,#16\n"
  "adds r0,r0,r2\n"
  "ands r3,r0,#3\n"
  "beq 1f\n"
  "subs r2,r2,r3\n"
  "lsls r3,r3,#31\n"
  "it mi\nstrbmi r1,[r0,#-1]!\n"
  "it cs\nstrhcs r1,[r0,#-2]!\n"
  "1:\n"
  "movs r3,r1\npush {r4,r5}\nmov r4,r1\nmov r5,r1\n"
  "2:\nsubs r2,r2,#16\nit cs\nstmdbcs r0!,{r1,r3,r4,r5}\nbhi 2b\n"
  "lsls r2,r2,#29\nit cs\nstmdbcs r0!,{r1,r3}\n"
  "it mi\nstrmi r1,[r0,#-4]!\n"
  "lsls r2,r2,#2\nit cs\nstrhcs r1,[r0,#-2]!\n"
  "it mi\nstrbmi r1,[r0,#-1]!\n"
  "pop {r4,r5}\nbx lr\n"
  ".size local_bulk_style,.-local_bulk_style\n"
);

/* Alternative: fill the first and last word up front, both wholly inside
 * the range because n >= 16. Their overlap with the aligned middle is
 * intentional. This eliminates the byte/halfword tail handling entirely.
 * Only the two edge stores may be unaligned; STM stores remain aligned.
 */
__asm__(
  ".section .text.local_bulk_edges,\"ax\",%progbits\n.balign 4\n"
  ".global local_bulk_edges\n.type local_bulk_edges,%function\n.thumb_func\n"
  "local_bulk_edges:\n"
  "bfi r1,r1,#8,#8\nbfi r1,r1,#16,#16\n"
  "mov ip,r0\nstr r1,[r0]\nadds r0,r0,r2\nstr r1,[r0,#-4]\n"
  "bic r0,r0,#3\nsub r2,r0,ip\n"
  "movs r3,r1\npush {r4,r5}\nmov r4,r1\nmov r5,r1\n"
  "1:\nsubs r2,r2,#16\nit cs\nstmdbcs r0!,{r1,r3,r4,r5}\nbhi 1b\n"
  "lsls r2,r2,#29\nit cs\nstmdbcs r0!,{r1,r3}\n"
  "it mi\nstrmi r1,[r0,#-4]!\n"
  "mov r0,ip\npop {r4,r5}\nbx lr\n"
  ".size local_bulk_edges,.-local_bulk_edges\n"
);

/* Same bounded edges, but a three-instruction bulk loop without an IT block. */
__asm__(
  ".section .text.local_bulk_edges_loop,\"ax\",%progbits\n.balign 4\n"
  ".global local_bulk_edges_loop\n.type local_bulk_edges_loop,%function\n.thumb_func\n"
  "local_bulk_edges_loop:\n"
  "bfi r1,r1,#8,#8\nbfi r1,r1,#16,#16\n"
  "mov ip,r0\nstr r1,[r0]\nadds r0,r0,r2\nstr r1,[r0,#-4]\n"
  "bic r0,r0,#3\nsub r2,r0,ip\n"
  "movs r3,r1\npush {r4,r5}\nmov r4,r1\nmov r5,r1\n"
  "subs r2,r2,#16\nbcc 2f\n"
  "1:\nstmdb r0!,{r1,r3,r4,r5}\nsubs r2,r2,#16\nbcs 1b\n"
  "2:\nlsls r2,r2,#29\nit cs\nstmdbcs r0!,{r1,r3}\n"
  "it mi\nstrmi r1,[r0,#-4]!\n"
  "mov r0,ip\npop {r4,r5}\nbx lr\n"
  ".size local_bulk_edges_loop,.-local_bulk_edges_loop\n"
);
