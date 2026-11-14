#include "metadata.hpp"
#include "mk8_codec.hpp"
#include <cstring>

namespace mp3 {
namespace {
uint32_t big(const uint8_t* bytes, unsigned count, unsigned bits = 8) {
    uint32_t result = 0;
    while (count--) result = (result << bits) | *bytes++;
    return result;
}

bool synchsafe(const uint8_t* bytes) {
    return !((bytes[0] | bytes[1] | bytes[2] | bytes[3]) & 0x80);
}

struct Reader {
    File file;
    uint32_t pos, end, buffer_start = 0;
    unsigned count = 0;
    bool unsync = false, previous_ff = false;
    uint8_t buffer[256];

    Reader(File source, uint32_t first, uint32_t last) : file(source), pos(first), end(last) {}

    int byte() {
        while (pos < end) {
            if (!count || pos < buffer_start || pos - buffer_start >= count) {
                buffer_start = pos;
                count = end - pos;
                if (count > sizeof(buffer)) count = sizeof(buffer);
                if (!file.read(file.context, pos, buffer, count)) {
                    pos = end;
                    return -1;
                }
            }
            const unsigned v = buffer[pos++ - buffer_start];
            const bool stuffing = unsync && previous_ff && v == 0;
            previous_ff = v == 255;
            if (!stuffing) return (int)v;
        }
        return -1;
    }

    bool read(uint8_t* target, unsigned size) {
        while (size--) {
            const int value = byte();
            if (value < 0) return false;
            *target++ = (uint8_t)value;
        }
        return true;
    }

    void skip(uint32_t size) {
        if (unsync) {
            while (size-- && byte() >= 0) {}
        } else {
            pos += size > end - pos ? end - pos : size;
        }
    }
};

uint8_t text_byte(uint32_t cp) {
    if (cp == 0xA0 || cp == '\t' || cp == '\r' || cp == '\n') return ' ';
    uint8_t result;
    if (cp >= 0x20 && mk8::from_codepoint(cp, result)) return result;
    // Common accented Latin characters are still readable on the M8 display.
    if (cp >= 0xC0 && cp <= 0xFF)
        return (uint8_t)"AAAAAAACEEEEIIIIDNOOOOO?OUUUUYTsaaaaaaaceeeeiiiidnooooo?ouuuuyty"[cp - 0xC0];
    return '?';
}

void trim(char* text, unsigned length) {
    while (length && text[length - 1] == ' ') --length;
    text[length] = 0;
}

void decode_text(const uint8_t* bytes, unsigned count, char (&out)[96]) {
    if (!count || bytes[0] > 3) return;
    const unsigned encoding = *bytes++;
    --count;
    const bool wide = encoding == 1 || encoding == 2;
    bool little = false;
    if (encoding == 1) {
        if (count < 2) return;
        little = bytes[0] == 0xFF && bytes[1] == 0xFE;
        if (!little && (bytes[0] != 0xFE || bytes[1] != 0xFF)) return;
        bytes += 2;
        count -= 2;
    }

    unsigned length = 0;
    while (count && length + 1 < sizeof(out)) {
        uint32_t cp = bytes[0];
        unsigned used = 1;
        if (wide) {
            if (count < 2) break;
            cp = little ? bytes[0] | (bytes[1] << 8) : big(bytes, 2);
            used = 2;
            if (cp >= 0xD800 && cp <= 0xDBFF && count >= 4) {
                const unsigned last = little ? bytes[2] | (bytes[3] << 8) : big(bytes + 2, 2);
                if (last >= 0xDC00 && last <= 0xDFFF) {
                    cp = 0x10000 + ((cp - 0xD800) << 10) + last - 0xDC00;
                    used = 4;
                }
            }
        } else if (encoding == 3) {
            const auto decoded = utf8_codec::decode(bytes, count);
            cp = decoded.codepoint;
            used = decoded.size;
        }
        if (!cp) break;
        const uint8_t value = text_byte(cp);
        if (length || value != ' ') out[length++] = (char)value;
        bytes += used;
        count -= used;
    }
    trim(out, length);
}

void read_v2(File file, Tags& out) {
    uint8_t header[10];
    if (file.size < sizeof(header) || !file.read(file.context, 0, header, sizeof(header)) ||
        std::memcmp(header, "ID3", 3) || !synchsafe(header + 6)) return;

    const unsigned version = header[3], flags = header[5];
    const uint32_t stop = 10 + big(header + 6, 4, 7);
    const uint32_t audio = stop + (version == 4 && (flags & 0x10) ? 10 : 0);
    if (audio > file.size) return;
    out.begin = audio;
    if (version < 2 || version > 4 || (version == 2 && (flags & 0x40))) return;

    Reader cursor{file, 10, stop};
    cursor.unsync = version < 4 && (flags & 0x80);
    uint8_t frame[10];
    if (version >= 3 && (flags & 0x40)) {
        if (!cursor.read(frame, 4) || (version == 4 && !synchsafe(frame))) return;
        const uint32_t length = big(frame, 4, version == 4 ? 7 : 8);
        if (version == 4 && length < 6) return;
        cursor.skip(version == 4 ? length - 4 : length);
    }

    const unsigned id_size = version == 2 ? 3 : 4;
    const unsigned head_size = version == 2 ? 6 : 10;
    for (unsigned n = 0; n < 256 && (!out.title[0] || !out.artist[0]); ++n) {
        if (!cursor.read(frame, head_size) || !frame[0] ||
            (version == 4 && !synchsafe(frame + 4))) break;
        const uint32_t length = big(frame + id_size, id_size, version == 4 ? 7 : 8);
        if (!length || length > cursor.end - cursor.pos) break;
        auto* text = !std::memcmp(frame, version == 2 ? "TT2" : "TIT2", id_size) ? &out.title
                   : !std::memcmp(frame, version == 2 ? "TP1" : "TPE1", id_size) ? &out.artist : nullptr;
        const unsigned format = version == 2 ? 0 : frame[9];
        if (!text || (*text)[0] || (format & (version == 4 ? 0x0C : 0xC0))) {
            cursor.skip(length);
            continue;
        }
        const unsigned prefix = version == 4
            ? ((format & 0x40) ? 1 : 0) + ((format & 1) ? 4 : 0)
            : (format & 0x20) ? 1 : 0;
        if (prefix >= length) {
            cursor.skip(length);
            continue;
        }
        uint8_t bytes[385];
        const unsigned limit = length - prefix < sizeof(bytes) ? length - prefix : sizeof(bytes);
        if (version == 4) {
            const uint32_t tag_end = cursor.end;
            const uint32_t frame_end = cursor.pos + length;
            cursor.unsync = (flags & 0x80) || (format & 2);
            cursor.previous_ff = false;
            cursor.end = frame_end;
            cursor.skip(prefix);
            unsigned copied = 0;
            while (copied < limit && cursor.read(bytes + copied, 1)) ++copied;
            decode_text(bytes, copied, *text);
            cursor.end = tag_end;
            cursor.pos = frame_end;
            cursor.unsync = false;
        } else {
            cursor.skip(prefix);
            if (cursor.read(bytes, limit)) decode_text(bytes, limit, *text);
            cursor.skip(length - prefix - limit);
        }
    }
}

void read_v1(File file, Tags& out) {
    uint8_t tail[128];
    if (file.size < sizeof(tail) || !file.read(file.context, file.size - sizeof(tail), tail, sizeof(tail)) ||
        std::memcmp(tail, "TAG", 3)) return;
    const uint32_t end = file.size - sizeof(tail);
    if (end < out.begin) return;
    out.end = end;
    // ID3v1 has no charset marker. First accept valid UTF-8, then use M8's
    // Windows-1251 mapping for old Russian libraries.
    for (unsigned field = 0; field < 2; ++field) {
        auto& target = field ? out.artist : out.title;
        if (target[0]) continue;
        const auto* value = tail + 3 + field * 30;
        unsigned size = 0;
        while (size < 30 && value[size]) ++size;
        usize written = 0;
        if (mk8::from_utf8(value, size, (uint8_t*)target, sizeof(target) - 1, written)) {
            trim(target, (unsigned)written);
        } else {
            for (unsigned i = 0; i < size; ++i)
                target[i] = value[i] < 0x20 || !mk8::valid_byte(value[i]) ? '?' : (char)value[i];
            trim(target, size);
        }
    }
}

struct Header {
    uint32_t bytes, rate, samples;
    unsigned info_at;
};

bool parse_header(const uint8_t* data, Header& info) {
    const unsigned version = (data[1] >> 3) & 3;
    const unsigned bit = data[2] >> 4;
    const unsigned rate_code = (data[2] >> 2) & 3;
    if (data[0] != 255 || (data[1] & 0xE6) != 0xE2 ||
        version == 1 || !bit || bit == 15 || rate_code == 3) return false;
    static constexpr uint16_t rates[] = {44100, 48000, 32000};
    static constexpr uint16_t bitrates[2][14] = {
        {8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160},
        {32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320}
    };
    const bool mpeg1 = version == 3;
    const bool mono = (data[3] >> 6) == 3;
    info.rate = rates[rate_code] >> (mpeg1 ? 0 : version == 2 ? 1 : 2);
    info.samples = mpeg1 ? 1152 : 576;
    info.bytes = bitrates[mpeg1][bit - 1] * (mpeg1 ? 144000u : 72000u) / info.rate + ((data[2] >> 1) & 1);
    info.info_at = 4 + ((data[1] & 1) ? 0 : 2) + (mpeg1 ? (mono ? 17 : 32) : (mono ? 9 : 17));
    return true;
}
}

bool ends_in_mp3(const char* name) {
    const size_t length = std::strlen(name);
    return length > 4 && name[length - 4] == '.' &&
        (name[length - 3] | 32) == 'm' && (name[length - 2] | 32) == 'p' && name[length - 1] == '3';
}

void tags(File file, Tags& out) {
    out = {};
    out.end = file.size;
    read_v2(file, out);
    read_v1(file, out);
}

bool timing(File file, const Tags& input, Timing& out) {
    out = {};
    uint8_t probe[4096];
    const unsigned count = input.end - input.begin < sizeof(probe) ? input.end - input.begin : sizeof(probe);
    if (count < 4 || !file.read(file.context, input.begin, probe, count)) return false;

    for (unsigned at = 0; at + 4 <= count; ++at) {
        Header h{}, next{};
        if (!parse_header(probe + at, h) || h.bytes > input.end - input.begin - at) continue;
        const uint32_t following = input.begin + at + h.bytes;
        if (following < input.end) {
            uint8_t scratch[4];
            const uint8_t* second = scratch;
            if (at + h.bytes + 4 <= count) second = probe + at + h.bytes;
            else if (input.end - following < 4 || !file.read(file.context, following, scratch, 4)) continue;
            if (!parse_header(second, next) || next.rate != h.rate) continue;
        }
        out.first = input.begin + at;
        out.end = input.end;
        out.rate = h.rate;
        out.samples = h.samples;
        const uint32_t estimated = (out.end - out.first) / h.bytes;
        out.frames = estimated;

        unsigned p = at + h.info_at;
        if (h.info_at + 8 <= h.bytes && p + 8 <= count &&
            (!std::memcmp(probe + p, "Xing", 4) || !std::memcmp(probe + p, "Info", 4))) {
            const uint32_t flags = big(probe + p + 4, 4);
            p += 8;
            const unsigned limit = at + h.bytes < count ? at + h.bytes : count;
            if ((flags & 1) && p + 4 <= limit) {
                const uint32_t frames = big(probe + p, 4);
                if (frames && frames <= (out.end - out.first) / 16 + 1) out.frames = frames;
                p += 4;
            }
            if ((flags & 2) && p + 4 <= limit) {
                const uint32_t bytes = big(probe + p, 4);
                if (bytes >= h.bytes && bytes <= out.end - out.first) out.end = out.first + bytes;
                p += 4;
            }
            if ((flags & 4) && p + sizeof(out.toc) <= limit) {
                std::memcpy(out.toc, probe + p, sizeof(out.toc));
                out.has_toc = true;
                for (unsigned i = 1; i < sizeof(out.toc); ++i)
                    if (out.toc[i] < out.toc[i - 1]) out.has_toc = false;
            }
        } else if (h.bytes >= 54 && at + 54 <= count && !std::memcmp(probe + at + 36, "VBRI", 4)) {
            const uint32_t bytes = big(probe + at + 46, 4);
            const uint32_t frames = big(probe + at + 50, 4);
            if (bytes >= h.bytes && bytes <= out.end - out.first) out.end = out.first + bytes;
            if (frames && frames <= (out.end - out.first) / 16 + 1) out.frames = frames;
        }
        return true;
    }
    return false;
}

uint32_t Timing::seconds() const {
    return rate ? (uint32_t)((uint64_t)frames * samples / rate) : 0;
}

uint32_t Timing::offset(uint32_t sec) const {
    if (!sec || !rate || !frames) return first;
    const uint64_t sample_at = (uint64_t)sec * rate;
    const uint64_t total = (uint64_t)frames * samples;
    if (sample_at >= total) return end;
    const uint32_t size = end - first;
    if (!has_toc) return first + (uint32_t)((sample_at * 65536 / total) * size >> 16);

    const uint32_t percent = (uint32_t)(sample_at * 25600 / total);
    const unsigned i = percent >> 8;
    const unsigned a = toc[i], b = i == 99 ? 256 : toc[i + 1];
    const uint32_t fraction = a * 256 + (b - a) * (percent & 255);
    return first + (uint32_t)((uint64_t)size * fraction >> 16);
}
}
