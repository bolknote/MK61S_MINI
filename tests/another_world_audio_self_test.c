#include "../examples/portable-apps/ANOTHER/audio.h"
#include "../sdk/coproc/stm3_module.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef struct { uint8_t bank[2048], ram[4096]; } memory;
uint32_t module_entry(uint32_t, const stm3_api *, stm3_job *);
static bool from_bank(void *ctx, uint8_t bank, uint32_t at, void *out, uint32_t n) {
    memory *m = ctx; if (bank != 1 || at > sizeof(m->bank) || n > sizeof(m->bank) - at) return false;
    memcpy(out, m->bank + at, n); return true;
}
static bool read_ram(void *ctx, uint32_t at, void *out, uint32_t n) {
    memory *m = ctx; if (at > sizeof(m->ram) || n > sizeof(m->ram) - at) return false;
    memcpy(out, m->ram + at, n); return true;
}
static bool write_ram(void *ctx, uint32_t at, const void *in, uint32_t n) {
    memory *m = ctx; if (at > sizeof(m->ram) || n > sizeof(m->ram) - at) return false;
    memcpy(m->ram + at, in, n); return true;
}
static void be16(uint8_t *p, unsigned value) { p[0] = (uint8_t)(value >> 8); p[1] = (uint8_t)value; }
static void entry(uint8_t *p, unsigned offset, unsigned size) {
    memset(p, 0, 20); p[7] = 1; p[10] = (uint8_t)(offset >> 8); p[11] = (uint8_t)offset;
    be16(p + 14, size); be16(p + 18, size);
}
static void scalar(aw_audio *a, int16_t *out, unsigned count) {
    int8_t mixed[AW_AUDIO_BLOCK] = {0};
    for (unsigned ch = 0; ch < 4; ++ch) {
        aw_audio_channel *c = &a->channels[ch];
        const uint32_t end = c->length + c->loop_length;
        for (unsigned i = 0; i < count && c->active; ++i) {
            uint32_t pos = c->position >> 8;
            if (pos >= end) {
                if (!c->loop_length) { c->active = false; break; }
                c->position = ((uint32_t)c->loop << 8) +
                    (c->position - (end << 8)) % ((uint32_t)c->loop_length << 8);
                pos = c->position >> 8;
            }
            uint32_t next = pos + 1;
            if (next >= end) next = c->loop_length ? c->loop : pos;
            uint8_t x, y;
            assert(aw_assets_read(a->assets, c->data + pos, &x, 1));
            assert(aw_assets_read(a->assets, c->data + next, &y, 1));
            if (c->zero_prefix && pos < 4) x = 0;
            if (c->zero_prefix && next < 4) y = 0;
            const unsigned frac = c->position & 255;
            const int value = ((int8_t)x * (int)(255 - frac) + (int8_t)y * (int)frac) >> 8;
            int sum = mixed[i] + value * c->volume / 64;
            if (sum < -128) sum = -128; else if (sum > 127) sum = 127;
            mixed[i] = (int8_t)sum; c->position += c->increment;
        }
        if (c->loop_length && (c->position >> 8) >= end)
            c->position = ((uint32_t)c->loop << 8) +
                (c->position - (end << 8)) % ((uint32_t)c->loop_length << 8);
    }
    for (unsigned i = 0; i < count; ++i) out[i] = (int16_t)((int)mixed[i] * 256);
}
int main(void) {
    memory m = {0}; aw_assets assets; aw_vm vm = {0}; aw_audio audio; uint8_t list[61];
    entry(list, 0, 12); entry(list + 20, 32, 16); entry(list + 40, 128, 0xC0 + 1024); list[60] = 0xFF;
    be16(m.bank, 2); m.bank[8] = 0; m.bank[9] = 64; m.bank[10] = 192; m.bank[11] = 127;
    be16(m.bank + 32, 2); be16(m.bank + 34, 2);
    for (unsigned i = 0; i < 8; ++i) m.bank[40 + i] = (uint8_t)(i * 10);
    uint8_t *music = m.bank + 128;
    be16(music, 5); be16(music + 2, 1); be16(music + 4, 63); be16(music + 0x3E, 1);
    be16(music + 0xC0, 0xFFFD); be16(music + 0xC2, 0x1234);
    be16(music + 0xC4, 200); be16(music + 0xC6, 0x1000);
    assert(aw_assets_init(&assets, list, sizeof(list), sizeof(m.ram), &m, from_bank, read_ram, write_ram));
    vm.assets = &assets;
    for (unsigned i = 0; i < 3; ++i) { assert(aw_assets_load(&assets, i)); vm.loaded[i] = 1; }
    aw_audio_init(&audio, &assets, &vm);
    aw_audio_sound(&audio, 0, 0, 63, 0); assert(audio.channels[0].active);
    audio.channels[0].increment = 256;
    int16_t pcm[12]; assert(aw_audio_render(&audio, pcm, 6));
    assert(pcm[0] == 0 && pcm[1] == 62 * 256 && pcm[2] == -63 * 256 && pcm[3] == 124 * 256);
    assert(pcm[4] == 0 && !audio.channels[0].active);
    aw_audio_sound(&audio, 1, 1, 63, 0); audio.channels[0].increment = 256;
    assert(aw_audio_render(&audio, pcm, 12));
    assert(audio.channels[0].active && pcm[8] == pcm[4] && pcm[9] == pcm[5]);
    aw_audio_sound(&audio, 1, 0, 0, 0); assert(!audio.channels[0].active);
    aw_audio_music(&audio, 2, 5, 0); assert(audio.music_active);
    assert(aw_audio_render(&audio, pcm, 2));
    assert(vm.vars[0xF4] == 0x1234 && audio.channels[1].active && audio.channels[1].zero_prefix);
    aw_audio_stop(&audio); assert(!audio.music_active && !audio.channels[1].active);
    uint32_t random = 1;
    for (unsigned test = 0; test < 1000; ++test) {
        aw_audio candidate, reference; aw_audio_init(&candidate, &assets, &vm);
        for (unsigned ch = 0; ch < 4; ++ch) {
            aw_audio_channel *c = &candidate.channels[ch];
            random = random * 1664525u + 1013904223u;
            c->data = assets.entries[1].store_offset + 8; c->length = 4;
            c->loop = 4; c->loop_length = (random & 1) ? 4 : 0;
            c->position = (random >> 8) % ((c->length + c->loop_length) * 256u);
            c->increment = 1 + ((random >> 16) % 666); c->volume = (uint8_t)((random >> 24) & 63);
            c->zero_prefix = (random & 2) != 0; c->active = true;
        }
        reference = candidate;
        int16_t got[AW_AUDIO_BLOCK], want[AW_AUDIO_BLOCK];
        const unsigned n = 1 + test % AW_AUDIO_BLOCK;
        assert(aw_audio_render(&candidate, got, n)); scalar(&reference, want, n);
        assert(!memcmp(got, want, n * sizeof(*got)));
        for (unsigned ch = 0; ch < 4; ++ch) {
            assert(candidate.channels[ch].active == reference.channels[ch].active);
            assert(candidate.channels[ch].position == reference.channels[ch].position);
        }
    }
    for (unsigned test = 0; test < 1000; ++test) {
        aw_audio remote, local; aw_audio_init(&remote, &assets, &vm);
        for (unsigned ch = 0; ch < 4; ++ch) {
            aw_audio_channel *c = &remote.channels[ch];
            random = random * 1664525u + 1013904223u;
            c->data = assets.entries[1].store_offset + 8; c->length = 4;
            c->loop = 4; c->loop_length = (random & 1) ? 4 : 0;
            c->position = (random >> 8) % ((c->length + c->loop_length) * 256u);
            c->increment = 1 + ((random >> 16) % 666); c->volume = (uint8_t)((random >> 24) & 63);
            c->zero_prefix = (random & 2) != 0; c->active = true;
        }
        local = remote;
        uint8_t packet[512], result[72]; unsigned frames, bytes;
        assert(aw_audio_prepare_m3(&remote, packet, sizeof(packet), 1 + test % 64, 1000,
                                   (uint16_t)test, &frames, &bytes));
        int16_t reference[64]; assert(aw_audio_render(&local, reference, frames));
        stm3_job job = {packet, bytes, result, sizeof(result), 0, 0};
        uint32_t status = module_entry(STM3_INIT, NULL, &job);
        while (status == STM3_MORE) status = module_entry(STM3_STEP, NULL, &job);
        assert(status == STM3_DONE && job.output_bytes == frames + 8);
        for (unsigned i = 0; i < frames; ++i) assert(result[8+i] == 128 + reference[i] / 512);
        for (unsigned ch = 0; ch < 4; ++ch) {
            assert(remote.channels[ch].active == local.channels[ch].active);
            assert(remote.channels[ch].position == local.channels[ch].position);
        }
    }
    puts("Another World mono audio tests passed"); return 0;
}
