// Arduino's core archive owns no second runtime. The shared implementations,
// main(), vector table and startup are compiled from the MK61s sketch sources.
// The installer supplies the same Arduino compatibility headers as native GCC.
static_assert(sizeof(unsigned) == 4, "MK61s native core requires ARM32");
