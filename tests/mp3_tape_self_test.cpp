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

uint32_t call(uint32_t operation, uint32_t a, uint32_t b, uint32_t, void* data) {
    if (operation == MK61_SERVICE_KEYBOARD) {
        assert(a == MK61_SERVICE_KEY_BITMAP && b == keyboard.size());
        std::memcpy(data, keyboard.data(), keyboard.size());
        return 1;
    }
    if (operation == MK61_SERVICE_FILE_BYTES && a == MK61_FILE_BYTES_READ) {
        const auto& request = *static_cast<mk61_service_file_bytes*>(data);
        const bool cassette = !std::strcmp(request.path, "CASSETTE.TV");
        if (!cassette && std::strcmp(request.path, "REEL.TV")) return 0;
        const auto& asset = assets[!cassette];
        if (request.offset > asset.size() || request.size > asset.size() - request.offset) return 0;
        std::memcpy(request.data, asset.data() + request.offset, request.size);
        return 1;
    }
    if (operation == MK61_SERVICE_COLOR_DISPLAY && a == MK61_COLOR_PRESENT) {
        const auto& frame = *static_cast<mk61_service_color_frame*>(data);
        using namespace picocalc::lcd;
        assert(valid_color(frame));
        assert(frame.x == 0 && frame.width == 320 && frame.height == mp3::strip_height);
        const Rect area{frame.x, frame.y, frame.width, frame.height};
        for (unsigned row = 0; row < frame.height; ++row)
            color_scanline(frame, area, row, pixels.data() + (frame.y + row) * frame.width);
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

const auto& render(mp3::Screen& screen, unsigned position, unsigned time, bool playing) {
    constexpr unsigned duration = 160;
    screen.tape_pose(position, duration, time, playing ? 0xfb0007a0 : 0);
    for (unsigned y = 0; y < 320; y += mp3::strip_height) {
        for (unsigned layer = 0; layer < 3; ++layer) assert(screen.read_tape_band(y, layer));
        screen.paint_tape(y, "Title", "Artist", position, duration, 100, playing, false, 0, nullptr);
        assert(screen.present(y, mp3::strip_height) == 1);
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
    player.screen.begin(&services, work.strip, raster);
    using mp3::TapeView;
    assert(player.screen.select_tape(TapeView::cassette));
    const auto cassette = render(player.screen, 26, 0, true);
    assert(render(player.screen, 26, 550, true) != cassette);
    press(player, 'v');
    assert(player.screen.tape_view() == TapeView::reel);
    assert(player.seek_seconds == 26 && player.current == 1 && player.playing && !player.paused);
    assert(work.queue.queued() == 1);
    const auto reel = render(player.screen, 26, 550, true);
    assert(reel != cassette && render(player.screen, 154, 550, true) != reel);
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
        const auto paused = render(player.screen, 26, 550, false);
        assert(render(player.screen, 26, 550, false) == paused);
        assert(mp3::StereoQueue::consume(&work.queue) == 0 && work.queue.queued() == 1);
    }
    press(player, ' ');
    assert(!player.paused && work.queue.queued() == 1);
    std::puts("MP3 cassette/reel: INDEX4 frames, winding, V during playback/pause, Space and stereo queue passed.");
}
