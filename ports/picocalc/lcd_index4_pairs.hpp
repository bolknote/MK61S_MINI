#ifndef MK61_PICOCALC_LCD_INDEX4_PAIRS_HPP
#define MK61_PICOCALC_LCD_INDEX4_PAIRS_HPP

#include "lcd_update.hpp"
#include "loadable_app_services.h"

namespace picocalc::lcd {

// Two little-endian RGB565 words in the order consumed by the LCD DMA.
class Index4Pairs {
public:
    void refresh(const uint16_t* colors) {
        if (valid_ && std::memcmp(palette_, colors, sizeof(palette_)) == 0) return;
        for (unsigned high = 0; high < 16; ++high) {
            const uint32_t first = colors[high];
            for (unsigned low = 0; low < 16; ++low)
                words_[16 * high + low] = first | (uint32_t(colors[low]) << 16);
        }
        std::memcpy(palette_, colors, sizeof(palette_));
        valid_ = true;
    }

#if defined(PICO_ON_DEVICE) && defined(__GNUC__)
    // Keep the scalar fallback inlined in the worker's original call sites.
    __attribute__((noinline))
#endif
    void line(const mk61_service_color_frame& f, const Rect& r, unsigned row,
              uint16_t* out, void (*progress)() = nullptr) const {
        unsigned x = r.x - f.x;
        const unsigned y = r.y - f.y + row;
        const uint8_t* packed = f.pixels + y * ((f.width + 1u) / 2);
        unsigned remaining = r.width;
        while (remaining) {
            const unsigned count = progress && remaining > 64 ? 64 : remaining;
            span(packed, x, count, out);
            if (progress) progress();
            remaining -= count;
            x += count;
            out += count;
        }
    }

private:
    void span(const uint8_t* p, unsigned x, unsigned count, uint16_t* out) const {
        p += x / 2;
        if (x & 1) {
            *out++ = static_cast<uint16_t>(words_[*p++] >> 16);
            --count;
        }
        const unsigned pairs = count / 2;
#if defined(__GNUC__) && __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
        if ((reinterpret_cast<uintptr_t>(out) & 3u) == 0) {
            auto* aligned = static_cast<uint16_t*>(__builtin_assume_aligned(out, 4));
            for (unsigned i = 0; i < pairs; ++i) {
                const uint32_t pair = words_[p[i]];
                __builtin_memcpy(aligned + 2 * i, &pair, sizeof(pair));
            }
        } else
#endif
        {
            for (unsigned i = 0; i < pairs; ++i) {
                const uint32_t pair = words_[p[i]];
                out[2 * i] = static_cast<uint16_t>(pair);
                out[2 * i + 1] = static_cast<uint16_t>(pair >> 16);
            }
        }
        if (count & 1) out[count - 1] = static_cast<uint16_t>(words_[p[pairs]]);
    }

    uint32_t words_[256];
    uint16_t palette_[16];
    bool valid_ = false;
};
}
#endif
