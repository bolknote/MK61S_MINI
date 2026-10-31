#ifndef MK61_STRCHR_RESEARCH_BENCH_H
#define MK61_STRCHR_RESEARCH_BENCH_H
#include <stddef.h>
#include <stdint.h>
enum { ST_ROUNDS=7, ST_MAX_REPEATS=4096 };
typedef char* (*st_search)(const char*,int);
typedef uint32_t (*st_tick)(void);
typedef struct {
  const char* text;
  size_t text_bytes;
  int character;
  int32_t expected_offset; /* -1 for no match, otherwise first byte offset. */
  uint32_t repeats;
} st_case;
typedef struct {
  uint32_t version,status,completed_rounds;
  int32_t oracle_offset;
  uintptr_t before,after,mismatch;
  uint32_t raw[ST_ROUNDS];
} st_samples;
/* Supplier owns clock/IRQ qualification, input/guard/state preservation,
 * actual Flash/SRAM layout, route order and raw storage. No peripheral or
 * IRQ access here. Raw values include the whole indirect-call/check loop.
 */
int st_measure(const st_case*,st_search,st_tick,st_samples*);
#endif
