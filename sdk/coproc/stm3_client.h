#ifndef STM3_CLIENT_H
#define STM3_CLIENT_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
enum {S3_HELLO=1,S3_LOAD_BEGIN,S3_LOAD_CHUNK,S3_LOAD_COMMIT,S3_WRITE,S3_START,S3_STATUS,S3_READ,S3_CANCEL,S3_UNLOAD,S3_START_RESULT,S3_START_RESULT_INPUT};
enum {S3_TRANSPORT_RX_DMA=1,S3_TRANSPORT_TX_DMA=2,S3_TRANSPORT_START_RESULT=4,S3_TRANSPORT_START_RESULT_INPUT=8};
#define S3_RESULT_LIMIT 244u
#define S3_START_RESULT_INPUT_LIMIT 240u
// START_RESULT input: module_id,input_bytes,deadline_ms,result_bytes (4 LE words).
// One deferred reply: job_id,max_slice_us,result_bytes of output from offset0.
// START_RESULT_INPUT appends exactly input_bytes after those words. It avoids
// the preceding WRITE round trip when input_bytes<=240; larger jobs use WRITE.
// Remote errors retain their original status. No STATUS/READ readiness polls.
// Require HELLO's START_RESULT bit; keep one request outstanding until reply.
enum {S3_TIMEOUT=-1,S3_FRAME=-2,S3_SIZE=-3,S3_IO=-4};
typedef struct {
 void*context;
 uint32_t(*micros)(void*);
 int(*send)(void*,const uint8_t*,unsigned,uint32_t);
 int(*read_byte)(void*,uint32_t);
} stm3_client_io;
typedef struct {
 stm3_client_io io;
 uint8_t tx[272],rx[272];
 uint16_t seq;
 uint8_t command;
 unsigned tx_bytes;
 uint32_t sent,received,requests,last_us,max_us;
} stm3_client;
void stm3_client_init(stm3_client*,const stm3_client_io*);
// Return 0, a positive remote status, or a negative local transport error.
// Output excludes the remote status word; at most252 bytes. No allocation.
int stm3_client_request(stm3_client*,uint8_t,const void*,unsigned,void*,unsigned*,uint32_t);
// One outstanding request. begin sends its frame without awaiting the reply;
// finish receives that same reply without retransmitting. UART RX must remain
// serviced between calls. replay still retries the identical cached request.
int stm3_client_begin(stm3_client*,uint8_t,const void*,unsigned,uint32_t);
int stm3_client_finish(stm3_client*,void*,unsigned*,uint32_t);
int stm3_client_replay(stm3_client*,void*,unsigned*,uint32_t);
uint32_t stm3_get32(const void*);
void stm3_put32(void*,uint32_t);
#ifdef __cplusplus
}
#endif
#endif
