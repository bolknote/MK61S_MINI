#ifndef STM3_MODULE_H
#define STM3_MODULE_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define STM3_ABI 1u
#define STM3_TARGET 0x00070301u
#define STM3_MAGIC 0x314d3353u /* S3M1 */
#define STM3_LINK_BASE 0x20000000u
#define STM3_HEADER_BYTES 64u
#define STM3_IMAGE_CAPACITY 6144u
#define STM3_RELOC_LIMIT 64u
#define STM3_PACKAGE_CAPACITY (STM3_HEADER_BYTES+STM3_IMAGE_CAPACITY+4u*STM3_RELOC_LIMIT)
#define STM3_IO_CAPACITY 512u
#define STM3_WIRE_PAYLOAD 256u
#define STM3_WIRE_CAPACITY 272u

typedef struct {
 uint32_t magic,abi,header_bytes,package_bytes;
 uint32_t image_bytes,bss_bytes,entry_offset,reloc_count;
 uint32_t input_limit,output_limit,stack_hint,slice_us;
 uint32_t payload_crc,flags,target,header_crc;
} stm3_header;
typedef struct {
 uint32_t abi,size;
 uint32_t (*micros)(void*);
 void* context;
} stm3_api;
typedef struct {
 const uint8_t* input;
 uint32_t input_bytes;
 uint8_t* output;
 uint32_t output_capacity,output_bytes,progress;
} stm3_job;
enum { STM3_INIT=0,STM3_STEP=1,STM3_CANCEL=2,STM3_FINI=3 };
enum { STM3_MORE=0,STM3_DONE=1,STM3_INVALID=2 };
typedef uint32_t (*stm3_entry)(uint32_t,const stm3_api*,stm3_job*);
#ifdef __cplusplus
}
#endif
#endif
