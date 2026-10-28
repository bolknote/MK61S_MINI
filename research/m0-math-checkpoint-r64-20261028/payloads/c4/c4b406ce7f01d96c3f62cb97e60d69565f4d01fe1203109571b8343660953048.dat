// Cheap high Taylor terms for pow's normal Q70 logarithm only.
// cube<2^37, t<2^32. fourth differs from the previous floor by at most1;
// the final rounded fourth/fifth terms together change by at most2 Q70
// units. Existing main error13.401+2 remains below the unchanged guard16.
__attribute__((always_inline)) inline uint32_t pow_log_fourth70(U cube,uint32_t t) {
  const uint32_t a=uint32_t(cube>>6),al=a&65535U,ah=a>>16;
  const uint32_t bl=t&65535U,bh=t>>16;
  return (ah*bh+((al*bh)>>16)+((ah*bl)>>16)+1)>>5;
}
__attribute__((always_inline)) inline uint32_t pow_log_fifth70(uint32_t fourth,uint32_t t) {
  return (((fourth>>12)*(t>>17))>>14)+2;
}
