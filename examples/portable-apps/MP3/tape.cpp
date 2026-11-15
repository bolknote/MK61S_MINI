#include "screen.hpp"
#include <cstring>

namespace mp3 {
namespace {
constexpr unsigned tape_header_bytes = 52, phases = 32;
constexpr unsigned half_width = screen_width / 2;
constexpr unsigned base_bands = screen_width / strip_height;
constexpr unsigned transparent = 0;

const char* tape_path(TapeView view) {
    return view == TapeView::cassette ? "CASSETTE.TV" : "REEL.TV";
}

bool read_at(const mk61_app_services* services, const char* path, void* data, unsigned at, unsigned size) {
    mk61_service_file_bytes request{path, data, at, size};
    return services->call(MK61_SERVICE_FILE_BYTES, MK61_FILE_BYTES_READ, 0, sizeof(request), &request);
}

unsigned root(unsigned value) {
    unsigned result = 0;
    for (unsigned bit = 1u << 7; bit; bit >>= 1) {
        const unsigned candidate = result | bit;
        if (candidate * candidate <= value) result = candidate;
    }
    return result;
}
}

bool Screen::select_tape(TapeView view) {
    uint8_t header[tape_header_bytes];
    if (!raster || view == TapeView::none ||
        !read_at(services, tape_path(view), header, 0, sizeof(header)) || std::memcmp(header, "TV01", 4)) return false;
    for (unsigned i = 36; i < sizeof(header); ++i) if (header[i] >= 16) return false;
    for (unsigned i = 0; i < 16; ++i) palette[i] = header[4 + i * 2] | (header[5 + i * 2] << 8);
    std::memcpy(ring_color, header + 36, sizeof(ring_color));
    tape = view;
    return true;
}

bool Screen::read_tape_chunk(unsigned id, int side) {
    uint8_t entry[6];
    const char* path = tape_path(tape);
    if (!read_at(services, path, entry, tape_header_bytes + id * sizeof(entry), sizeof(entry))) return false;
    const uint32_t offset = uint32_t(entry[0]) | uint32_t(entry[1]) << 8 | uint32_t(entry[2]) << 16 | uint32_t(entry[3]) << 24;
    const unsigned size = entry[4] | (entry[5] << 8);
    if (!size || size > tape_chunk_bytes || !read_at(services, path, raster, offset, size)) return false;
    const unsigned row_bytes = side < 0 ? screen_width / 2 : half_width / 2;
    const unsigned expected = row_bytes * strip_height;
    unsigned input = 0, output = 0, column = 0;
    uint8_t* dest = strip + (side > 0 ? half_width / 2 : 0);
    while (input < size) {
        const unsigned token = raster[input++];
        const unsigned count = (token & 127) + 1;
        const bool repeat = token >= 128;
        if (count > expected - output || (repeat ? 1U : count) > size - input) return false;
        if (side < 0) {
            if (repeat) std::memset(dest + output, raster[input], count);
            else std::memcpy(dest + output, raster + input, count);
        } else {
            for (unsigned i = 0; i < count; ++i) {
                const unsigned pair = raster[input + (repeat ? 0 : i)];
                if ((pair >> 4) != transparent) *dest = (*dest & 15) | (pair & 240);
                if ((pair & 15) != transparent) *dest = (*dest & 240) | (pair & 15);
                ++dest;
                if (++column == row_bytes) {
                    if (output + i + 1 < expected) dest += row_bytes;
                    column = 0;
                }
            }
        }
        input += repeat ? 1 : count;
        output += count;
    }
    return output == expected;
}

void Screen::tape_pose(unsigned position, unsigned duration, uint32_t played_ms, uint32_t levels) {
    const bool cassette = tape == TapeView::cassette;
    if (position > duration) position = duration;
    const unsigned progress = duration ? (uint64_t(position) * 1024) / duration : 0;
    const unsigned core = cassette ? 20 : 26;
    const unsigned rim = cassette ? 53 : 73;
    const unsigned delta = played_ms - tape_time;
    tape_time = played_ms;
    for (unsigned side = 0; side < 2; ++side) {
        const unsigned fraction = side ? progress : 1024 - progress;
        spool_radius[side] = root(core * core + fraction * (rim * rim - core * core) / 1024);
        spool_phase[side] += uint64_t(delta) * (cassette ? 18 : 25) * rim / spool_radius[side];
        const int level = (int16_t)(levels >> (16 * side));
        const unsigned peak = level < 0 ? -level : level;
        const unsigned deflection = root(peak / 32);
        needle[side] = deflection > 15 ? 15 : deflection;
    }
}

void Screen::line(int x0, int y0, int x1, int y1, unsigned color, unsigned width) {
    const int d = x1 - x0, e = y1 - y0;
    const int dx = d < 0 ? -d : d, dy = e < 0 ? -e : e;
    const int sx = d < 0 ? -1 : 1, sy = e < 0 ? -1 : 1;
    int error = dx - dy;
    for (;;) {
        rect(x0, y0, width, width, color);
        if (x0 == x1 && y0 == y1) break;
        const int twice = error * 2;
        if (twice > -dy) { error -= dy; x0 += sx; }
        if (twice < dx) { error += dx; y0 += sy; }
    }
}

void Screen::paint_spool(unsigned side) {
    const bool cassette = tape == TapeView::cassette;
    const int radius = (int)spool_radius[side];
    const int cx = cassette ? (side ? 226 : 94) : (side ? 240 : 80);
    const int cy = cassette ? 111 : 77;
    if (!cassette && top + (int)strip_height > 48) {
        const int gx = side ? 266 : 54, gy = 174;
        const int dx = gx - cx, dy = gy - cy;
        const int square = dx * dx + dy * dy;
        const int scaled_radius = radius - 7;
        const int tangent = (int)root(square - scaled_radius * scaled_radius) * (side ? -1 : 1);
        const int x = scaled_radius * dx - tangent * dy;
        const int y = scaled_radius * dy + tangent * dx;
        const int x0 = cx + (radius - 1) * x / square, y0 = cy + (radius - 1) * y / square;
        const int x1 = gx + 8 * x / square, y1 = gy + 8 * y / square;
        if (top <= y1 && y0 < top + (int)strip_height) {
            line(x0 - 1, y0, x1 - 1, y1, background, 3);
            line(x0, y0, x1, y1, 9, 2);
            line(x0, y0 - 1, x1, y1 - 1, 10);
        }
    }
    int limit[16];
    for (int i = 0; i < 16; ++i) limit[i] = (radius * (i + 1)) * (radius * (i + 1));
    for (int yy = top; yy < top + (int)strip_height; ++yy) {
        if (cassette && (yy < 86 || yy > 138)) continue;
        const int dy = (yy - cy) * 33;
        if (dy * dy > radius * radius * 1024) continue;
        const int dy_squared = dy * dy / 4;
        unsigned ring = 0;
        for (int x = 0; x <= radius; ++x) {
            const int square = dy_squared + x * x * 256;
            if (square > limit[15]) break;
            while (ring < 15 && limit[ring] < square) ++ring;
            const unsigned color = ring_color[ring];
            if (!cassette || cx + x <= 274) pixel(cx + x, yy, color);
            if (x && (!cassette || cx - x >= 45)) pixel(cx - x, yy, color);
        }
    }
}

bool Screen::read_tape_band(unsigned y, unsigned layer) {
    if (!layer) {
        top = (int)y;
        return read_tape_chunk(y / strip_height, -1);
    }
    const bool cassette = tape == TapeView::cassette;
    const unsigned art_top = tape_top(), bands = cassette ? 4 : 12;
    if (y < art_top || y >= art_top + bands * strip_height) return true;
    const unsigned side = layer - 1;
    const unsigned phase = (spool_phase[side] >> 11) & (phases - 1);
    paint_spool(side);
    return read_tape_chunk(base_bands + (side * phases + phase) * bands + (y - art_top) / strip_height, side);
}

void Screen::paint_tape(unsigned y, const char* title, const char* artist, unsigned position, unsigned duration,
                        unsigned volume, bool playing, bool shuffle, unsigned repeat, const char* status) {
    const bool cassette = tape == TapeView::cassette;
    if (cassette) {
        text(32, 48, title, background, 257, false, 2);
        text(32, 72, artist, 7, 255);
        if (y >= 80 && y < 144) {
            line(45, 88, 61, 86, 7);
            for (int x = 143; x <= 177; x += 34) {
                rect(x, 125, 1, 13, 7);
                rect(x + 1, 125, 1, 13, background);
            }
        }
    } else {
        text(13, 236, title, light, 244, false, 2);
        text(13, 262, artist, muted, 144);
        if (y == 208) {
            static const int8_t knob_x[] = {-19,-17,-15,-13,-10,-8,-5,-2,1,4,7,10,12,15,17,19};
            static const int8_t knob_y[] = {-11,-14,-16,-18,-19,-20,-21,-22,-22,-22,-21,-20,-18,-16,-14,-11};
            for (unsigned side = 0; side < 2; ++side) {
                const int cx = side ? 265 : 56;
                const unsigned n = needle[side];
                line(cx, 221, cx + knob_x[n], 225 + knob_y[n], 8);
                text(cx - 33, 210, side ? "R" : "L", background, 6);
            }
        }
    }
    if (y >= 192 && y < 280) tape_status(position, duration, volume, playing, status);
    if (y >= 288) transport_keys(shuffle, repeat, true);
}
}
