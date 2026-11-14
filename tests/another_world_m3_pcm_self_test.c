#include "../examples/portable-apps/ANOTHER/m3_pcm.h"
#include "../sdk/coproc/stm3_module.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

uint32_t module_entry(uint32_t, const stm3_api *, stm3_job *);
int main(void) {
    uint8_t packet[512] = {0}, output[72] = {0};
    aw_m3_put32(packet, AW_M3_MAGIC); aw_m3_put16(packet + 4, 42);
    packet[6] = 64; packet[7] = 3; aw_m3_put16(packet + 8, 1000);
    for (unsigned ch = 0; ch < 2; ++ch) {
        uint8_t *d = packet + 12 + ch * 8;
        aw_m3_put16(d, (uint16_t)(44 + ch * 66)); d[2] = 66; d[3] = 64;
        d[4] = 0; d[5] = 63; aw_m3_put16(d + 6, 256);
        for (unsigned i = 0; i < 66; ++i) packet[44 + ch * 66 + i] = ch ? 192 : 64;
    }
    stm3_job job = {packet, 176, output, sizeof(output), 0, 0};
    uint32_t result = module_entry(STM3_INIT, NULL, &job);
    assert(result == STM3_MORE && job.progress == 16);
    while (result == STM3_MORE) result = module_entry(STM3_STEP, NULL, &job);
    assert(result == STM3_DONE && job.progress == 64 && job.output_bytes == 72);
    assert(aw_m3_get32(output) == AW_M3_PWM && output[4] == 64 && aw_m3_get16(output + 6) == 42);
    for (unsigned i = 0; i < 64; ++i) assert(output[8+i] == 128);
    packet[7] = 1; job.progress = 0;
    result = module_entry(STM3_INIT, NULL, &job);
    while (result == STM3_MORE) result = module_entry(STM3_STEP, NULL, &job);
    assert(result == STM3_DONE && output[8] == 159);
    packet[6] = 65; assert(module_entry(STM3_INIT, NULL, &job) == STM3_INVALID);
    packet[6] = 64; aw_m3_put16(packet + 12, 511);
    assert(module_entry(STM3_INIT, NULL, &job) == STM3_INVALID);
    uint32_t random = 1;
    for (unsigned test = 0; test < 1000; ++test) {
        memset(packet, 0, sizeof(packet)); memset(output, 0, sizeof(output));
        aw_m3_put32(packet, AW_M3_MAGIC); aw_m3_put16(packet + 4, (uint16_t)test);
        packet[6] = (uint8_t)(1 + test % 64); aw_m3_put16(packet + 8, 1000);
        unsigned end = AW_M3_HEADER;
        for (unsigned ch = 0; ch < 4; ++ch) {
            random = random * 1664525u + 1013904223u;
            uint8_t *d = packet + 12 + 8 * ch;
            const unsigned phase = random & 255, volume = (random >> 8) & 63;
            const unsigned rate = 1 + ((random >> 16) % 666);
            const unsigned size = ((phase + (packet[6] - 1) * rate) >> 8) + 2;
            if (end + size > sizeof(packet)) continue;
            packet[7] |= (uint8_t)(1u << ch);
            aw_m3_put16(d, (uint16_t)end); d[2] = (uint8_t)size; d[3] = packet[6];
            d[4] = (uint8_t)phase; d[5] = (uint8_t)volume; aw_m3_put16(d + 6, (uint16_t)rate);
            for (unsigned i = 0; i < size; ++i) {
                random = random * 1664525u + 1013904223u; packet[end++] = (uint8_t)(random >> 24);
            }
        }
        job.input_bytes = end; job.progress = 0;
        result = module_entry(STM3_INIT, NULL, &job);
        while (result == STM3_MORE) result = module_entry(STM3_STEP, NULL, &job);
        assert(result == STM3_DONE && job.output_bytes == 8u + packet[6]);
        for (unsigned i = 0; i < packet[6]; ++i) {
            int mixed = 0;
            for (unsigned ch = 0; ch < 4; ++ch) if (packet[7] & (1u << ch)) {
                const uint8_t *d = packet + 12 + 8 * ch, *src = packet + aw_m3_get16(d);
                const unsigned pos = d[4] + i * aw_m3_get16(d + 6), frac = pos & 255, index = pos >> 8;
                const int value = ((int8_t)src[index] * (int)(255 - frac) + (int8_t)src[index+1] * (int)frac) >> 8;
                mixed += value * d[5] / 64;
                if (mixed < -128) mixed = -128; else if (mixed > 127) mixed = 127;
            }
            assert(output[8+i] == 128 + mixed / 2);
        }
    }
    puts("Another World M3 mono mixer tests passed"); return 0;
}
