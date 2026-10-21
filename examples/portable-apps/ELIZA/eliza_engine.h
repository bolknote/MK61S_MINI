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
typedef int (*eliza_memory_read)(void*,size_t,uint8_t*,size_t);
typedef int (*eliza_memory_write)(void*,size_t,const uint8_t*,size_t);

typedef struct eliza_state {
  uint8_t next_reassembly[ELIZA_TRANSFORM_SLOTS];
  uint8_t limit;
  uint8_t* memory;
  size_t memory_capacity;
  size_t memory_used;
  size_t memory_head;
  void* memory_context;
  eliza_memory_read memory_read;
  eliza_memory_write memory_write;
  uint8_t memory_failed;
} eliza_state;

void eliza_init(eliza_state* state, uint8_t* memory, size_t memory_capacity);
void eliza_init_storage(eliza_state* state,void* context,size_t capacity,
                        eliza_memory_read read,eliza_memory_write write);
void eliza_reply(eliza_state* state, const char* input,
                 char* output, size_t output_size);
int eliza_is_goodbye(const char* input);

#ifdef __cplusplus
}
#endif

#endif
