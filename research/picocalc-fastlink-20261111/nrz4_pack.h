/* Two GPIO BSRR words per nibble, prepared before the DMA burst. */
#ifndef FL_NRZ4_PACK_H
#define FL_NRZ4_PACK_H
static __attribute__((noinline,noclone)) void fl_nrz_pack(const uint8_t *p,unsigned n,uint32_t *out) {
 /* PB9/PB8 carry the low pair; PC11/PC10 use the same words shifted by2.
  * Four entries keep the complete diagnostic inside its6144-byte RAM cap. */
 static const uint32_t pair[4]={0x03000000u,0x01000200u,0x02000100u,0x00000300u};
 uint32_t *b=out,*c=out+FL_NRZ_SYMBOL_CAPACITY;
 const uint8_t *end=p+n;
 while(p!=end) {
  *b++=0x03000000u;*c++=0x0c000000u; /* common start0 */
  for(unsigned i=0;i<4;++i) {
   unsigned v=*p++;
   *b++=pair[(v>>4)&3u];*c++=pair[v>>6]<<2;
   *b++=pair[v&3u];*c++=pair[(v>>2)&3u]<<2;
  }
  *b++=0x300u;*c++=0xc00u; /* common stop15 */
 }
 *b=0x300u;*c=0xc00u; /* finite idle tail */
}
#endif
