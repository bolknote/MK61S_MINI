#include "audio.hpp"
#include "screen.hpp"
#include "mk8_literal.hpp"
#include <cstring>
#include <new>

namespace mp3 {
namespace {
constexpr unsigned path_bytes = 384, max_entries = 1024, rows_per_screen = 7;
constexpr unsigned no_index = max_entries, folder = 0x8000, entry_index = folder - 1;
constexpr unsigned fast_lcd_hz = 24000000, turn_ms = 8000;
enum { function1 = MK61_APP_KEY_RAW_BASE + 0x81, function2, function3, function4, function5,
       space_key = MK61_APP_KEY_RAW_BASE + ' ' };

struct Workspace {
    Decoder decoder;
    StereoQueue queue;
    Resampler resampler;
    Loudness loudness;
    uint16_t entries[max_entries], playlist[max_entries];
    uint8_t strip[screen_width * strip_height / 2];
};

struct Player {
    const mk61_app_services* services;
    Workspace* work;
    Screen screen;
    Tags metadata;
    Timing duration;
    char directory[path_bytes], path[path_bytes], play_directory[path_bytes];
    const char* read_path = nullptr;
    const char* message = nullptr;
    unsigned count = 0, selected = 0, first_visible = 0;
    unsigned tracks = 0, current = no_index, repeat = 0;
    mk61_service_file_info visible_entry;
    bool visible_entry_ok = false;
    unsigned volume = 100, draw_y = screen_width, draw_end = screen_width, deck_second = UINT32_MAX;
    unsigned read_page = 0, lcd_hz = 0, power_check = 0, next_frame = 0;
    unsigned record_frames = 0, animation_started = 0, animation_ms = 0;
    unsigned angle_phase = 0, angle_at = 0;
    uint32_t seek_seconds = 0, enqueued = 0;
    bool strip_ready = false, scan_limit = false, shuffle = false, browsing = false, have_track = false,
         paused = false, output = false, playing = false, running = true, display_failed = false;
    bool deck_dirty = true, clock_running = false, have_animation_frames = false;
    bool tape_pose_pending = false;
    uint8_t key_state[32]{};

    bool call_file(unsigned operation, const char* name, uint32_t offset, void* data, unsigned size) {
        mk61_service_file_bytes request{name, data, offset, size};
        return services->call(MK61_SERVICE_FILE_BYTES, operation, 0, sizeof(request), &request);
    }
    static bool read(void* context, uint32_t offset, void* data, unsigned size) {
        auto& self = *static_cast<Player*>(context);
        return self.call_file(MK61_FILE_BYTES_READ, self.read_path, offset, data, size);
    }
    void parent() {
        const unsigned length = (unsigned)std::strlen(directory);
        for (unsigned i = length; i > 1; --i) {
            if (directory[i - 1] != '/') continue;
            directory[i - 1] = 0;
            return;
        }
        directory[1] = 0;
    }
    static bool join(const char* directory, const char* name, char* dest) {
        const unsigned size = (unsigned)std::strlen(directory);
        const unsigned length = (unsigned)std::strlen(name);
        const unsigned separator = size > 1 ? 1 : 0;
        if (size + separator + length >= path_bytes) return false;
        std::memcpy(dest, directory, size);
        if (separator) dest[size] = '/';
        std::memcpy(dest + size + separator, name, length + 1);
        return true;
    }
    bool child(const char* dir, unsigned raw, mk61_service_file_info& info) {
        return call_file(MK61_FILE_BYTES_CHILD, dir, raw, &info, sizeof(info));
    }
    bool entry(unsigned index, mk61_service_file_info& info) {
        return index < count && child(directory, work->entries[index] & entry_index, info);
    }
    unsigned playing_entry() const {
        if (current >= tracks || std::strcmp(play_directory, directory)) return no_index;
        return work->playlist[current];
    }
    void scan() {
        count = selected = first_visible = 0;
        scan_limit = false;
        message = nullptr;
        mk61_service_file_info info;
        const unsigned playing = playing_entry();
        for (unsigned raw = 0; raw < max_entries; ++raw) {
            pump_audio();
            // FAT enumeration shares the SD bus with the stream.
            fill_audio();
            if (!child(directory, raw, info)) break;
            if (info.directory || ends_in_mp3(info.name)) {
                if (raw == playing) selected = count;
                work->entries[count++] = (uint16_t)(raw | (info.directory ? folder : 0));
            }
            scan_limit = raw + 1 == max_entries;
        }
        keep_visible();
    }
    void keep_visible() {
        if (selected < first_visible) first_visible = selected;
        else if (selected >= first_visible + rows_per_screen) first_visible = selected - rows_per_screen + 1;
    }
    bool audio_call(unsigned operation, void* payload = nullptr, unsigned size = 0) {
        return services->call(MK61_SERVICE_AUDIO_STREAM, operation, 0, size, payload);
    }
    void close_audio() {
        if (output) audio_call(MK61_AUDIO_CLOSE);
        output = false;
    }
    void mute() {
        work->queue.mute();
        playing = false;
    }
    void pump_audio() { mk61_api->service(); }
    bool open_audio() {
        mk61_service_audio_synth request{StereoQueue::consume, &work->queue, output_rate, 100};
        if (!audio_call(MK61_AUDIO_SYNTH_OPEN, &request, sizeof(request))) {
            message = M8("Аудиовыход недоступен");
            paused = true;
            refresh_deck();
            return false;
        }
        output = true;
        return true;
    }
    void fill_audio() {
        if (!have_track || paused || !work->queue.ready()) return;
        unsigned queued = work->queue.queued();
        if (queued < StereoQueue::capacity - 128 && !work->decoder.eof) {
            if (work->decoder.step()) {
                auto& decoder = work->decoder;
                auto& resampler = work->resampler;
                const unsigned rate = decoder.synth.pcm.samplerate;
                if (resampler.rate != rate) resampler.reset();
                for (; decoder.pcm_at < decoder.synth.pcm.length; ++decoder.pcm_at) {
                    const uint32_t pcm = decoder.source_sample();
                    uint32_t frame;
                    while (resampler.output(pcm, frame)) {
                        // The producer is the only writer; this snapshot
                        // gives a lower bound on the number of free slots.
                        if (queued < StereoQueue::capacity) {
                            work->queue.push(work->loudness.process(frame));
                            ++enqueued;
                            ++queued;
                        } else {
                            // output() advanced one interpolation step. Keep
                            // that sample for the next call without decoding.
                            resampler.phase -= rate;
                            return;
                        }
                    }
                    resampler.advance(pcm, rate);
                }
            }
        }
        if (work->decoder.eof) work->queue.finish();
        if (!playing && (queued >= StereoQueue::capacity * 3 / 4 || (queued && work->decoder.eof)) &&
            (output || open_audio())) {
            work->queue.play();
            playing = true;
        }
    }
    unsigned played_seconds() const {
        const unsigned queued = work->queue.ready() ? work->queue.queued() : 0;
        return seek_seconds + (enqueued > queued ? enqueued - queued : 0) / output_rate;
    }
    void reset_decoder(unsigned at) {
        playing = false;
        seek_seconds = at;
        enqueued = 0;
        if (output) work->queue.discard();
        else work->queue.reset();
        work->resampler.reset();
        work->loudness = {};
        const File file{this, read, duration.end};
        work->decoder.reset(file, duration.offset(at), duration.end);
        deck_second = UINT32_MAX;
    }
    bool start(const char* source) {
        mk61_service_file_info info{};
        if (!call_file(MK61_FILE_BYTES_STAT, source, 0, &info, sizeof(info)) || info.directory) {
            message = M8("Файл недоступен");
            return false;
        }
        Tags next_tags;
        Timing next_duration;
        read_path = source;
        const File file{this, read, info.size};
        tags(file, next_tags);
        const bool valid = timing(file, next_tags, next_duration);
        read_path = path;
        if (!valid) {
            message = M8("Не удалось открыть MP3");
            return false;
        }
        if (source != path) std::memcpy(path, source, std::strlen(source) + 1);
        metadata = next_tags;
        duration = next_duration;
        if (!metadata.title[0]) {
            unsigned length = (unsigned)std::strlen(info.name);
            if (ends_in_mp3(info.name)) length -= 4;
            if (length >= sizeof(metadata.title)) length = sizeof(metadata.title) - 1;
            std::memcpy(metadata.title, info.name, length);
            metadata.title[length] = 0;
        }
        have_track = true;
        paused = false;
        message = nullptr;
        reset_decoder(0);
        redraw();
        return true;
    }

    void order_playlist() {
        const unsigned active = current < tracks ? work->playlist[current] : no_index;
        if (shuffle) {
            if (active < max_entries) {
                work->playlist[current] = work->playlist[0];
                work->playlist[0] = (uint16_t)active;
                current = 0;
            }
            const unsigned first = active < max_entries ? 1 : 0;
            for (unsigned n = tracks; n > first + 1; --n) {
                const unsigned random = services->call(MK61_SERVICE_RANDOM, 0, 0, 0, nullptr);
                const unsigned pick = first + (random >> 8) % (n - first);
                const uint16_t last = work->playlist[n - 1];
                work->playlist[n - 1] = work->playlist[pick];
                work->playlist[pick] = last;
            }
        } else {
            // Restore SD order by walking the raw directory indices once.
            uint8_t included[max_entries / 8]{};
            for (unsigned i = 0; i < tracks; ++i) {
                const unsigned slot = work->playlist[i];
                included[slot / 8] |= 1u << (slot % 8);
            }
            unsigned index = 0;
            for (unsigned slot = 0; slot < max_entries; ++slot) {
                if (!(included[slot / 8] & (1u << (slot % 8)))) continue;
                if (slot == active) current = index;
                work->playlist[index++] = (uint16_t)slot;
            }
        }
    }
    void build_playlist(unsigned active = no_index) {
        std::memcpy(play_directory, directory, std::strlen(directory) + 1);
        tracks = 0;
        current = no_index;
        for (unsigned i = 0; i < count; ++i) {
            const unsigned raw = work->entries[i];
            if (raw & folder) continue;
            if (active == i) current = tracks;
            work->playlist[tracks++] = (uint16_t)raw;
        }
        if (shuffle) order_playlist();
    }
    bool advance(int direction, bool automatic) {
        if (automatic && repeat == 2 && have_track) {
            reset_decoder(0);
            return true;
        }
        if (!have_track) build_playlist();
        const bool known = current < tracks;
        unsigned index = known ? current : direction > 0 && tracks ? tracks - 1 : 0;
        for (unsigned visited = 0; visited < tracks; ++visited) {
            if (automatic && !repeat && known && index + 1 == tracks) break;
            if (direction > 0) index = index + 1 == tracks ? 0 : index + 1;
            else index = index ? index - 1 : tracks - 1;
            mk61_service_file_info info;
            char candidate[path_bytes];
            if (child(play_directory, work->playlist[index], info) && !info.directory &&
                join(play_directory, info.name, candidate) && start(candidate)) {
                current = index;
                return true;
            }
            pump_audio();
            if (!automatic) fill_audio();
        }
        if (automatic) {
            mute();
            paused = true;
        }
        return false;
    }
    void seek(int delta) {
        if (!have_track) return;
        const int after = (int)played_seconds() + delta;
        const unsigned total = duration.seconds();
        if (!total) return;
        unsigned target = after < 0 ? 0 : (unsigned)after;
        if (target >= total) target = total - 1;
        reset_decoder(target);
        if (paused) refresh_deck();
    }
    void toggle_files() {
        browsing = !browsing;
        screen.invalidate_tape();
        if (browsing) {
            const unsigned playing = playing_entry();
            for (unsigned i = 0; i < count; ++i)
                if (work->entries[i] == playing) { selected = i; break; }
            keep_visible();
        }
        redraw();
    }
    bool use_directory(const char* candidate) {
        mk61_service_file_info info{};
        if (!call_file(MK61_FILE_BYTES_STAT, candidate, 0, &info, sizeof(info)) || !info.directory) return false;
        std::memcpy(directory, candidate, std::strlen(candidate) + 1);
        return true;
    }
    void file_key(int key) {
        if (key == function1) { toggle_files(); return; }
        if (key == MK61_APP_KEY_ESC) {
            if (directory[1]) {
                parent();
                scan();
            } else toggle_files();
        } else if (key == MK61_APP_KEY_BACKWARD && selected) {
            --selected;
        } else if (key == MK61_APP_KEY_FORWARD && selected + 1 < count) {
            ++selected;
        } else if (key == MK61_APP_KEY_OK && count) {
            mk61_service_file_info info;
            char candidate[path_bytes];
            if (entry(selected, info) && join(directory, info.name, candidate)) {
                if (info.directory) {
                    std::memcpy(directory, candidate, std::strlen(candidate) + 1);
                    scan();
                } else if (start(candidate)) {
                    build_playlist(selected);
                    toggle_files();
                    return;
                }
            } else message = M8("Файл недоступен");
        } else return;
        keep_visible();
        redraw();
    }
    void player_key(int key) {
        if (key == MK61_APP_KEY_ESC) { running = false; return; }
        if (key == function1) { toggle_files(); return; }
        if (key == function2) {
            shuffle = !shuffle;
            order_playlist();
        } else if (key == function3) repeat = (repeat + 1) % 3;
        else if (key == function4 || key == function5) advance(key == function5 ? 1 : -1, false);
        else if (key == MK61_APP_KEY_LEFT || key == MK61_APP_KEY_RIGHT) seek(key == MK61_APP_KEY_RIGHT ? 5 : -5);
        else if (key == MK61_APP_KEY_BACKWARD || key == MK61_APP_KEY_FORWARD) {
            if (key == MK61_APP_KEY_BACKWARD) volume = volume < 95 ? volume + 5 : 100;
            else volume = volume > 5 ? volume - 5 : 0;
            work->queue.volume(volume);
        } else if (key == space_key) {
            if (!have_track) { toggle_files(); return; }
            if (paused && work->decoder.eof && !work->queue.queued()) reset_decoder(0);
            paused = !paused;
            if (paused) mute();
        } else return;
        refresh_deck();
    }
    static int physical(unsigned key) {
        switch (key) {
        case 0xB4: return MK61_APP_KEY_LEFT;
        case 0xB5: return MK61_APP_KEY_BACKWARD;
        case 0xB6: return MK61_APP_KEY_FORWARD;
        case 0xB7: return MK61_APP_KEY_RIGHT;
        case 0x1B: case 0xB1: return MK61_APP_KEY_ESC;
        case '\r': case '\n': return MK61_APP_KEY_OK;
        // Raw key values can overlap logical keys (e.g. Space and Forward).
        default: return MK61_APP_KEY_RAW_BASE + (int)key;
        }
    }
    void keyboard() {
        uint8_t snapshot[32];
        if (!services->call(MK61_SERVICE_KEYBOARD, MK61_SERVICE_KEY_BITMAP, sizeof(snapshot), 0, snapshot)) return;
        for (unsigned i = 0; i < sizeof(snapshot); ++i) {
            unsigned pressed = snapshot[i] & ~key_state[i];
            if (!pressed) continue;
            for (unsigned bit = 0; bit < 8 && pressed; ++bit) {
                const unsigned mask = 1u << bit;
                if (!(pressed & mask)) continue;
                pressed &= ~mask;
                const int key = physical(i * 8 + bit);
                if ((key == MK61_APP_KEY_RAW_BASE + 'v' || key == MK61_APP_KEY_RAW_BASE + 'V') &&
                    screen.tape_view() != TapeView::none) {
                    const TapeView next = screen.tape_view() == TapeView::cassette ? TapeView::reel : TapeView::cassette;
                    if (screen.select_tape(next)) redraw();
                } else if (browsing) file_key(key);
                else player_key(key);
            }
        }
        std::memcpy(key_state, snapshot, sizeof(snapshot));
    }
    void redraw(unsigned y = 0) {
        draw_y = y;
        draw_end = screen_width;
        strip_ready = false;
        read_page = 0;
        tape_pose_pending = true;
    }
    void refresh_deck() { deck_dirty = true; }
    void display_clock(unsigned now) {
        if ((int32_t)(now - power_check) < 0) return;
        lcd_hz = screen.spi_hz();
        power_check = now + 500;
    }
    void animate(unsigned now) {
        const bool running_now = playing && !browsing && (screen.record || screen.tape_view() != TapeView::none);
        if (clock_running) angle_phase = (angle_phase + now - angle_at) % turn_ms;
        if (clock_running != running_now) {
            if (clock_running) animation_ms += now - animation_started;
            else {
                animation_started = now;
                next_frame = now;
            }
            clock_running = running_now;
        }
        angle_at = now;
    }
    bool draw_record() {
        if (!screen.record) {
            screen.blank(draw_y);
            return submit(screen.present(draw_y, strip_height));
        }
        if (read_page < record_pages) {
            if (!screen.read_record(draw_y, read_page++)) {
                screen.record = nullptr;
                redraw();
                message = M8("RECORD.LP недоступен");
                refresh_deck();
            }
            return false;
        }
        if (!strip_ready) {
            if (!screen.use_record_palette()) return false;
            screen.paint_label(draw_y, metadata.title, metadata.artist);
            strip_ready = true;
        }
        if (!submit(screen.present_record(draw_y, record_strip_height))) return false;
        read_page = 0;
        strip_ready = false;
        return true;
    }
    bool submit(unsigned result) {
        if (!result) {
            display_failed = true;
            running = false;
        }
        return result == 1;
    }
    void draw() {
        const unsigned now = mk61_api->millis_ms();
        animate(now);
        const unsigned position = have_track ? played_seconds() : 0;
        const bool tape = screen.tape_view() != TapeView::none;
        if (draw_y == draw_end && !browsing) {
            if (deck_dirty || deck_second != position) {
                redraw(tape ? (paused ? screen.tape_top() : 192) : record_height);
                deck_dirty = false;
            } else if (clock_running && (int32_t)(now - next_frame) >= 0) {
                redraw(tape ? screen.tape_top() : 0);
                draw_end = tape ? screen.tape_end() : record_height;
                // Finish each picture before starting another. Derive the
                // angle from time so fast mode keeps the same rotation speed.
                screen.angle = angle_phase * rotation_frames / turn_ms;
                next_frame = now + (lcd_hz >= fast_lcd_hz ? 50 : 125);
            }
        }
        if (draw_y == draw_end) return;
        if (playing && work->queue.queued() < StereoQueue::capacity / 2 && !work->decoder.eof) return;
        const unsigned y = draw_y;
        if (tape && !browsing) {
            if (tape_pose_pending) {
                const uint32_t levels = playing ? __atomic_load_n(&work->queue.level, __ATOMIC_RELAXED) : 0;
                screen.tape_pose(position, duration.seconds(), animation_ms + (clock_running ? now - animation_started : 0), levels);
                tape_pose_pending = false;
            }
            if (read_page < 3) {
                if (!screen.read_tape_band(y, read_page++)) {
                    screen.use_record();
                    message = M8("Оформление недоступно");
                    redraw();
                }
                return;
            }
            if (!strip_ready) {
                screen.paint_tape(y, metadata.title, metadata.artist, position, duration.seconds(), volume,
                                  playing, shuffle, repeat, message);
                strip_ready = true;
            }
            if (submit(screen.present_tape(y))) {
                strip_ready = false;
                read_page = 0;
                draw_y += strip_height;
                if (draw_y == screen_width) deck_second = position;
                else if (clock_running && draw_y == screen.tape_end()) {
                    have_animation_frames = true;
                    ++record_frames;
                }
            }
            return;
        }
        if (!browsing && y < record_height) {
            const unsigned height = screen.record ? record_strip_height : strip_height;
            if (draw_record()) {
                draw_y += height;
                if (draw_y == record_height) {
                    strip_ready = false;
                    if (clock_running) {
                        have_animation_frames = true;
                        ++record_frames;
                    }
                }
            }
            return;
        }
        if (!strip_ready) {
            if (browsing) {
                if (y < 64) screen.files_header(y, directory);
                else if (y < 288) {
                    const unsigned offset = first_visible + (y - 64) / 32;
                    if (!(y & 31)) visible_entry_ok = entry(offset, visible_entry);
                    if (visible_entry_ok) {
                        const bool active = work->entries[offset] == playing_entry();
                        screen.file_row(y, visible_entry.name, visible_entry.directory, offset == selected, active);
                    } else screen.file_row(y, nullptr, false, false, false);
                } else screen.files_footer(y, message ? message : scan_limit ? M8("Показаны первые 1024 записи") :
                                           count ? nullptr : M8("Папка пуста"));
            } else {
                screen.paint_deck(y, position, have_track ? duration.seconds() : 0, volume, playing,
                                  shuffle, repeat, message);
            }
            strip_ready = true;
        }
        if (submit(screen.present(y, strip_height))) {
            strip_ready = false;
            draw_y += strip_height;
            if (draw_y == screen_width) deck_second = position;
        }
    }
    void loop() {
        // Ignore the key which launched this APP until its physical release.
        services->call(MK61_SERVICE_KEYBOARD, MK61_SERVICE_KEY_BITMAP, sizeof(key_state), 0, key_state);
        while (running) {
            keyboard();
            if (!running) break;
            fill_audio();
            if (have_track && !paused && work->decoder.eof && !work->queue.queued()) {
                if (work->decoder.failed || !enqueued) {
                    mute();
                    paused = true;
                    message = M8("Ошибка чтения или декодирования");
                } else advance(1, true);
                if (paused) {
                    if (browsing) redraw();
                    else refresh_deck();
                }
            }
            display_clock(mk61_api->millis_ms());
            draw();
            pump_audio();
        }
    }
};

uint32_t run(uint32_t id, uint32_t app_id = UINT32_MAX) {
    const auto* s = mk61_app_get_services(mk61_api, MK61_SERVICE_CAP_BUFFERS | MK61_SERVICE_CAP_COLOR_DISPLAY |
        MK61_SERVICE_CAP_FILE_BYTES | MK61_SERVICE_CAP_AUDIO_STREAM | MK61_SERVICE_CAP_FONT | MK61_SERVICE_CAP_FORMAT |
        MK61_SERVICE_CAP_TEXT_COLORS);
    if (!s || !s->call(MK61_SERVICE_COLOR_DISPLAY, MK61_COLOR_AVAILABLE, 0, 0, nullptr))
        return MK61_APP_UNSUPPORTED_DISPLAY;

    mk61_service_buffer memory{};
    if (!mk61_app_buffer_acquire(s, sizeof(Workspace), MK61_BUFFER_DIRECT, &memory) || !memory.data) {
        if (memory.handle) mk61_app_buffer_release(s, memory.handle);
        return MK61_APP_RUNTIME_ERROR;
    }
    Player app{};
    app.services = s;
    app.work = new (memory.data) Workspace;
    app.work->queue.reset();
    app.work->queue.volume(app.volume);

    mk61_service_buffer art{};
    (void)mk61_app_buffer_acquire(s, tape_chunk_bytes, MK61_BUFFER_DIRECT, &art);
    app.screen.begin(s, app.work->strip, art.data);
    if (id != UINT32_MAX) {
        if (!app.call_file(MK61_FILE_BYTES_PATH, nullptr, id, app.path, sizeof(app.path))) {
            if (art.handle) mk61_app_buffer_release(s, art.handle);
            mk61_app_buffer_release(s, memory.handle);
            return MK61_APP_INVALID_FILE;
        }
        std::memcpy(app.directory, app.path, std::strlen(app.path) + 1);
        app.parent();
        app.scan();
        unsigned active = no_index;
        mk61_service_file_info track;
        if (app.call_file(MK61_FILE_BYTES_STAT, app.path, 0, &track, sizeof(track))) {
            for (unsigned i = 0; i < app.count; ++i) {
                mk61_service_file_info info;
                if (app.entry(i, info) && !info.directory && !std::strcmp(info.name, track.name)) {
                    active = i;
                    break;
                }
                app.pump_audio();
            }
        }
        if (app.start(app.path)) app.build_playlist(active);
        else app.toggle_files();
    } else {
        if (!app.use_directory("/Music") && !app.use_directory("/Documents/Music") && !app.use_directory("/Documents")) {
            if (app_id != UINT32_MAX &&
                app.call_file(MK61_FILE_BYTES_PATH, nullptr, app_id, app.directory, sizeof(app.directory))) {
                app.parent();
            } else {
                std::memcpy(app.directory, "/", 2);
            }
        }
        app.scan();
        app.toggle_files();
    }
    app.screen.cache_tapes();
    if (!app.screen.select_tape(TapeView::cassette)) (void)app.screen.select_tape(TapeView::reel);
    app.loop();
    const unsigned finished_at = mk61_api->millis_ms();
    // Preserve the last stereo sample for the output driver's shutdown ramp.
    app.close_audio();
    app.mute();
    app.animate(finished_at);
    const auto& queue = app.work->queue;
    const unsigned rendered = __atomic_load_n(&queue.rendered, __ATOMIC_RELAXED);
    if (rendered) {
        char line[112];
        const unsigned underruns = __atomic_load_n(&queue.underruns, __ATOMIC_RELAXED);
        const unsigned separated = __atomic_load_n(&queue.separated, __ATOMIC_RELAXED);
        const int length = mk61_app_snprintf(s, line, sizeof(line),
            "MP3_PCM_FRAMES=%u MP3_PCM_UNDERRUNS=%u MP3_PCM_L_NE_R=%u\n", rendered, underruns, separated);
        if (length > 0 && length < (int)sizeof(line))
            s->call(MK61_SERVICE_DEBUG_WRITE, (unsigned)length, 0, 0, line);
    }
    if (app.have_animation_frames) {
        char line[112];
        const int length = mk61_app_snprintf(s, line, sizeof(line),
            "MP3_VIDEO_FRAMES=%u MP3_VIDEO_MS=%u MP3_LCD_HZ=%u\n",
            app.record_frames, app.animation_ms, app.lcd_hz);
        if (length > 0 && length < (int)sizeof(line))
            s->call(MK61_SERVICE_DEBUG_WRITE, (unsigned)length, 0, 0, line);
    }
    s->call(MK61_SERVICE_COLOR_DISPLAY, MK61_COLOR_END, 0, 0, nullptr);
    app.screen.release_tapes();
    if (art.handle) mk61_app_buffer_release(s, art.handle);
    mk61_app_buffer_release(s, memory.handle);
    return app.display_failed ? MK61_APP_UNSUPPORTED_DISPLAY : MK61_APP_OK;
}
}
}

int main() { return (int)mp3::run(UINT32_MAX); }
uint32_t mk61_app_open_file(uint32_t id) { return mp3::run(id); }

uint32_t mk61_app_file_flow(void) { return MK61_APP_FLOW_MAGIC; }

uint32_t mk61_app_flow_step(mk61_app_flow* flow) {
    if (!mk61_app_flow_compatible(flow)) return 0;
    uint32_t file = UINT32_MAX;
    if (flow->current.phase == MK61_APP_FLOW_FILE_PHASE) {
        if (flow->context_size < sizeof(file)) return 0;
        std::memcpy(&file, flow->context, sizeof(file));
    } else if (flow->current.phase != 0) {
        return 0;
    }
    mk61_app_flow_return(flow, mp3::run(file, flow->current.file_id), MK61_FLOW_OK);
    return 1;
}
