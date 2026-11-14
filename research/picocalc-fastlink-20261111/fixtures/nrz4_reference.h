/* Original hardware016 packer, retained only for the diagnostic A/B build. */
static inline void fl_nrz_pack(const uint8_t *p,unsigned n,uint32_t *out) {
 for(unsigned i=0;i<=n/4u*10u;++i) {
  unsigned v=i==n/4u*10u?15u:fl_nrz_symbol(p,i);
  uint32_t b=((v&1u)<<9)|((v&2u)<<7),c=((v&4u)<<9)|((v&8u)<<7);
  out[i]=b|((~b&0x300u)<<16);
  out[FL_NRZ_SYMBOL_CAPACITY+i]=c|((~c&0xc00u)<<16);
 }
}
