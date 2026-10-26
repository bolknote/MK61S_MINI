// Identical CORE-MATH storage types in a neutral namespace avoid ADL
// between separately included function implementations. No field changes.
namespace core_m0_shared {
typedef mk61_u128 u128;
#if __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
typedef union {
  u128 r;
  struct {
    uint64_t lo;
    uint64_t hi;
    int64_t ex;
    uint64_t sgn;
  };
} Trig;
#else
typedef union {
  u128 r;
  struct {
    uint64_t hi;
    uint64_t lo;
    int64_t ex;
    uint64_t sgn;
  };
} Trig;
#endif
typedef struct {
  uint64_t hi;
  uint64_t lo;
  int64_t ex;
  uint64_t sgn;
} Log;
static_assert(sizeof(Trig)==32 && sizeof(Log)==32,"CORE-MATH constant layout");
}
