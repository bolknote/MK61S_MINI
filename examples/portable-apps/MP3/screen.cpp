#include "screen.hpp"
#include "mk8_literal.hpp"
#include <cstring>

namespace mp3 {
namespace {
constexpr uint16_t rgb(unsigned r, unsigned g, unsigned b) {
    return (uint16_t)((r >> 3) << 11 | (g >> 2) << 5 | (b >> 3));
}

constexpr unsigned record_stride = screen_width / 8;
constexpr unsigned record_attr_stride = record_stride * 2;
const int16_t sine[33] = {
    0, 13, 25, 38, 50, 62, 74, 86, 98, 109, 121, 132, 142, 152, 162, 172, 181,
    190, 198, 206, 213, 220, 226, 231, 237, 241, 245, 248, 251, 253, 255, 256, 256
};
int sin128(unsigned angle) {
    angle &= 127;
    const unsigned quarter = angle & 31;
    const int value = sine[angle & 32 ? 32 - quarter : quarter];
    return angle & 64 ? -value : value;
}

void clock_text(char (&text)[12], unsigned sec) {
    char reverse[8];
    unsigned at = 0, minutes = sec / 60;
    do {
        reverse[at++] = (char)('0' + minutes % 10);
        minutes /= 10;
    } while (minutes && at < sizeof(reverse));
    unsigned n = 0;
    while (at) text[n++] = reverse[--at];
    text[n++] = ':';
    text[n++] = (char)('0' + (sec % 60) / 10);
    text[n++] = (char)('0' + sec % 10);
    text[n] = 0;
}
}

void Screen::begin(const mk61_app_services* api, uint8_t* pixels, uint8_t* raster) {
    services = api;
    strip = pixels;
    this->raster = raster;
    record = raster;
    angle = 0;
    palette_ready = false;
    use_record();
    old_title[0] = old_artist[0] = 0;
    std::memset(title_mask, 0, sizeof(title_mask));
    uint8_t header[record_header_bytes];
    mk61_service_file_bytes request{"RECORD.LP", header, 0, sizeof(header)};
    if (!record || !services->call(MK61_SERVICE_FILE_BYTES, MK61_FILE_BYTES_READ, 0, sizeof(request), &request) ||
        std::memcmp(header, "LP04", 4)) {
        record = nullptr;
        return;
    }
    for (unsigned i = 0; i < 64; ++i) record_palette[i] = header[4 + i * 2] | (header[5 + i * 2] << 8);
}

void Screen::use_record() {
    tape = TapeView::none;
    invalidate_tape();
    const uint16_t colors[16] = {rgb(20,20,19), rgb(33,46,83), rgb(243,237,223), rgb(182,174,157),
        rgb(239,209,142), rgb(57,47,33), rgb(12,11,10), rgb(17,16,15), rgb(26,24,22), rgb(39,35,32),
        rgb(57,52,47), rgb(82,74,66), rgb(121,112,100), rgb(215,199,175), rgb(230,215,189), rgb(244,226,199)};
    std::memcpy(palette, colors, sizeof(colors));
}

uint32_t Screen::spi_hz() const {
    // An automatic (zero) request reports the actual clock, including the
    // resident's external-power detection and its recovery to the slow clock.
    uint32_t automatic = 0;
    return services->call(MK61_SERVICE_COLOR_DISPLAY, MK61_COLOR_SPI_HZ, 0, sizeof(automatic), &automatic);
}

bool Screen::use_record_palette() {
    if (palette_ready) return true;
    const unsigned result = services->call(MK61_SERVICE_COLOR_DISPLAY, MK61_COLOR_PALETTE64, 0,
                                            sizeof(record_palette), record_palette);
    palette_ready = result == 1;
    if (!result) record = nullptr;
    return palette_ready;
}

bool Screen::read_record(unsigned y, unsigned page) {
    const unsigned offset = page * record_page_bytes;
    if (offset >= record_frame_bytes) return false;
    const unsigned remaining = record_frame_bytes - offset;
    const unsigned size = remaining < record_page_bytes ? remaining : record_page_bytes;
    const unsigned strip_id = angle * (record_height / record_strip_height) + y / record_strip_height;
    mk61_service_file_bytes request{"RECORD.LP", record + offset,
                                    record_header_bytes + strip_id * record_frame_bytes + offset, size};
    return services->call(MK61_SERVICE_FILE_BYTES, MK61_FILE_BYTES_READ, 0, sizeof(request), &request);
}

uint32_t Screen::present_record(unsigned y, unsigned height) {
    mk61_service_color_frame frame{};
    frame.pixels = record;
    frame.tiles = record + record_bitmap_bytes;
    frame.pixel_bytes = height * record_stride;
    frame.tile_bytes = (height / 8) * record_attr_stride;
    frame.y = (uint16_t)y;
    frame.width = screen_width;
    frame.height = (uint16_t)height;
    frame.background = palette[background];
    frame.format = MK61_COLOR_TILE8 | MK61_COLOR_PRESERVE_OUTSIDE;
    return services->call(MK61_SERVICE_COLOR_DISPLAY, MK61_COLOR_PRESENT, 0, sizeof(frame), &frame);
}

void Screen::clear(unsigned y) {
    top = (int)y;
    std::memset(strip, 0, screen_width * strip_height / 2);
}

uint32_t Screen::present(unsigned y, unsigned height) {
    return present_indexed(strip, 0, y, screen_width, height);
}

uint32_t Screen::present_indexed(const uint8_t* pixels, unsigned x, unsigned y, unsigned width, unsigned height) {
    mk61_service_color_frame frame{};
    frame.pixels = pixels;
    frame.pixel_bytes = height * (width / 2);
    std::memcpy(frame.palette, palette, sizeof(palette));
    frame.x = (uint16_t)x;
    frame.y = (uint16_t)y;
    frame.width = (uint16_t)width;
    frame.height = (uint16_t)height;
    frame.background = palette[background];
    frame.format = MK61_COLOR_INDEX4 | MK61_COLOR_PRESERVE_OUTSIDE;
    return services->call(MK61_SERVICE_COLOR_DISPLAY, MK61_COLOR_PRESENT, 0, sizeof(frame), &frame);
}

void Screen::pixel(int x, int y, unsigned color) {
    if ((unsigned)x >= screen_width || (unsigned)(y - top) >= strip_height) return;
    uint8_t& pair = strip[(y - top) * (screen_width / 2) + x / 2];
    if (x & 1) pair = (pair & 0xF0) | color;
    else pair = (pair & 15) | (color << 4);
}

void Screen::rect(int x, int y, unsigned width, unsigned height, unsigned color) {
    const int start = y > top ? y : top;
    const int end = y + (int)height < top + (int)strip_height ? y + (int)height : top + (int)strip_height;
    for (int row = start; row < end; ++row)
        for (unsigned col = 0; col < width; ++col) pixel(x + (int)col, row, color);
}

void Screen::text(int x, int y, const char* words, unsigned color, unsigned max_width, bool center, unsigned scale) {
    if (y + (int)(8 * scale) <= top || y >= top + (int)strip_height) return;
    const unsigned length = (unsigned)std::strlen(words);
    const unsigned columns = max_width / (6 * scale);
    const unsigned count = length < columns ? length : columns;
    if (center) x -= (int)(count * 3 * scale);
    for (unsigned i = 0; i < count; ++i) {
        mk61_service_glyph glyph{};
        if (length > count && i + 1 == count) {
            for (unsigned dot = 0; dot < 5; dot += 2)
                rect(x + (int)(dot * scale), y + (int)(6 * scale), scale, scale, color);
        } else {
            const uint32_t cp = mk8::codepoint((uint8_t)words[i]);
            if (services->call(MK61_SERVICE_FONT, 0, cp, sizeof(glyph), &glyph) ||
                services->call(MK61_SERVICE_FONT, 0, '?', sizeof(glyph), &glyph)) {
                for (unsigned row = 0; row < glyph.height && row < 8; ++row)
                    for (unsigned col = 0; col < glyph.width && col < 5; ++col)
                        if (glyph.pixels[row] & (0x80 >> col)) {
                            if (scale == 1) pixel(x + (int)col, y + (int)row, color);
                            else rect(x + (int)(col * scale), y + (int)(row * scale), scale, scale, color);
                        }
            }
        }
        x += (int)(6 * scale);
    }
}

void Screen::label(const char* title, const char* artist) {
    if (!std::strcmp(title, old_title) && !std::strcmp(artist, old_artist)) return;
    std::memcpy(old_title, title, std::strlen(title) + 1);
    std::memcpy(old_artist, artist, std::strlen(artist) + 1);
    // Store only the two lines of ink. They are sampled in record-local
    // coordinates by the same transform as the grooves and spindle.
    std::memset(title_mask, 0, sizeof(title_mask));
    const char* lines[] = {artist, title};
    for (unsigned line_id = 0; line_id < 2; ++line_id) {
        const auto* words = lines[line_id];
        unsigned used = 0;
        uint8_t columns[label_width]{};
        bool truncated = false;
        while (*words) {
            mk61_service_glyph g{};
            uint32_t cp = mk8::codepoint((uint8_t)*words++);
            if (cp >= 0x430 && cp <= 0x44F) cp -= 32;
            else if (cp == 0x451) cp = 0x401;
            else if (cp >= 'a' && cp <= 'z') cp -= 32;
            if (!services->call(MK61_SERVICE_FONT, 0, cp, sizeof(g), &g) &&
                !services->call(MK61_SERVICE_FONT, 0, '?', sizeof(g), &g)) continue;
            unsigned first = 5, end = 0;
            for (unsigned col = 0; col < 5; ++col)
                for (unsigned row = 0; row < 8; ++row)
                    if (g.pixels[row] & (0x80 >> col)) {
                        if (col < first) first = col;
                        if (col + 1 > end) end = col + 1;
                    }
            const unsigned width = first == 5 ? 2 : end - first + 1;
            if (used + width > label_width) {
                truncated = true;
                break;
            }
            if (first == 5) { used += width; continue; }
            for (unsigned col = first; col < end; ++col) {
                uint8_t vertical = 0;
                for (unsigned row = 0; row < 8; ++row)
                    if (g.pixels[row] & (0x80 >> col)) vertical |= 1u << row;
                columns[used++] = vertical;
            }
            ++used;
        }
        if (truncated) {
            if (used > label_width - 6) used = label_width - 6;
            while (used && columns[used - 1]) --used;
            std::memset(columns + used, 0, 6);
            columns[used + 1] = columns[used + 3] = columns[used + 5] = 0x40;
            used += 6;
        } else if (used) --used;
        const unsigned left = (label_width - used) / 2;
        for (unsigned col = 0; col < used; ++col)
            for (unsigned row = 0; row < 8; ++row)
                if (columns[col] & (1u << row)) {
                    const unsigned x = left + col;
                    title_mask[line_id][row][x >> 3] |= (uint8_t)(1u << (x & 7));
                }
    }
}

void Screen::record_ink(unsigned x, unsigned y) {
    y &= record_strip_height - 1;
    uint8_t* attrs = record + record_bitmap_bytes + (y / 8) * record_attr_stride + (x / 8) * 2;
    if (attrs[1] != ink) {
        // Labels are well inside the paper. Keep its lighter shade and use
        // the tile's second color for the printed ink.
        attrs[0] = attrs[1];
        attrs[1] = ink;
        for (unsigned row = y & ~7u; row < (y & ~7u) + 8; ++row)
            record[row * record_stride + x / 8] = 0;
    }
    record[y * record_stride + x / 8] |= 0x80 >> (x & 7);
}

void Screen::paint_label(unsigned y0, const char* title, const char* artist) {
    label(title, artist);
    const int cosine = sin128(angle + 32), sine = sin128(angle);
    // Visit only the tiles inside the rotating label's bounding box.
    // Inverse-map the type and the printed mark in the same coordinates
    // as the prepared record, avoiding a second resample of the photograph.
    const unsigned reach_x = (80 * (unsigned)(cosine < 0 ? -cosine : cosine) +
                              64 * (unsigned)(sine < 0 ? -sine : sine) + 255) >> 8;
    const unsigned reach_y = (80 * (unsigned)(sine < 0 ? -sine : sine) +
                              64 * (unsigned)(cosine < 0 ? -cosine : cosine) + 255) >> 8;
    const unsigned first = y0 > 128 - reach_y ? y0 : 128 - reach_y;
    const unsigned last = y0 + record_strip_height < 128 + reach_y ? y0 + record_strip_height : 128 + reach_y;
    for (unsigned y = first; y < last; ++y) {
        const int dy = (int)y - 128;
        int u = -(int)reach_x * cosine + dy * sine;
        int v = (int)reach_x * sine + dy * cosine;
        for (unsigned x = 160 - reach_x; x < 160 + reach_x; ++x) {
            const bool title_line = v >= 0;
            const int row = title_line ? (v >> 8) - 22 : ((v + 36 * 256) >> 8);
            if ((unsigned)row < 8) {
                const int column = (title_line ? (u * 3 >> 10) : (u * 7 >> 11)) + (int)label_width / 2;
                if ((unsigned)column < label_width &&
                    (title_mask[title_line][row][column >> 3] & (1u << (column & 7)))) record_ink(x, y);
            } else {
                const int mark_x = u >> 8, mark_y = (v >> 8) + 61;
                if ((unsigned)(mark_x + 19) <= 38 && (mark_y == 0 ||
                    ((unsigned)(mark_x + 2) < 4 && (mark_y == -1 || mark_y == 1)))) record_ink(x, y);
            }
            u += cosine;
            v -= sine;
        }
    }
}

void Screen::paint_deck(unsigned y, unsigned position, unsigned duration, unsigned volume,
                        bool playing, bool shuffle, unsigned repeat, const char* status) {
    clear(y);
    if (y == 256) {
        char elapsed[12], total[12];
        clock_text(elapsed, position);
        clock_text(total, duration);
        text(12, 261, elapsed, muted, 52);
        text(308 - (int)std::strlen(total) * 6, 261, total, muted, 52);
        rect(65, 264, 190, 2, 11);
        if (duration) rect(65, 264, position >= duration ? 190 : 190 * position / duration, 2, accent);
        return;
    }
    if (y == 272) {
        text(12, 277, status ? status : M8("←→ Перемотка 5 с"), light, status ? 168 : 116);
        if (!status) {
            char level[8];
            mk61_app_snprintf(services, level, sizeof(level), "%u%%", volume);
            text(129, 277, M8("↑↓"), light, 20);
            text(145, 277, level, muted, 30);
        }
        text(188, 277, playing ? M8("Пробел Пауза") : M8("Пробел Играть"), light, 115);
        return;
    }
    transport_keys(shuffle, repeat, false);
}

void Screen::transport_keys(bool shuffle, unsigned repeat, bool view_key) {
    if (!view_key) rect(12, 289, 296, 1, 11);
    constexpr int centers[] = {39, 102, 169, 227, 283};
    const char* keys[] = {"F1", "F2", "F3", "F4", "F5", "V"};
    const char* labels[] = {M8("Файлы"), M8("Случайно"), repeat == 2 ? M8("Повтор 1") : repeat ? M8("Список") : M8("Повтор"),
                            M8("Пред."), M8("След."), M8("Вид")};
    for (unsigned i = 0; i < (view_key ? 6U : 5U); ++i) {
        const int x = view_key ? 26 + (int)i * 53 : centers[i];
        const unsigned color = ((i == 1 && shuffle) || (i == 2 && repeat)) ? accent : muted;
        text(x, 294, keys[i], color == accent ? accent : light, 24, true);
        text(x, 306, labels[i], color, 54, true);
    }
}

void Screen::tape_status(unsigned position, unsigned duration, unsigned volume, bool playing,
                         const char* status) {
    const bool cassette = tape == TapeView::cassette;
    const bool timer_visible = cassette ? top == 224 : top == 192 || top == 208;
    if (timer_visible) {
        char elapsed[12], total[12];
        clock_text(elapsed, position);
        clock_text(total, duration);
        if (cassette) {
            text(13, 232, elapsed, light, 45);
            text(307 - (int)std::strlen(total) * 6, 232, total, muted, 45);
        } else {
            text(116, 201, elapsed, accent, 60, false, 2);
            text(205 - (int)std::strlen(total) * 6, 210, total, muted, 30);
        }
        const unsigned width = cassette ? 202 : 96;
        const unsigned left = cassette ? 59 : 112, y = cassette ? 234 : 223;
        rect(left, y, width, 2, 7);
        if (duration) rect(left, y, position >= duration ? width : (uint64_t(width) * position) / duration, 2, accent);
    }
    if (top < 240) return;
    const unsigned status_y = cassette ? 256 : 262;
    if (status) text(13, status_y, status, light, 206);
    else {
        text(cassette ? 13 : 266, cassette ? 256 : 243, M8("←→ 5 с"), muted, 50);
        char level[14];
        mk61_app_snprintf(services, level, sizeof(level), M8("↑↓ %u%%"), volume);
        text(158, status_y, level, muted, 70, cassette);
    }
    const char* action = playing ? M8("Пробел Пауза") : M8("Пробел Играть");
    text(307 - (int)std::strlen(action) * 6, status_y, action, light, 115);
}

void Screen::files_header(unsigned y, const char* directory) {
    clear(y);
    text(14, 15, M8("Файлы"), light, 70);
    text(14, 38, directory, muted, 290);
    rect(14, 54, 292, 1, 11);
}
void Screen::file_row(unsigned strip_y, const char* name, bool folder, bool active, bool current) {
    const int y = (int)(strip_y & ~31u);
    clear(strip_y);
    if (!name) return;
    if (active) {
        rect(14, y, 292, 30, selected);
        rect(14, y, 2, 30, accent);
    }
    text(22, y + 11, folder ? "/" : current ? ">" : "-", current || active ? accent : muted, 6);
    text(39, y + 11, name, active ? accent : light, 257);
    rect(14, y + 31, 292, 1, 10);
}
void Screen::files_footer(unsigned y, const char* status) {
    clear(y);
    if (status) text(14, 289, status, accent, 292);

    text(14, 299, M8("↑↓ Выбрать"), muted, 94);
    text(126, 299, M8("Enter Открыть"), light, 104);
    text(244, 299, M8("Esc Назад"), light, 62);
}
}
