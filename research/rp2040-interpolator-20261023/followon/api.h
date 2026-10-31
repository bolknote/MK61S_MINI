#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef uint64_t FoFunction(uint64_t,uint64_t);
uint64_t fo_ln_cpu(uint64_t,uint64_t);
uint64_t fo_ln_interp(uint64_t,uint64_t);
void fo_lookup_setup(void);
void fo_root_setup(void);
void fo_texture_setup(void);
void fo_audio_setup(void);
uint64_t fo_texture_cpu(uint64_t,uint64_t);
uint64_t fo_texture_pop(uint64_t,uint64_t);
uint64_t fo_audio_cpu(uint64_t,uint64_t);
uint64_t fo_audio_interp(uint64_t,uint64_t);
uint32_t fo_pop_hash(unsigned);
unsigned fo_pop_verify(unsigned,uint64_t,unsigned);
extern uint8_t fo_output[2048];
#define FO_ROOT(name) uint64_t fo_sqrt_##name(uint64_t,uint64_t); uint64_t fo_rsqrt_##name(uint64_t,uint64_t);
FO_ROOT(base)
FO_ROOT(new_cpu)
FO_ROOT(new_interp)
FO_ROOT(skip_refine)
#undef FO_ROOT
#ifdef __cplusplus
}
#endif
