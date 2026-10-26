#ifndef MK61_STRING_COMPARE_RESEARCH_BENCH_H
#define MK61_STRING_COMPARE_RESEARCH_BENCH_H
#include <stddef.h>
#include <stdint.h>
enum { SC_ROUNDS=7, SC_MAX_REPEATS=4096 };
typedef int (*sc_cmp)(const char*,const char*);
typedef int (*sc_ncmp)(const char*,const char*,size_t);
typedef uint32_t (*sc_tick)(void);
typedef struct {
  const char *left,*right;
  size_t left_bytes,right_bytes,n;
  uint32_t bounded,repeats;
  int expected_sign;
} sc_case;
typedef struct {sc_cmp compare;sc_ncmp bounded;} sc_route;
typedef struct {
  uint32_t version,status,completed_rounds;
  int oracle_sign,pre_sign,post_sign;
  uint32_t checksum,raw[SC_ROUNDS];
} sc_samples;
/* Ordinary RAM/Flash only. Timer, buffers, ABI checks, per-route ordering,
 * firmware identity, clock/IRQ qualification and storage are the supplier's
 * responsibility. This core neither accesses peripherals nor changes IRQs.
 * Durations cover the whole indirect-call loop; no empty-call subtraction.
 */
int sc_measure(const sc_case*,const sc_route*,sc_tick,sc_samples*);
#endif
