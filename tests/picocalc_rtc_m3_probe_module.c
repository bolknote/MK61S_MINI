/* Temporary SRAM-only diagnostic. No peripheral or Flash writes. */
#include "stm3_module.h"
#define MAGIC 0x31435452u
#define WORD(at) (*(const volatile uint32_t *)(uintptr_t)(at))
static uint32_t steps, work, accumulator, seed, started;
static uint32_t get(const uint8_t *p) {
    return (uint32_t)p[0] | (uint32_t)p[1]<<8 | (uint32_t)p[2]<<16 | (uint32_t)p[3]<<24;
}
static void put(uint8_t *p, uint32_t value) {
    for (unsigned i=0; i<4; ++i) p[i]=(uint8_t)(value>>(8*i));
}
static int ram_word(uint32_t at) { return !(at&3) && at>=0x20000000u && at<=0x20004ffcu; }
__attribute__((section(".text.module_entry"),used))
uint32_t module_entry(uint32_t op, const stm3_api *api, stm3_job *job) {
    if (!api || api->abi!=STM3_ABI || api->size!=sizeof(*api)) return STM3_INVALID;
    if (op==STM3_CANCEL || op==STM3_FINI) return STM3_DONE;
    if (job->input_bytes<8 || get(job->input)!=MAGIC || job->output_capacity<32) return STM3_INVALID;
    const uint32_t command=get(job->input+4);
    if (op==STM3_INIT && command==0) {
        if (job->input_bytes<16) return STM3_INVALID;
        const uint32_t at=get(job->input+8), n=get(job->input+12);
        if (!n || n>224 || job->input_bytes!=16+n || at>0xf800 || n>0xf800-at) return STM3_INVALID;
        const volatile uint8_t *flash=(const volatile uint8_t *)(uintptr_t)(0x08000000u+at);
        uint32_t equal=1;
        for (uint32_t i=0; i<n; ++i) if (flash[i]!=job->input[16+i]) equal=0;
        put(job->output,MAGIC); put(job->output+4,0); put(job->output+8,at);
        put(job->output+12,n); put(job->output+16,equal); job->output_bytes=20;
        return STM3_DONE;
    }
    if (op==STM3_INIT && command==2) {
        if (job->input_bytes!=20) return STM3_INVALID;
        const uint32_t date=get(job->input+8), time=get(job->input+12), calendar=get(job->input+16);
        if (!ram_word(date) || !ram_word(time) || !ram_word(calendar)) return STM3_INVALID;
        uint32_t high,low,again;
        do { high=WORD(0x40002818u); low=WORD(0x4000281cu); again=WORD(0x40002818u); } while(high!=again);
        put(job->output,MAGIC); put(job->output+4,2); put(job->output+8,WORD(0x40002800u));
        put(job->output+12,WORD(0x40002804u)); put(job->output+16,(high<<16)|low);
        put(job->output+20,WORD(calendar)); put(job->output+24,WORD(date)); put(job->output+28,WORD(time));
        job->output_bytes=32; return STM3_DONE;
    }
    if (command!=1 || job->input_bytes!=24) return STM3_INVALID;
    if (op==STM3_INIT) {
        steps=get(job->input+8); work=get(job->input+12); seed=accumulator=get(job->input+16);
        if (!steps || steps>8192 || work>4096 || get(job->input+20)) return STM3_INVALID;
        job->progress=0; job->output_bytes=0; started=api->micros(api->context); return STM3_MORE;
    }
    if (op!=STM3_STEP || job->progress>=steps) return STM3_INVALID;
    for (uint32_t i=0; i<work; ++i) accumulator=accumulator*1664525u+1013904223u;
    accumulator^=job->progress+0x9e3779b9u;
    if (++job->progress<steps) return STM3_MORE;
    put(job->output,MAGIC); put(job->output+4,1); put(job->output+8,steps);
    put(job->output+12,work); put(job->output+16,seed); put(job->output+20,accumulator);
    put(job->output+24,api->micros(api->context)-started); job->output_bytes=28;
    return STM3_DONE;
}
