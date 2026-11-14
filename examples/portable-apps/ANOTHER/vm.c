/* Another World bytecode semantics based on Raw, Copyright (C) 2004 Gregory
 * Montoir, GPL-2.0-or-later. Resource addresses are offsets into PSRAM. */
#include "vm.h"
#include "text.h"
#include <string.h>

static const uint8_t parts[10][4] = {
    {0x14,0x15,0x16,0}, {0x17,0x18,0x19,0}, {0x1A,0x1B,0x1C,0x11},
    {0x1D,0x1E,0x1F,0x11}, {0x20,0x21,0x22,0x11}, {0x23,0x24,0x25,0},
    {0x26,0x27,0x28,0x11}, {0x29,0x2A,0x2B,0x11}, {0x7D,0x7E,0x7F,0},
    {0x7D,0x7E,0x7F,0}
};

static bool load(aw_vm *v, unsigned id) {
    if (id >= v->assets->count || !aw_assets_load(v->assets, id)) return !(v->fault = true);
    const aw_asset_entry *e = &v->assets->entries[id];
    if (e->type == 2) return aw_video_bitmap(v->video, e->store_offset, e->size) || !(v->fault = true);
    v->loaded[id] = 1; return true;
}
static uint8_t byte(aw_vm *v) {
    uint8_t b = 0;
    const aw_asset_entry *e = &v->assets->entries[v->code_id];
    if (v->cursor >= e->size || !aw_assets_read(v->assets, e->store_offset + v->cursor, &b, 1)) {
        v->fault = true; return 0;
    }
    ++v->cursor; return b;
}
static uint16_t word(aw_vm *v) {
    const uint16_t high = byte(v); return (uint16_t)((high << 8) | byte(v));
}
static bool text(aw_vm *v, uint16_t id, uint16_t x, uint16_t y, uint8_t color) {
    const uint8_t *p = (const uint8_t *)aw_text(id);
    if (!p) return true;
    const uint16_t origin = x;
    for (; *p; ++p) {
        if (*p == '\n') { y = (uint16_t)(y + 8); x = origin; }
        else {
            if (*p >= 32 && *p < 128 && !aw_video_char(v->video, x, y, color, aw_font + (*p - 32) * 8)) return false;
            ++x;
        }
    }
    return true;
}
bool aw_vm_init(aw_vm *v, aw_assets *a, aw_video *video, aw_vm_host host, uint16_t seed) {
    if (!v || !a || !video || a->count <= 0x7F) return false;
    memset(v, 0, sizeof(*v)); v->assets = a; v->video = video; v->host = host;
    v->vars[0x54] = 0x81; v->vars[0x3C] = (int16_t)seed; v->palette_request = 0xFF;
    return true;
}
bool aw_vm_set_part(aw_vm *v, uint16_t part) {
    if (!v || v->fault || part < AW_VM_FIRST_PART || part > AW_VM_LAST_PART) return false;
    if (v->host.stop_audio) v->host.stop_audio(v->host.ctx);
    v->vars[0xE4] = 0x14;
    if (part != v->part) {
        /* The original DOS executable sets this after copy protection.  Some
         * releases skip that screen entirely, but still need the variable for
         * the password screen and other later scripts. */
        if (v->part == AW_VM_FIRST_PART) v->vars[0xDC] = 33;
        memset(v->loaded, 0, sizeof(v->loaded));
        const uint8_t *p = parts[part - AW_VM_FIRST_PART];
        for (unsigned i = 0; i < 4; ++i) if (p[i] && !load(v, p[i])) return false;
        v->palette_id = p[0]; v->code_id = p[1]; v->polygon_id = p[2]; v->polygon2_id = p[3];
        v->part = part;
    }
    for (unsigned i = 0; i < AW_VM_THREADS; ++i) v->pc[i] = v->requested_pc[i] = 0xFFFF;
    memset(v->paused, 0, sizeof(v->paused)); memset(v->requested_pause, 0, sizeof(v->requested_pause));
    v->pc[0] = 0; v->next_part = 0;
    return true;
}
static void input_vars(aw_vm *v, aw_input *input) {
    if (v->part == AW_VM_LAST_PART) {
        const uint8_t c = input->last_char;
        if (c == 8 || !c || (c >= 'a' && c <= 'z')) { v->vars[0xDA] = c & ~0x20; input->last_char = 0; }
    }
    int16_t lr = 0, ud = 0, mask = 0;
    if (input->directions & AW_INPUT_RIGHT) { lr = 1; mask |= 1; }
    if (input->directions & AW_INPUT_LEFT) { lr = -1; mask |= 2; }
    if (input->directions & AW_INPUT_DOWN) { ud = 1; mask |= 4; }
    v->vars[0xE5] = ud;
    if (input->directions & AW_INPUT_UP) { ud = -1; v->vars[0xE5] = -1; mask |= 8; }
    v->vars[0xFB] = ud; v->vars[0xFC] = lr; v->vars[0xFD] = mask;
    v->vars[0xFA] = input->button ? 1 : 0;
    v->vars[0xFE] = input->button ? (mask | 0x80) : mask;
    if (input->code) {
        input->code = false;
        if (v->part != AW_VM_LAST_PART && v->part != AW_VM_FIRST_PART) v->next_part = AW_VM_LAST_PART;
    }
}
static bool draw(aw_vm *v, unsigned id, uint16_t offset, uint16_t zoom, int16_t x, int16_t y) {
    if (!id || id >= v->assets->count || !v->loaded[id]) return !(v->fault = true);
    const aw_asset_entry *e = &v->assets->entries[id];
    if (!aw_video_polygon(v->video, e->store_offset, e->size, offset, zoom, x, y)) return !(v->fault = true);
    return true;
}
static bool run_thread(aw_vm *v) {
    bool done = false;
    for (unsigned instructions = 0; !done && !v->fault && instructions < 100000u; ++instructions) {
        if (!(instructions & 255u) && v->host.pump) v->host.pump(v->host.ctx);
        const uint8_t op = byte(v);
        if (op & 0x80) {
            const uint16_t offset = (uint16_t)(((op << 8) | byte(v)) * 2);
            int16_t x = byte(v), y = byte(v);
            if (y > 199) { x = (int16_t)(x + y - 199); y = 199; }
            if (!draw(v, v->polygon_id, offset, 64, x, y)) return false;
            continue;
        }
        if (op & 0x40) {
            const uint16_t offset = (uint16_t)(word(v) * 2);
            int16_t x = byte(v);
            if (!(op & 0x20)) x = !(op & 0x10) ? (int16_t)((x << 8) | byte(v)) : v->vars[(uint8_t)x];
            else if (op & 0x10) x = (int16_t)(x + 256);
            int16_t y = byte(v);
            if (!(op & 8)) y = !(op & 4) ? (int16_t)((y << 8) | byte(v)) : v->vars[(uint8_t)y];
            uint16_t zoom = byte(v); unsigned shape_id = v->polygon_id;
            if (!(op & 2)) {
                if (!(op & 1)) { --v->cursor; zoom = 64; }
                else zoom = (uint16_t)v->vars[zoom];
            } else if (op & 1) { --v->cursor; zoom = 64; shape_id = v->polygon2_id; }
            if (!draw(v, shape_id, offset, zoom, x, y)) return false;
            continue;
        }
        uint8_t a, b; uint16_t n;
        switch (op) {
        case 0x00: a = byte(v); v->vars[a] = (int16_t)word(v); break;
        case 0x01: a = byte(v); b = byte(v); v->vars[a] = v->vars[b]; break;
        case 0x02: a = byte(v); b = byte(v); v->vars[a] = (int16_t)((uint16_t)v->vars[a] + (uint16_t)v->vars[b]); break;
        case 0x03: a = byte(v); n = word(v); v->vars[a] = (int16_t)((uint16_t)v->vars[a] + n); break;
        case 0x04:
            n = word(v);
            if (v->sp >= 64) return !(v->fault = true);
            v->stack[v->sp++] = (uint16_t)v->cursor; v->cursor = n; break;
        case 0x05:
            if (!v->sp) return !(v->fault = true);
            v->cursor = v->stack[--v->sp]; break;
        case 0x06: done = true; break;
        case 0x07: v->cursor = word(v); break;
        case 0x08:
            a = byte(v); n = word(v);
            if (a >= AW_VM_THREADS) return !(v->fault = true);
            v->requested_pc[a] = n; break;
        case 0x09:
            a = byte(v); n = word(v); v->vars[a] = (int16_t)((uint16_t)v->vars[a] - 1u);
            if (v->vars[a]) v->cursor = n;
            break;
        case 0x0A: {
            a = byte(v); b = byte(v);
            const int16_t lhs = v->vars[b];
            int16_t rhs;
            if (a & 0x80) rhs = v->vars[byte(v)];
            else if (a & 0x40) rhs = (int16_t)word(v);
            else rhs = byte(v);
            n = word(v); bool condition;
            switch (a & 7) {
            case 0: condition = lhs == rhs; break; case 1: condition = lhs != rhs; break;
            case 2: condition = lhs > rhs; break; case 3: condition = lhs >= rhs; break;
            case 4: condition = lhs < rhs; break; case 5: condition = lhs <= rhs; break;
            default: return !(v->fault = true);
            }
            if (condition) v->cursor = n;
            break;
        }
        case 0x0B: v->palette_request = (uint8_t)(word(v) >> 8); break;
        case 0x0C: {
            a = byte(v); b = byte(v) & 63u; const uint8_t action = byte(v);
            if (a >= AW_VM_THREADS || b < a || action > 2) return !(v->fault = true);
            for (unsigned i = a; i <= b; ++i) {
                if (action == 2) v->requested_pc[i] = 0xFFFE;
                else v->requested_pause[i] = action;
            }
            break;
        }
        case 0x0D: if (!aw_video_select(v->video, byte(v))) return !(v->fault = true); break;
        case 0x0E: a = byte(v); b = byte(v); if (!aw_video_fill(v->video, a, b)) return !(v->fault = true); break;
        case 0x0F: a = byte(v); b = byte(v); if (!aw_video_copy(v->video, a, b, v->vars[0xF9])) return !(v->fault = true); break;
        case 0x10: {
            a = byte(v); const unsigned delay = v->vars[0xFF] < 0 ? 0 : (unsigned)v->vars[0xFF];
            if (v->part == AW_VM_FIRST_PART && v->vars[0x67] == 1) v->vars[0xDC] = 33;
            if (v->host.frame_wait && !v->host.frame_wait(v->host.ctx, delay)) return false;
            if (v->palette_request != 0xFF) {
                const aw_asset_entry *p = &v->assets->entries[v->palette_id];
                if (!aw_video_palette(v->video, p->store_offset, p->size, v->palette_request)) return !(v->fault = true);
                v->palette_request = 0xFF;
            }
            v->vars[0xF7] = 0;
            if (!aw_video_show(v->video, a)) return !(v->fault = true);
            break;
        }
        case 0x11: v->cursor = 0xFFFF; done = true; break;
        case 0x12: {
            n = word(v); a = byte(v); b = byte(v); const uint8_t color = byte(v);
            if (!text(v, n, a, b, color)) return !(v->fault = true);
            break;
        }
        case 0x13: a = byte(v); b = byte(v); v->vars[a] = (int16_t)((uint16_t)v->vars[a] - (uint16_t)v->vars[b]); break;
        case 0x14: a = byte(v); n = word(v); v->vars[a] = (int16_t)((uint16_t)v->vars[a] & n); break;
        case 0x15: a = byte(v); n = word(v); v->vars[a] = (int16_t)((uint16_t)v->vars[a] | n); break;
        case 0x16: a = byte(v); n = word(v); v->vars[a] = n < 16 ? (int16_t)((uint16_t)v->vars[a] << n) : 0; break;
        case 0x17: a = byte(v); n = word(v); v->vars[a] = n < 16 ? (int16_t)((uint16_t)v->vars[a] >> n) : 0; break;
        case 0x18: {
            n = word(v); const uint8_t freq = byte(v), volume = byte(v), channel = byte(v);
            if (n < v->assets->count && v->loaded[n] && v->host.sound)
                v->host.sound(v->host.ctx, n, freq, volume, channel & 3);
            break;
        }
        case 0x19:
            n = word(v);
            if (!n) {
                if (v->host.stop_audio) v->host.stop_audio(v->host.ctx);
                for (unsigned i = 0; i < v->assets->count; ++i)
                    if (v->assets->entries[i].type <= 2 || v->assets->entries[i].type > 6) v->loaded[i] = 0;
            } else if (n >= AW_VM_FIRST_PART && n <= AW_VM_LAST_PART) v->next_part = n;
            else if (n >= v->assets->count || (!v->loaded[n] && !load(v, n))) return !(v->fault = true);
            break;
        case 0x1A:
            n = word(v); { const uint16_t delay = word(v); a = byte(v);
            if (v->host.music) v->host.music(v->host.ctx, n, delay, a); } break;
        default: return !(v->fault = true);
        }
    }
    if (!done) v->fault = true;
    return !v->fault;
}
bool aw_vm_frame(aw_vm *v, aw_input *input) {
    if (!v || !input || v->fault || !v->part) return false;
    if (v->next_part && !aw_vm_set_part(v, v->next_part)) return false;
    for (unsigned i = 0; i < AW_VM_THREADS; ++i) {
        v->paused[i] = v->requested_pause[i];
        if (v->requested_pc[i] != 0xFFFF) {
            v->pc[i] = v->requested_pc[i] == 0xFFFE ? 0xFFFF : v->requested_pc[i];
            v->requested_pc[i] = 0xFFFF;
        }
    }
    input_vars(v, input);
    for (unsigned i = 0; i < AW_VM_THREADS && !input->quit; ++i) if (!v->paused[i] && v->pc[i] != 0xFFFF) {
        v->cursor = v->pc[i]; v->sp = 0;
        if (!run_thread(v)) return false;
        v->pc[i] = (uint16_t)v->cursor;
    }
    return !v->fault;
}
