/* Four-channel DOS sample player and tracker semantics based on Raw,
 * Copyright (C) 2004 Gregory Montoir, GPL-2.0-or-later. */
#include "audio.h"
#include "m3_pcm.h"
#include <string.h>

static const uint16_t frequencies[40] = {
    0x0CFF,0x0DC3,0x0E91,0x0F6F,0x1056,0x114E,0x1259,0x136C,
    0x149F,0x15D9,0x1726,0x1888,0x19FD,0x1B86,0x1D21,0x1EDE,
    0x20AB,0x229C,0x24B3,0x26D7,0x293F,0x2BB2,0x2E4C,0x3110,
    0x33FB,0x370D,0x3A43,0x3DDF,0x4157,0x4538,0x4998,0x4DAE,
    0x5240,0x5764,0x5C9A,0x61C8,0x6793,0x6E19,0x7485,0x7BBD
};
static bool read_resource(aw_audio *a, unsigned id, uint32_t offset, void *out, uint32_t size) {
    if (id >= a->assets->count || !a->vm->loaded[id]) return false;
    const aw_asset_entry *e = &a->assets->entries[id];
    if (offset > e->size || size > e->size - offset) return false;
    return aw_assets_read(a->assets, e->store_offset + offset, out, size);
}
static uint16_t be16(const uint8_t *p) { return (uint16_t)(((uint16_t)p[0] << 8) | p[1]); }
void aw_audio_init(aw_audio *a, aw_assets *assets, aw_vm *vm) {
    memset(a, 0, sizeof(*a)); a->assets = assets; a->vm = vm;
}
void aw_audio_stop(aw_audio *a) {
    if (!a) return;
    memset(a->channels, 0, sizeof(a->channels)); a->music_active = false; a->resource = 0;
}
static void play(aw_audio *a, unsigned id, unsigned freq, unsigned volume, unsigned channel, bool zero) {
    if (channel >= 4) return;
    aw_audio_channel *c = &a->channels[channel];
    uint8_t header[4];
    if (!read_resource(a, id, 0, header, sizeof(header))) { c->active = false; return; }
    const uint32_t length = (uint32_t)be16(header) * 2, loop = (uint32_t)be16(header + 2) * 2;
    const aw_asset_entry *e = &a->assets->entries[id];
    if (!length || length + loop > 65535u || length + loop + 8u > e->size || !freq) {
        c->active = false; return;
    }
    c->data = e->store_offset + 8; c->length = (uint16_t)length;
    c->loop = (uint16_t)length; c->loop_length = (uint16_t)loop;
    c->position = 0; c->increment = (freq << 8) / AW_AUDIO_RATE;
    c->volume = volume > 63 ? 63 : (uint8_t)volume; c->zero_prefix = zero; c->active = true;
}
void aw_audio_sound(aw_audio *a, unsigned id, unsigned frequency_index, unsigned volume, unsigned channel) {
    if (!a || channel >= 4) return;
    if (!volume) { a->channels[channel].active = false; return; }
    if (frequency_index < 40) play(a, id, frequencies[frequency_index], volume, channel, false);
}
static uint32_t event_period(unsigned delay) {
    const uint32_t samples = (uint32_t)delay * 1500u / 7050u;
    return samples ? samples : 1;
}
void aw_audio_music(aw_audio *a, unsigned id, unsigned delay, unsigned position) {
    if (!a) return;
    if (!id) {
        if (delay) a->delay = (uint16_t)delay;
        else { a->music_active = false; a->resource = 0; }
        return;
    }
    uint8_t header[0xC0];
    if (!read_resource(a, id, 0, header, sizeof(header))) { a->music_active = false; return; }
    const unsigned count = be16(header + 0x3E);
    if (!count || count > 128 || position >= count) { a->music_active = false; return; }
    a->resource = (uint16_t)id; a->row = 0; a->order = (uint8_t)position; a->order_count = (uint8_t)count;
    memcpy(a->orders, header + 0x40, sizeof(a->orders));
    for (unsigned i = 0; i < 15; ++i) {
        a->instruments[i] = be16(header + 2 + 4 * i);
        a->volumes[i] = be16(header + 4 + 4 * i);
    }
    a->delay = (uint16_t)(delay ? delay : be16(header));
    a->until_event = event_period(a->delay); a->music_active = true;
}
static void music_event(aw_audio *a) {
    uint8_t pattern[16];
    const uint32_t pos = 0xC0u + (uint32_t)a->orders[a->order] * 1024u + a->row;
    if (!read_resource(a, a->resource, pos, pattern, sizeof(pattern))) {
        a->music_active = false; return;
    }
    for (unsigned ch = 0; ch < 4; ++ch) {
        const uint16_t note = be16(pattern + ch * 4), effect = be16(pattern + ch * 4 + 2);
        const unsigned sample = effect >> 12;
        unsigned id = 0, volume = 0;
        if (note != 0xFFFD && sample && sample <= 15) {
            id = a->instruments[sample - 1]; volume = a->volumes[sample - 1];
            const unsigned code = (effect >> 8) & 15, value = effect & 255;
            if (code == 5) volume = volume + value > 63 ? 63 : volume + value;
            else if (code == 6) volume = volume < value ? 0 : volume - value;
            if (volume > 63) volume = 63;
            a->channels[ch].volume = (uint8_t)volume;
        }
        if (note == 0xFFFD) a->vm->vars[0xF4] = (int16_t)effect;
        else if (note == 0xFFFE) a->channels[ch].active = false;
        else if (note && id && note >= 0x37 && note < 0x1000)
            play(a, id, 7159092u / ((uint32_t)note * 2), volume, ch, true);
    }
    a->row = (uint16_t)(a->row + 16);
    if (a->row >= 1024) {
        a->row = 0;
        if (++a->order >= a->order_count) {
            a->music_active = false; a->resource = 0;
            for (unsigned i = 0; i < 4; ++i) a->channels[i].active = false;
        }
    }
}
static bool mix_span(aw_audio *a, int16_t *out, unsigned count) {
    int8_t mixed[AW_AUDIO_BLOCK] = {0};
    /* Even the highest valid tracker note needs at most 312 source bytes
     * for 120 output samples. Stage contiguous windows instead of asking
     * the PSRAM cache twice for every generated sample. */
    uint8_t source[320];
    for (unsigned ch = 0; ch < 4; ++ch) {
        aw_audio_channel *c = &a->channels[ch];
        if (!c->active) continue;
        const uint32_t end = (uint32_t)c->length + c->loop_length;
        if ((c->position >> 8) >= end) {
            if (!c->loop_length) { c->active = false; continue; }
            c->position = ((uint32_t)c->loop << 8) +
                          (c->position - (end << 8)) % ((uint32_t)c->loop_length << 8);
        }
        const uint32_t start = c->position >> 8, fraction = c->position & 255;
        const uint32_t needed = ((fraction + (count - 1) * c->increment) >> 8) + 2;
        if (needed > sizeof(source)) return !(a->fault = true);
        uint32_t pos = start, loaded = 0;
        while (loaded < needed) {
            if (pos >= end) {
                if (c->loop_length) pos = c->loop;
                else { memset(source + loaded, loaded ? source[loaded - 1] : 0, needed - loaded); break; }
            }
            uint32_t n = end - pos;
            if (n > needed - loaded) n = needed - loaded;
            if (!aw_assets_read(a->assets, c->data + pos, source + loaded, n)) return !(a->fault = true);
            if (c->zero_prefix && pos < 4) {
                unsigned zero = 4 - pos; if (zero > n) zero = n;
                memset(source + loaded, 0, zero);
            }
            loaded += n; pos += n;
        }
        for (unsigned i = 0; i < count && c->active; ++i) {
            const uint32_t phase = fraction + i * c->increment, index = phase >> 8;
            if (!c->loop_length && start + index >= end) { c->active = false; break; }
            const unsigned frac = phase & 255;
            const int value = ((int8_t)source[index] * (int)(255 - frac) +
                               (int8_t)source[index + 1] * (int)frac) >> 8;
            int sum = mixed[i] + value * c->volume / 64;
            if (sum < -128) sum = -128; else if (sum > 127) sum = 127;
            mixed[i] = (int8_t)sum; c->position += c->increment;
        }
        if (c->loop_length && (c->position >> 8) >= end)
            c->position = ((uint32_t)c->loop << 8) +
                          (c->position - (end << 8)) % ((uint32_t)c->loop_length << 8);
    }
    for (unsigned i = 0; i < count; ++i) out[i] = (int16_t)((int)mixed[i] * 256);
    return true;
}
bool aw_audio_render(aw_audio *a, int16_t *out, unsigned count) {
    if (!a || (!out && count) || a->fault) return false;
    while (count) {
        unsigned span = count < AW_AUDIO_BLOCK ? count : AW_AUDIO_BLOCK;
        if (a->music_active && a->until_event < span) span = a->until_event;
        if (span && !mix_span(a, out, span)) return false;
        out += span; count -= span;
        if (a->music_active) {
            a->until_event -= span;
            if (!a->until_event) { music_event(a); a->until_event = event_period(a->delay); }
        }
    }
    return true;
}

bool aw_audio_prepare_m3(aw_audio *a, uint8_t *packet, unsigned capacity,
                         unsigned max_frames, unsigned gain, uint16_t sequence,
                         unsigned *frames, unsigned *bytes) {
    if (!a || !packet || !frames || !bytes || a->fault || capacity < AW_M3_HEADER || capacity > AW_M3_MAX_INPUT ||
        !max_frames || max_frames > AW_M3_MAX_FRAMES || gain > 1000 || (a->music_active && !a->until_event)) return false;
    unsigned count = max_frames;
    if (a->music_active && a->until_event < count) count = a->until_event;
    struct window { uint32_t position, end; unsigned active, needed; } windows[4];
    for (;;) {
        unsigned total = AW_M3_HEADER;
        memset(windows, 0, sizeof(windows));
        for (unsigned ch = 0; ch < 4; ++ch) {
            const aw_audio_channel *c = &a->channels[ch];
            if (!c->active) continue;
            if (!c->increment || c->increment > 1024 || c->volume > 63) return false;
            struct window *w = &windows[ch];
            w->end = (uint32_t)c->length + c->loop_length; w->position = c->position;
            if (!w->end) return false;
            if ((w->position >> 8) >= w->end) {
                if (!c->loop_length) continue;
                w->position = ((uint32_t)c->loop << 8) +
                    (w->position - (w->end << 8)) % ((uint32_t)c->loop_length << 8);
            }
            w->active = count;
            if (!c->loop_length) {
                const uint32_t remaining = (w->end << 8) - w->position;
                const uint32_t available = (remaining + c->increment - 1) / c->increment;
                if (w->active > available) w->active = available;
            }
            if (!w->active) continue;
            w->needed = (((w->position & 255) + (w->active - 1) * c->increment) >> 8) + 2;
            if (w->needed > 255) return false;
            total += w->needed;
        }
        if (total <= capacity) break;
        if (--count == 0) return false;
    }
    memset(packet, 0, AW_M3_HEADER); aw_m3_put32(packet, AW_M3_MAGIC); aw_m3_put16(packet + 4, sequence);
    packet[6] = (uint8_t)count; aw_m3_put16(packet + 8, (uint16_t)gain);
    unsigned used = AW_M3_HEADER;
    for (unsigned ch = 0; ch < 4; ++ch) {
        aw_audio_channel *c = &a->channels[ch]; const struct window *w = &windows[ch];
        if (!w->active) { if (c->active) c->active = false; continue; }
        uint8_t *d = packet + 12 + 8 * ch; packet[7] |= (uint8_t)(1u << ch);
        aw_m3_put16(d, (uint16_t)used); d[2] = (uint8_t)w->needed; d[3] = (uint8_t)w->active;
        d[4] = (uint8_t)w->position; d[5] = c->volume; aw_m3_put16(d + 6, (uint16_t)c->increment);
        uint32_t pos = w->position >> 8, written = 0;
        while (written < w->needed) {
            if (pos >= w->end) {
                if (c->loop_length) pos = c->loop;
                else { memset(packet + used + written, written ? packet[used + written - 1] : 0, w->needed - written); break; }
            }
            unsigned n = w->end - pos;
            if (n > w->needed - written) n = w->needed - written;
            if (!aw_assets_read(a->assets, c->data + pos, packet + used + written, n)) return !(a->fault = true);
            if (c->zero_prefix && pos < 4) {
                unsigned zero = 4 - pos; if (zero > n) zero = n;
                memset(packet + used + written, 0, zero);
            }
            pos += n; written += n;
        }
        used += w->needed;
        c->position = w->position + w->active * c->increment;
        if (!c->loop_length && w->active < count) c->active = false;
        if (c->loop_length && (c->position >> 8) >= w->end)
            c->position = ((uint32_t)c->loop << 8) +
                (c->position - (w->end << 8)) % ((uint32_t)c->loop_length << 8);
    }
    if (a->music_active) {
        a->until_event -= count;
        if (!a->until_event) { music_event(a); a->until_event = event_period(a->delay); }
    }
    *frames = count; *bytes = used;
    return true;
}
