#ifndef MK61_ELIZA_ENGINE_H
#define MK61_ELIZA_ENGINE_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define ELIZA_INPUT_BYTES 96U
#define ELIZA_REPLY_BYTES 192U
#define ELIZA_TRANSFORM_SLOTS 59U
#define ELIZA_MEMORY_SLOTS 16U

typedef struct eliza_state {
  uint8_t next_reassembly[ELIZA_TRANSFORM_SLOTS];
  uint8_t limit;
  uint8_t memory_head;
  uint8_t memory_count;
  uint8_t memory_kind[ELIZA_MEMORY_SLOTS];
  char memory[ELIZA_MEMORY_SLOTS][ELIZA_INPUT_BYTES];
} eliza_state;

void eliza_init(eliza_state* state);
void eliza_reply(eliza_state* state, const char* input,
                 char* output, size_t output_size);
int eliza_is_goodbye(const char* input);

#ifdef __cplusplus
}
#endif

#endif
