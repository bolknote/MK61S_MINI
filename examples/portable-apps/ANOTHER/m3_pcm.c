/* Experimental native Cortex-M3 four-channel mono PCM mixer. */
#include "m3_pcm.h"
#include "stm3_module.h"
#include <stdbool.h>

static bool valid(const stm3_job *job) {
    if (!job || !job->input || !job->output || job->input_bytes < AW_M3_HEADER ||
        job->input_bytes > AW_M3_MAX_INPUT) return false;
    const uint8_t *p = job->input;
    const unsigned frames = p[6], mask = p[7], gain = aw_m3_get16(p + 8);
    if (aw_m3_get32(p) != AW_M3_MAGIC || !frames || frames > AW_M3_MAX_FRAMES ||
        (mask & ~15u) || gain > 1000 || p[10] || p[11] || job->output_capacity < 8 + frames) return false;
    for (unsigned i = 0; i < 4; ++i) if (mask & (1u << i)) {
        const uint8_t *d = p + 12 + 8 * i;
        const unsigned offset = aw_m3_get16(d), size = d[2], active = d[3], step = aw_m3_get16(d + 6);
        if (!active || active > frames) return false;
        const unsigned needed = ((d[4] + (active - 1) * step) >> 8) + 2;
        if (offset < AW_M3_HEADER || offset > job->input_bytes || size > job->input_bytes - offset ||
            size < needed || d[5] > 63 || !step || step > 1024) return false;
    }
    return true;
}
static uint32_t step(stm3_job *job) {
    const uint8_t *p = job->input; const unsigned frames = p[6], mask = p[7], gain = aw_m3_get16(p + 8);
    unsigned end = job->progress + 16; if (end > frames) end = frames;
    for (unsigned i = job->progress; i < end; ++i) {
        int sum = 0;
        for (unsigned ch = 0; ch < 4; ++ch) if ((mask & (1u << ch)) && i < p[12 + 8 * ch + 3]) {
            const uint8_t *d = p + 12 + 8 * ch, *data = p + aw_m3_get16(d);
            const unsigned phase = d[4] + i * aw_m3_get16(d + 6), index = phase >> 8, frac = phase & 255;
            const int value = ((int8_t)data[index] * (int)(255 - frac) + (int8_t)data[index + 1] * (int)frac) >> 8;
            sum += value * d[5] / 64;
            if (sum < -128) sum = -128; else if (sum > 127) sum = 127;
        }
        job->output[8 + i] = (uint8_t)(128 + (sum * 256 * (int)gain) / 512000);
    }
    job->progress = end;
    if (end != frames) return STM3_MORE;
    job->output_bytes = 8 + frames; return STM3_DONE;
}
uint32_t module_entry(uint32_t op, const stm3_api *api, stm3_job *job) {
    (void)api;
    if (op == STM3_CANCEL || op == STM3_FINI) return STM3_DONE;
    if (op == STM3_INIT) {
        if (!valid(job)) return STM3_INVALID;
        aw_m3_put32(job->output, AW_M3_PWM); job->output[4] = job->input[6]; job->output[5] = 0;
        aw_m3_put16(job->output + 6, aw_m3_get16(job->input + 4));
        job->output_bytes = 0; job->progress = 0;
        return step(job);
    }
    if (op == STM3_STEP && valid(job) && job->progress < job->input[6]) return step(job);
    return STM3_INVALID;
}
