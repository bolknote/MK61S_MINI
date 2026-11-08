#ifndef MK61_AI_M3_LINEAR_PROTOCOL_H
#define MK61_AI_M3_LINEAR_PROTOCOL_H
#include <stdint.h>
#define AI_M3_MAGIC 0x314c4941u /* AIL1; little endian IEEE binary32 */
#define AI_M3_INT8_MAGIC 0x31494941u /* AII1; Q4 nibbles, INT8 activations */
#define AI_M3_PREPARE 1u
#define AI_M3_RUN 2u
#define AI_M3_HEADER 16u /* magic, operation, columns, rows */
#define AI_M3_MAX_COLUMNS 512u
#define AI_M3_MAX_ROWS 2u
/* PREPARE has no payload, rows=0. It resets the vector. Subsequent jobs
 * contain raw activation bytes (multiples of four, <=512) until columns*4
 * bytes are received. These jobs complete in INIT and return a 12-byte ACK:
 * magic, columns, received_bytes. RUN follows only after the complete vector:
 * header then rows * (columns/2 Q4 bit-plane bytes + columns/16 FP16 scales).
 * RUN returns rows binary32 values in row order. One STEP handles one group
 * of 32 columns for every row. The vector survives jobs until PREPARE/UNLOAD.
 */
#endif
