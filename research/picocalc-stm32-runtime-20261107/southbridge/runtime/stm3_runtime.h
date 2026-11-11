#ifndef STM3_RUNTIME_H
#define STM3_RUNTIME_H
#include "stm3_module.h"
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
enum { STM3_EMPTY=0,STM3_LOADING,STM3_READY,STM3_RUNNING,STM3_FINISHED,STM3_CANCELLED,STM3_FAULT };
enum { STM3_OK=0,STM3_E_ARGUMENT,STM3_E_STATE,STM3_E_SIZE,STM3_E_CRC,STM3_E_FORMAT,STM3_E_ABI,STM3_E_MODULE,STM3_E_TIME,STM3_E_JOB };
enum { STM3_HELLO=1,STM3_LOAD_BEGIN,STM3_LOAD_CHUNK,STM3_LOAD_COMMIT,STM3_WRITE,STM3_START,STM3_STATUS,STM3_READ,STM3_CANCEL_JOB,STM3_UNLOAD,STM3_START_RESULT };
enum { STM3_TRANSPORT_RX_DMA=1,STM3_TRANSPORT_TX_DMA=2,STM3_TRANSPORT_START_RESULT=4 };
#define STM3_RESULT_LIMIT (STM3_WIRE_PAYLOAD-12u)
typedef struct {
 void* context;
 uint32_t (*micros)(void*);
 uint32_t (*load_address)(void*,const void*);
 uint32_t (*invoke)(void*,uint32_t,uint32_t,const stm3_api*,stm3_job*);
 uint32_t baud,transport_flags; // bit0 RX DMA,bit1 TX DMA;0 for HOST backend
} stm3_backend;
typedef struct {
 stm3_backend backend;
 stm3_header header;
 uint32_t state,error,module_id,job_id,received,package_bytes;
 uint32_t entry,steps,started,deadline_us,max_slice_us;
 stm3_job job;
 uint32_t last_seq,last_request_crc,last_cmd,have_reply;
 uint32_t deferred,deferred_count;
 uint32_t frame_bytes,frame_overflow,tx_bytes,tx_at,bad_frames,sequence_conflicts;
 union {uint32_t alignment;uint8_t bytes[STM3_PACKAGE_CAPACITY];} arena;
 uint8_t input[STM3_IO_CAPACITY],output[STM3_IO_CAPACITY];
 // COBS decoding shrinks in place. The separate TX cache is pinned by DMA.
 uint8_t frame[STM3_WIRE_CAPACITY],tx[STM3_WIRE_CAPACITY];
} stm3_runtime;
uint32_t stm3_crc32(const void*,size_t);
void stm3_init(stm3_runtime*,const stm3_backend*);
void stm3_command(stm3_runtime*,uint8_t,const uint8_t*,uint16_t,uint8_t*,uint16_t*);
void stm3_tick(stm3_runtime*);
void stm3_feed(stm3_runtime*,uint8_t);
unsigned stm3_transmit(stm3_runtime*,uint8_t*,unsigned);
unsigned stm3_cobs_encode(const uint8_t*,unsigned,uint8_t*,unsigned);
unsigned stm3_cobs_decode(const uint8_t*,unsigned,uint8_t*,unsigned);
#ifdef __cplusplus
}
#endif
#endif
