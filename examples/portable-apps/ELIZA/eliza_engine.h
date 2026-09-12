#ifndef MK61_ELIZA_ENGINE_H
#define MK61_ELIZA_ENGINE_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define ELIZA_INPUT_BYTES 512U
#define ELIZA_REPLY_BYTES 1152U
#define ELIZA_TRANSFORM_SLOTS 59U
#define ELIZA_MEMORY_WORKSPACE_BYTES 8192U

typedef struct eliza_state {
  uint8_t next_reassembly[ELIZA_TRANSFORM_SLOTS];
  uint8_t limit;
  uint8_t* memory;
  size_t memory_capacity;
  size_t memory_used;
} eliza_state;

void eliza_init(eliza_state* state, uint8_t* memory, size_t memory_capacity);
void eliza_reply(eliza_state* state, const char* input,
                 char* output, size_t output_size);
int eliza_is_goodbye(const char* input);

#ifdef __cplusplus
}
#endif

#endif
