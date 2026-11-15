#include <array>
#include <cassert>
#include <cstdio>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>
#include "lcd_color.hpp"

#define main mp3_app_entry
#include "../examples/portable-apps/MP3/main.cpp"
#undef main

const mk61_app_api* mk61_api;

namespace {
std::array<uint8_t, 32> keyboard{};
std::array<std::vector<uint8_t>, 2> assets;
std::array<uint16_t, 320 * 320> pixels;
std::vector<uint8_t> psram;
unsigned sd_reads = 0, lcd_pixels = 0;

uint32_t call(uint32_t operation, uint32_t a, uint32_t b, uint32_t, void* data) {
    if (operation == MK61_SERVICE_KEYBOARD) {
        assert(a == MK61_SERVICE_KEY_BITMAP && b == keyboard.size());
        std::memcpy(data, keyboard.data(), keyboard.size());
        return 1;
    }
    if (operation == MK61_SERVICE_FILE_BYTES) {
        const auto& request = *static_cast<mk61_service_file_bytes*>(data);
        const bool cassette = !std::strcmp(request.path, "CASSETTE.TV");
        if (!cassette && std::strcmp(request.path, "REEL.TV")) return 0;
        const auto& asset = assets[!cassette];
        if (a == MK61_FILE_BYTES_STAT) {
            auto& info = *static_cast<mk61_service_file_info*>(request.data);
            info = {};
            info.size = asset.size();
            return 1;
        }
        assert(a == MK61_FILE_BYTES_READ);
        if (request.offset > asset.size() || request.size > asset.size() - request.offset) return 0;
        ++sd_reads;
        std::memcpy(request.data, asset.data() + request.offset, request.size);
        return 1;
    }
    if (operation == MK61_SERVICE_CAPABILITIES) return MK61_SERVICE_CAP_BUFFERS;
    if (operation == MK61_SERVICE_BUFFER) {
        auto& buffer = *static_cast<mk61_service_buffer*>(data);
        if (a == MK61_BUFFER_ACQUIRE) {
            assert(buffer.access == MK61_BUFFER_EXTERNAL && psram.empty());
            psram.resize(buffer.size);
            buffer.handle = 1;
            buffer.storage = MK61_BUFFER_PSRAM;
            return 1;
        }
        assert(buffer.handle == 1 && !psram.empty());
        if (a == MK61_BUFFER_RELEASE) {
            psram.clear();
            return 1;
        }
        assert(buffer.offset <= psram.size() && buffer.size <= psram.size() - buffer.offset);
        auto* address = psram.data() + buffer.offset;
        if (a == MK61_BUFFER_READ) std::memcpy(buffer.data, address, buffer.size);
        else {
            assert(a == MK61_BUFFER_WRITE);
            std::memcpy(address, buffer.data, buffer.size);
        }
        return 1;
    }
    if (operation == MK61_SERVICE_COLOR_DISPLAY && a == MK61_COLOR_PRESENT) {
        const auto& frame = *static_cast<mk61_service_color_frame*>(data);
        using namespace picocalc::lcd;
        assert(valid_color(frame));
        assert(frame.height <= mp3::strip_height && (frame.format & MK61_COLOR_PRESERVE_OUTSIDE));
        const Rect area{frame.x, frame.y, frame.width, frame.height};
        for (unsigned row = 0; row < frame.height; ++row)
            color_scanline(frame, area, row, pixels.data() + (frame.y + row) * mp3::screen_width + frame.x);
        lcd_pixels += frame.width * frame.height;
        return 1;
    }
    return 0;
}

void press(mp3::Player& player, unsigned key) {
    keyboard[key / 8] = 1u << (key & 7);
    player.keyboard();
    keyboard[key / 8] = 0;
    player.keyboard();
}

const auto& render(mp3::Screen& screen, unsigned position, unsigned time, bool playing, bool full = false) {
    constexpr unsigned duration = 160;
    screen.tape_pose(position, duration, time, playing ? 0xfb0007a0 : 0);
    for (unsigned y = 0; y < 320; y += mp3::strip_height) {
        for (unsigned layer = 0; layer < 3; ++layer) assert(screen.read_tape_band(y, layer));
        screen.paint_tape(y, "Title", "Artist", position, duration, 100, playing, false, 0, nullptr);
        assert((full ? screen.present(y, mp3::strip_height) : screen.present_tape(y)) == 1);
    }
    return pixels;
}
}

int main(int argc, char** argv) {
    assert(argc == 3);
    for (unsigned i = 0; i < assets.size(); ++i) {
        std::ifstream stream(argv[i + 1], std::ios::binary);
        assets[i].assign(std::istreambuf_iterator<char>(stream), {});
        assert(!assets[i].empty());
    }
    mk61_app_services services{};
    services.call = call;
    services.format = [](char* out, uint32_t count, const char* fmt, va_list args) {
        return std::vsnprintf(out, count, fmt, args);
    };
    mp3::Workspace work{};
    mp3::Player player{};
    player.services = &services;
    player.work = &work;
    player.have_track = player.playing = true;
    player.seek_seconds = 26;
    player.current = 1;
    work.queue.reset();
    work.queue.volume(100);
    work.queue.play();
    assert(work.queue.push(0x1234fedcu));
    uint8_t raster[mp3::tape_chunk_bytes]{};
    mk61_app_api api{};
    api.service = [] {};
    mk61_api = &api;
    player.screen.begin(&services, work.strip, raster);
    player.screen.cache_tapes();
    assert(sd_reads && !psram.empty());
    sd_reads = 0;
    using mp3::TapeView;
    assert(player.screen.select_tape(TapeView::cassette));
    const auto cassette = render(player.screen, 26, 0, true);
    assert(render(player.screen, 26, 550, true) != cassette);
    press(player, 'v');
    assert(player.screen.tape_view() == TapeView::reel);
    assert(player.seek_seconds == 26 && player.current == 1 && player.playing && !player.paused);
    assert(work.queue.queued() == 1);
    const auto reel = render(player.screen, 26, 550, true);
    lcd_pixels = 0;
    const auto rotated = render(player.screen, 26, 650, true);
    assert(rotated != reel && lcd_pixels && lcd_pixels < 320 * 192);
    const unsigned reel_pixels = lcd_pixels;
    lcd_pixels = 0;
    assert(render(player.screen, 26, 650, true) == rotated && lcd_pixels == 0);
    assert(render(player.screen, 26, 650, true, true) == rotated);
    assert(reel != cassette && render(player.screen, 154, 650, true) != reel);
    press(player, 'V');
    assert(player.screen.tape_view() == TapeView::cassette && player.playing);
    assert(mp3::StereoQueue::consume(&work.queue) == 0x1234fedcu);
    assert(work.queue.push(0x1234fedcu));
    press(player, ' ');
    assert(player.paused && !player.playing);
    for (unsigned i = 0; i < 2; ++i) {
        press(player, 'v');
        assert(player.screen.tape_view() == (i ? TapeView::cassette : TapeView::reel));
        assert(player.paused && !player.playing && player.played_seconds() == 26 && player.current == 1);
        const auto paused = render(player.screen, 26, 650, false);
        assert(render(player.screen, 26, 650, false) == paused);
        assert(mp3::StereoQueue::consume(&work.queue) == 0 && work.queue.queued() == 1);
    }
    press(player, ' ');
    assert(!player.paused && work.queue.queued() == 1);
    assert(sd_reads == 0);
    const auto cached_frame = render(player.screen, 26, 650, false);
    player.screen.release_tapes();
    assert(psram.empty());
    assert(render(player.screen, 26, 650, false) == cached_frame && sd_reads > 0);
    std::printf("MP3 tape views: rotation, winding, pause, V, identical cached/SD raster. "
                "Reel step submitted %u pixels; zero SD reads with warm PSRAM.\n", reel_pixels);
}
