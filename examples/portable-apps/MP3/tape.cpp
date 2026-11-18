#include "screen.hpp"
#include <cstring>

namespace mp3 {
namespace {
constexpr unsigned tape_header_bytes = 52;
constexpr unsigned half_width = screen_width / 2;
constexpr unsigned base_bands = screen_width / strip_height;
constexpr unsigned transparent = 0;
constexpr TapeView tape_views[] = {TapeView::cassette, TapeView::reel};

const char* tape_path(TapeView view) {
    return view == TapeView::cassette ? "CASSETTE.TV" : "REEL.TV";
}

bool read_at(const mk61_app_services* services, const char* path, void* data, unsigned at, unsigned size) {
    mk61_service_file_bytes request{path, data, at, size};
    return services->call(MK61_SERVICE_FILE_BYTES, MK61_FILE_BYTES_READ, 0, sizeof(request), &request);
}

unsigned tape_slot(TapeView view) { return view == TapeView::cassette ? 0 : 1; }

unsigned root(unsigned value) {
    unsigned result = 0;
    for (unsigned bit = 1u << 7; bit; bit >>= 1) {
        const unsigned candidate = result | bit;
        if (candidate * candidate <= value) result = candidate;
    }
    return result;
}
}

void Screen::cache_tapes() {
    if (!raster || tape_handle) return;
    constexpr unsigned max_tape_bytes = 2 * 1024 * 1024;
    unsigned total = 0;
    for (const auto view : tape_views) {
        mk61_service_file_info info{};
        mk61_service_file_bytes stat{tape_path(view), &info, 0, sizeof(info)};
        if (services->call(MK61_SERVICE_FILE_BYTES, MK61_FILE_BYTES_STAT, 0, sizeof(stat), &stat) &&
            !info.directory && info.size >= tape_header_bytes && info.size <= max_tape_bytes) {
            cached[tape_slot(view)] = {total, info.size};
            total += (info.size + 3) & ~3u;
        }
    }
    mk61_service_buffer cache{};
    if (!total || !mk61_app_buffer_acquire(services, total + tape_band_bytes * (base_bands + reel_bands),
                                          MK61_BUFFER_EXTERNAL, &cache)) return;
    tape_handle = cache.handle;
    tape_shadow = total;
    for (const auto view : tape_views) {
        auto& asset = cached[tape_slot(view)];
        for (unsigned at = 0; at < asset.size;) {
            const unsigned left = asset.size - at;
            const unsigned n = left < tape_chunk_bytes ? left : tape_chunk_bytes;
            if (!read_at(services, tape_path(view), raster, at, n) ||
                !tape_buffer(MK61_BUFFER_WRITE, asset.offset + at, raster, n)) {
                asset.size = 0;
                break;
            }
            at += n;
            mk61_api->service();
        }
    }
    if (!cached[0].size && !cached[1].size) release_tapes();
}

void Screen::release_tapes() {
    if (tape_handle) mk61_app_buffer_release(services, tape_handle);
    tape_handle = 0;
    invalidate_tape();
}

bool Screen::tape_buffer(unsigned operation, unsigned offset, void* data, unsigned size) {
    mk61_service_buffer request{};
    request.handle = tape_handle;
    request.offset = offset;
    request.size = size;
    request.data = static_cast<uint8_t*>(data);
    return services->call(MK61_SERVICE_BUFFER, operation, 0, sizeof(request), &request);
}

bool Screen::read_tape(TapeView view, void* data, unsigned offset, unsigned size) {
    auto& asset = cached[tape_slot(view)];
    if (tape_handle && asset.size) {
        if (offset > asset.size || size > asset.size - offset) return false;
        if (tape_buffer(MK61_BUFFER_READ, asset.offset + offset, data, size)) return true;
        asset.size = 0;
    }
    return read_at(services, tape_path(view), data, offset, size);
}

bool Screen::select_tape(TapeView view) {
    uint8_t header[tape_header_bytes];
    if (!raster || view == TapeView::none || !read_tape(view, header, 0, sizeof(header))) return false;
    const bool prepared = view == TapeView::reel && !std::memcmp(header, "TV03", 4);
    unsigned bits = 7;
    if (!prepared) {
        if (!std::memcmp(header, "TV02", 4)) bits = 6;
        else if (!std::memcmp(header, "TV01", 4)) bits = 5;
        else return false;
    }
    for (unsigned i = 36; i < sizeof(header); ++i) if (header[i] >= 16) return false;
    static_assert(sizeof(TapeArtBuffer::Bounds) == 4);
    const unsigned damage_bytes = prepared ? sizeof(tape_art->damage) : 0;
    if (!read_tape(view, raster, tape_header_bytes, damage_bytes + sizeof(tape_art->base))) return false;
    if (prepared) {
        for (unsigned i = 0; i < damage_bytes; i += 4)
            if (raster[i] > raster[i + 1] || raster[i + 1] > half_width / 2 ||
                raster[i + 2] > raster[i + 3] || raster[i + 3] > strip_height) return false;
        std::memcpy(tape_art->damage, raster, damage_bytes);
    }
    std::memcpy(tape_art->base, raster + damage_bytes, sizeof(tape_art->base));
    indexed_phase[0] = indexed_phase[1] = 255;
    for (unsigned i = 0; i < 16; ++i) palette[i] = header[4 + i * 2] | (header[5 + i * 2] << 8);
    std::memcpy(ring_color, header + 36, sizeof(ring_color));
    phase_bits = bits;
    tape = view;
    invalidate_tape();
    return true;
}

bool Screen::read_tape_chunk(unsigned band, int side) {
    const uint8_t* entry = tape_art->base[band];
    if (side >= 0) {
        const unsigned pose = phase(side);
        if (indexed_phase[side] != pose) {
            const unsigned bands = tape == TapeView::cassette ? 4 : reel_bands;
            const unsigned group = (side * (1u << phase_bits) + pose) * bands;
            const unsigned table = tape_header_bytes + (phase_bits == 7 ? sizeof(tape_art->damage) : 0);
            auto& entries = tape_art->sprites[side];
            if (!read_tape(tape, entries, table + (base_bands + group) * sizeof(entries[0]), bands * sizeof(entries[0])))
                return false;
            indexed_phase[side] = pose;
        }
        entry = tape_art->sprites[side][band];
    }
    const uint32_t offset = uint32_t(entry[0]) | uint32_t(entry[1]) << 8 | uint32_t(entry[2]) << 16 | uint32_t(entry[3]) << 24;
    const unsigned size = entry[4] | (entry[5] << 8);
    if (!size || size > tape_chunk_bytes || !read_tape(tape, raster, offset, size)) return false;
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
        const unsigned radius = root(core * core + fraction * (rim * rim - core * core) / 1024);
        if (spool_radius[side] != radius) winding_valid = reel_displayed = 0;
        spool_radius[side] = radius;
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

bool Screen::read_tape_band(unsigned y, unsigned layer, bool incremental) {
    const unsigned art_top = tape_top(), bands = tape == TapeView::cassette ? 4 : reel_bands;
    const bool spools = y >= art_top && y < art_top + bands * strip_height;
    if (!layer) {
        top = (int)y;
        tape_rect_count = tape_rect_next = 0;
        tape_rect_ready = false;
        const unsigned band = spools ? (y - art_top) / strip_height : 0;
        const uint32_t bit = 1u << band, offset = tape_shadow + (base_bands + band) * tape_band_bytes;
        reel_partial = incremental && phase_bits == 7 && spools && (reel_displayed & bit);
        if (reel_partial) {
            reel_sides = 0;
            for (unsigned side = 0; side < 2; ++side) {
                const auto& r = tape_art->damage[side][band];
                if (phase(side) == tape_art->displayed_phase[side][band] || r.left == r.right || r.first == r.end) continue;
                const unsigned left = side * (half_width / 2);
                tape_rects[tape_rect_count++] = {left + r.left, left + r.right, r.first, r.end};
                reel_sides |= 1u << side;
            }
            if (!reel_sides) return true;
            if (tape_rect_count == 2) {
                auto& left = tape_rects[0];
                const auto& right = tape_rects[1];
                if (left.right == right.left && left.first == right.first && left.end == right.end) {
                    left.right = right.right;
                    tape_rect_count = 1;
                }
            }
        }
        if (spools && (winding_valid & bit) && tape_buffer(MK61_BUFFER_READ, offset, strip, tape_band_bytes))
            return true;
        if (!read_tape_chunk(y / strip_height, -1)) return false;
        if (spools) {
            // The two windings occupy disjoint halves. Cache them with the
            // cabinet until a radius changes, then overlay the moving reels.
            paint_spool(0);
            paint_spool(1);
            if (tape_handle && tape_buffer(MK61_BUFFER_WRITE, offset, strip, tape_band_bytes))
                winding_valid |= bit;
        }
        return true;
    }
    if (!spools) return true;
    const unsigned side = layer - 1;
    if (reel_partial && !(reel_sides & (1u << side))) return true;
    return read_tape_chunk((y - art_top) / strip_height, side);
}

uint32_t Screen::present_tape(unsigned y) {
    if (!tape_handle) return present(y, strip_height);
    constexpr unsigned stride = screen_width / 2;
    const unsigned band = y / strip_height;
    const uint32_t bit = 1u << band, offset = tape_shadow + band * tape_band_bytes;
    if (!reel_partial && !tape_rect_count) {
        if ((tape_valid & bit) && tape_buffer(MK61_BUFFER_READ, offset, raster, tape_band_bytes)) {
            // Split the reel strip into two independent damage rectangles.
            // The stationary area between the reels can stay in GRAM.
            const unsigned part_width = tape == TapeView::reel && band < reel_bands ? stride / 2 : stride;
            for (unsigned start = 0; start < stride; start += part_width) {
                const unsigned end = start + part_width;
                TapeRect rect{end, start, strip_height, 0};
                for (unsigned row = 0; row < strip_height; ++row) {
                    const auto* old = raster + row * stride;
                    const auto* current = strip + row * stride;
                    if (!std::memcmp(old + start, current + start, part_width)) continue;
                    unsigned left = start, right = end;
                    while (old[left] == current[left]) ++left;
                    while (old[right - 1] == current[right - 1]) --right;
                    if (left < rect.left) rect.left = left;
                    if (right > rect.right) rect.right = right;
                    if (row < rect.first) rect.first = row;
                    rect.end = row + 1;
                }
                if (rect.end) tape_rects[tape_rect_count++] = rect;
            }
        } else {
            tape_rects[0] = {0, stride, 0, strip_height};
            tape_rect_count = 1;
        }
    }
    while (tape_rect_next < tape_rect_count) {
        const auto& rect = tape_rects[tape_rect_next];
        const unsigned width = rect.right - rect.left, height = rect.end - rect.first;
        const uint8_t* pixels = strip + rect.first * stride;
        if (width != stride) {
            if (!tape_rect_ready) {
                for (unsigned row = 0; row < height; ++row)
                    std::memcpy(raster + row * width, pixels + row * stride + rect.left, width);
                tape_rect_ready = true;
            }
            pixels = raster;
        }
        const uint32_t accepted = present_indexed(pixels, 2 * rect.left, y + rect.first, 2 * width, height);
        if (accepted != 1) return accepted;
        // A partial update no longer matches the saved complete strip.
        tape_valid &= ~bit;
        reel_displayed &= ~bit;
        ++tape_rect_next;
        tape_rect_ready = false;
    }
    if (!reel_partial && tape_rect_count && tape_buffer(MK61_BUFFER_WRITE, offset, strip, tape_band_bytes))
        tape_valid |= bit;
    if (phase_bits == 7 && band < reel_bands) {
        tape_art->displayed_phase[0][band] = phase(0);
        tape_art->displayed_phase[1][band] = phase(1);
        reel_displayed |= bit;
    }
    return 1;
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
