#ifndef MK61_MP3_SCREEN_HPP
#define MK61_MP3_SCREEN_HPP

#include "mk61_app.h"

namespace mp3 {
constexpr unsigned screen_width = 320, strip_height = 16;
constexpr unsigned record_height = 256, rotation_frames = 128;
constexpr unsigned record_strip_height = 32;
constexpr unsigned record_bitmap_bytes = screen_width * record_strip_height / 8;
constexpr unsigned record_tile_bytes = record_bitmap_bytes / 4;
constexpr unsigned record_frame_bytes = record_bitmap_bytes + record_tile_bytes;
constexpr unsigned record_page_bytes = 512;
constexpr unsigned record_pages = (record_frame_bytes + record_page_bytes - 1) / record_page_bytes;
constexpr unsigned record_header_bytes = 4 + 64 * 2;
constexpr unsigned tape_band_bytes = screen_width * strip_height / 2;
constexpr unsigned tape_chunk_bytes = tape_band_bytes + 20;
enum class TapeView { none, cassette, reel };

struct Screen {
    const mk61_app_services* services;
    uint8_t* strip;
    uint8_t* record;
    uint32_t angle;

    enum Color { background = 0, ink = 1, light = 2, muted = 3, accent = 4, selected = 5 };
    uint16_t palette[16];

    void blank(unsigned y) { clear(y); }
    void begin(const mk61_app_services* api, uint8_t* pixels, uint8_t* raster);
    uint32_t spi_hz() const;
    bool read_record(unsigned y, unsigned page);
    bool use_record_palette();
    void paint_label(unsigned y, const char* title, const char* artist);
    uint32_t present_record(unsigned y, unsigned height);
    uint32_t present(unsigned y, unsigned height);
    void paint_deck(unsigned y, unsigned position, unsigned duration, unsigned volume,
                    bool playing, bool shuffle, unsigned repeat, const char* status);
    void files_header(unsigned y, const char* directory);
    void file_row(unsigned y, const char* name, bool folder, bool active, bool current);
    void files_footer(unsigned y, const char* status);
    TapeView tape_view() const { return tape; }
    void use_record();
    void cache_tapes();
    void release_tapes();
    bool select_tape(TapeView view);
    void invalidate_tape() { tape_valid = winding_valid = 0; }
    unsigned tape_top() const { return tape == TapeView::cassette ? 80 : 0; }
    unsigned tape_end() const { return tape == TapeView::cassette ? 144 : 240; }
    void tape_pose(unsigned position, unsigned duration, uint32_t played_ms, uint32_t levels);
    bool read_tape_band(unsigned y, unsigned layer);
    uint32_t present_tape(unsigned y);
    void paint_tape(unsigned y, const char* title, const char* artist, unsigned position,
                    unsigned duration, unsigned volume, bool playing, bool shuffle,
                    unsigned repeat, const char* status);

private:
    uint8_t* raster;
    TapeView tape;
    struct CachedTape { uint32_t offset, size; } cached[2]{};
    uint32_t tape_handle = 0, tape_shadow = 0, tape_valid = 0, winding_valid = 0;
    struct TapeRect { unsigned left, right, first, end; };
    TapeRect tape_rects[2];
    unsigned tape_rect_count = 0, tape_rect_next = 0;
    bool tape_rect_ready = false;
    unsigned phase_bits = 0;
    uint8_t ring_color[16];
    uint32_t tape_time, spool_phase[2];
    unsigned spool_radius[2], needle[2];
    int top;
    static constexpr unsigned label_width = 112;
    uint8_t title_mask[2][8][label_width / 8];
    char old_title[96], old_artist[96];
    uint16_t record_palette[64];
    bool palette_ready;
    void clear(unsigned y);
    void rect(int x, int y, unsigned width, unsigned height, unsigned color);
    void pixel(int x, int y, unsigned color);
    void text(int x, int y, const char* text, unsigned color, unsigned max_width, bool center = false,
              unsigned scale = 1);
    void transport_keys(bool shuffle, unsigned repeat, bool view_key);
    void tape_status(unsigned position, unsigned duration, unsigned volume, bool playing, const char* status);
    bool tape_buffer(unsigned operation, unsigned offset, void* data, unsigned size);
    bool read_tape(TapeView view, void* data, unsigned offset, unsigned size);
    bool read_tape_chunk(unsigned id, int side);
    uint32_t present_indexed(const uint8_t* pixels, unsigned x, unsigned y, unsigned width, unsigned height);
    void paint_spool(unsigned side);
    void line(int x0, int y0, int x1, int y1, unsigned color, unsigned width = 1);
    void label(const char* title, const char* artist);
    void record_ink(unsigned x, unsigned y);
};
}
#endif
