#ifndef MK61_ELIZA_ENGINE_H
#define MK61_ELIZA_ENGINE_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define ELIZA_INPUT_BYTES 96U
#define ELIZA_REPLY_BYTES 192U
#define ELIZA_RESPONSE_SET_COUNT 41U

typedef struct eliza_state {
  uint8_t next_response[ELIZA_RESPONSE_SET_COUNT];
  uint8_t memory_pending;
  char previous[ELIZA_INPUT_BYTES];
  char memory[ELIZA_INPUT_BYTES];
} eliza_state;

void eliza_init(eliza_state* state);
void eliza_reply(eliza_state* state, const char* input,
                 char* output, size_t output_size);
int eliza_is_goodbye(const char* input);

#ifdef __cplusplus
}
#endif

#endif
