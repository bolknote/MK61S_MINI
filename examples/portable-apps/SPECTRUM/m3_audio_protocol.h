#ifndef MK61_SPECTRUM_M3_AUDIO_PROTOCOL_H
#define MK61_SPECTRUM_M3_AUDIO_PROTOCOL_H
#include <stddef.h>
#include <stdint.h>
#include "../../../third_party/emu2149/emu2149.h"

/* Little-endian, pointer-free packets, independent of the S3M1 loader ABI.
 * Both processors use the same integer PSG core and sample boundaries. */
#define SPECTRUM_M3_AUDIO_MAGIC 0x31594153u /* SAY1 */
#define SPECTRUM_M3_PCM_MAGIC 0x314d4350u   /* PCM1 */
#define SPECTRUM_M3_PWM_MAGIC 0x314d5750u   /* PWM1: exact existing 8-bit duty */
#define SPECTRUM_M3_STATE_MAGIC 0x31534153u /* SAS1 */
#define SPECTRUM_M3_PROFILE_MAGIC 0x31504153u /* SAP1 */
#define SPECTRUM_M3_PROFILE_BYTES 32u
#define SPECTRUM_M3_AUDIO_SAMPLES 120u
#define SPECTRUM_M3_AUDIO_IO 512u
#define SPECTRUM_M3_PSG_BYTES (offsetof(PSG,ch_out)+sizeof(((PSG*)0)->ch_out)-offsetof(PSG,reg))
#define SPECTRUM_M3_STATE_BYTES (8u+2u*SPECTRUM_M3_PSG_BYTES+8u+3u)
enum { SPECTRUM_M3_CONFIG=0,SPECTRUM_M3_RENDER=1,SPECTRUM_M3_EXPORT=2,SPECTRUM_M3_PROFILE=3 };
enum { SPECTRUM_M3_BEEPER_ARRAY=1,SPECTRUM_M3_COVOX_ARRAY=2,SPECTRUM_M3_SPECDRUM_ARRAY=4 };

/* CONFIG: 8-byte header, two PSG bodies (no voltbl pointer/padding),
 * signed DC input/output words, beeper/covox/specdrum bytes.
 * CONFIG header bytes5=0 for PCM16,1 for PWM8; bytes6..7=PWM gain0..1000.
 * RENDER: magic/op/samples/extensions/array_flags, three constant DAC bytes,
 * enabled variable arrays (beeper bitmap, Covox bytes, SpecDrum bytes),
 * then {sample_index,chip*16+register,value} triples. Event order is preserved,
 * including repeated envelope triggers. n<=120; total packet<=512.
 * PCM1/PWM1 reply: magic, uint16 count, uint16 sequence, mono16/PWM8 samples.
 * CONFIG acknowledgement: PCM1/count0, byte6=fast-INIT sample limit,
 * byte7=capabilities (bit0 inline INIT,bit1 exact PWM8,bit2 adaptive INIT,
 * bit3 read-only PROFILE). PROFILE is queried after playback, never per block.
 * Adaptive INIT may return MORE: STATUS must confirm completion before READ.
 * Adaptive INIT checks its100us budget every16 samples, then yields MORE;
 * STEP renders at most16 samples. The resident's2ms limit is unchanged.
 * EXPORT input: magic/op plus three reserved bytes. SAS1 output uses CONFIG's
 * state layout. PROFILE input: magic/op plus three reserved bytes. Output:
 * SAP1, uint32 samples/jobs/slices, uint64 render_us, uint32 max_job_us and
 * max_slice_us. Timings cover rendering and interrupt preemption within each
 * module call; they exclude packet exchange, readiness waits and validation.
 * CONFIG clears the counters. Without api->micros the timings are zero.
 * Cancel/unload do not call any Pico-owned pointer. */
static inline uint32_t spectrum_m3_get32(const uint8_t* p) {
    return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;
}
static inline void spectrum_m3_put32(uint8_t* p,uint32_t value) {
    for(unsigned i=0;i<4;++i)p[i]=(uint8_t)(value>>(8*i));
}
#endif
