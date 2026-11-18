#include "audio.hpp"
#include <cstring>

namespace mp3 {
namespace {
uint32_t stereo(int left, int right) {
    return (uint16_t)left | (uint32_t)(uint16_t)right << 16;
}

uint32_t lerp(uint32_t from, uint32_t to, unsigned blend) {
    const int l = (int16_t)from, r = (int16_t)(from >> 16);
    const int dl = (int16_t)to - l, dr = (int16_t)(to >> 16) - r;
    return stereo(l + (dl * (int)blend >> 12), r + (dr * (int)blend >> 12));
}
}

void Decoder::reset(File source, uint32_t begin, uint32_t stop) {
    mad_stream_init(&stream);
    mad_frame_init(&frame);
    mad_synth_init(&synth);
    stream.main_data = &reservoir;
    frame.overlap = &overlap;
    std::memset(overlap, 0, sizeof(overlap));
    file = source;
    next = begin;
    end = stop;
    length = pcm_at = 0;
    synth.pcm.length = 0;
    padded = eof = failed = false;
}

bool Decoder::refill() {
    unsigned keep = 0;
    if (stream.next_frame) {
        keep = (unsigned)(stream.bufend - stream.next_frame);
        if (keep >= 4096) { failed = true; return false; }
        std::memmove(input, stream.next_frame, keep);
    }
    const unsigned room = 4096 - keep;
    const unsigned count = end - next < room ? end - next : room;
    if (count && !file.read(file.context, next, input + keep, count)) { failed = true; return false; }
    next += count;
    length = keep + count;
    if (next == end) {
        if (!length) return false;
        std::memset(input + length, 0, MAD_BUFFER_GUARD);
        length += MAD_BUFFER_GUARD;
        padded = true;
    }
    mad_stream_buffer(&stream, input, length);
    stream.error = MAD_ERROR_NONE;
    return true;
}

bool Decoder::step(bool full) {
    if (pcm_at < synth.pcm.length) return true;
    if (eof) return false;
    pcm_at = synth.pcm.length = 0;
    if (!length || stream.error == MAD_ERROR_BUFLEN) {
        if (padded || !refill()) { eof = true; return false; }
    }
    if (mad_frame_decode(&frame, &stream) < 0) {
        if (stream.error != MAD_ERROR_BUFLEN && !MAD_RECOVERABLE(stream.error)) eof = failed = true;
        return false;
    }

    if (!full && !(frame.header.flags & MAD_FLAG_LSF_EXT)) {
        // synth_half takes every other PCM sample. Subbands 16–31 would fold
        // into the audible band, so remove them before the synthesis bank.
        for (unsigned ch = 0; ch < MAD_NCHANNELS(&frame.header); ++ch)
            for (auto& slot : frame.sbsample[ch])
                std::memset(slot + 16, 0, 16 * sizeof(*slot));
        frame.options |= MAD_OPTION_HALFSAMPLERATE;
    }
    mad_synth_frame(&synth, &frame);
    return synth.pcm.length != 0;
}

uint32_t Decoder::source_sample() const {
    const int16_t left = synth.pcm.samples[0][pcm_at];
    const int16_t right = synth.pcm.channels == 1 ? left : synth.pcm.samples[1][pcm_at];
    return stereo(left, right);
}

void Resampler::reset() { rate = phase = previous = 0; have_previous = false; }

bool Resampler::output(uint32_t current, uint32_t& frame, unsigned target) {
    if (!have_previous || phase >= target) return false;
    // A 44.1 kHz source in full-rate mode needs no interpolation.
    frame = phase ? lerp(previous, current, (phase << 12) / target) : previous;
    phase += rate;
    return true;
}

void Resampler::advance(uint32_t current, unsigned source_rate, unsigned target) {
    if (have_previous && rate == source_rate) phase -= target;
    else phase = 0;
    rate = source_rate;
    previous = current;
    have_previous = true;
}

uint32_t Loudness::process(uint32_t sample, bool speakers, unsigned rate) {
    int left = (int16_t)sample, right = (int16_t)(sample >> 16);
    if (speakers) {
        // One-pole high pass around 180 Hz, with the low-pass state in Q5.
        const int coefficient = rate == full_rate ? 415 : 725;
        const auto high_pass = [coefficient](int value, int& state) {
            value *= 32;
            state += ((value - state) * coefficient) >> 14;
            return (value - state) / 32;
        };
        left = high_pass(left, low[0]);
        right = high_pass(right, low[1]);
    }
    const unsigned left_peak = left < 0 ? -left : left;
    const unsigned right_peak = right < 0 ? -right : right;
    const unsigned peak = left_peak > right_peak ? left_peak : right_peak;
    // Allow up to +6 dB. A shared envelope preserves the stereo balance.
    // A louder sample can reduce gain immediately; recovery takes hundreds of ms.
    const unsigned decay = rate == full_rate ? 14 : 13;
    envelope -= (envelope + (1u << decay) - 1) >> decay;
    if (peak > envelope) envelope = peak;
    constexpr unsigned unity = 256;
    const unsigned limit = (speakers ? 27000 : 32767) * unity;
    if (!step || peak * gain > limit)
        gain = envelope < limit / (2 * unity) ? 2 * unity : limit / envelope;
    step = (step + 1) & 31;
    return stereo(left * (int)gain / (int)unity, right * (int)gain / (int)unity);
}

// RP2040 needs only aligned atomic loads/stores on this SPSC queue. The IRQ
// is the sole reader and must finish before read/write indices are reset.
void StereoQueue::reset() {
    __atomic_store_n(&write, 0, __ATOMIC_RELAXED);
    __atomic_store_n(&read, 0, __ATOMIC_RELAXED);
    __atomic_store_n(&underruns, 0, __ATOMIC_RELAXED);
    __atomic_store_n(&rendered, 0, __ATOMIC_RELAXED);
    __atomic_store_n(&separated, 0, __ATOMIC_RELAXED);
    __atomic_store_n(&finished, 0, __ATOMIC_RELAXED);
    __atomic_store_n(&state, MUTED, __ATOMIC_RELAXED);
    __atomic_store_n(&level, 0, __ATOMIC_RELAXED);
}
unsigned StereoQueue::queued() const {
    return __atomic_load_n(&write, __ATOMIC_RELAXED) - __atomic_load_n(&read, __ATOMIC_ACQUIRE);
}
bool StereoQueue::ready() const {
    return __atomic_load_n(&state, __ATOMIC_ACQUIRE) != DISCARD;
}
void StereoQueue::play() {
    __atomic_store_n(&state, PLAYING, __ATOMIC_RELEASE);
}
void StereoQueue::mute() {
    if (ready()) __atomic_store_n(&state, MUTED, __ATOMIC_RELEASE);
}
void StereoQueue::discard() {
    // Let the consumer drop old audio before the producer reuses its slots.
    __atomic_store_n(&state, DISCARD, __ATOMIC_RELEASE);
    __atomic_store_n(&finished, 0, __ATOMIC_RELAXED);
}
void StereoQueue::finish() {
    __atomic_store_n(&finished, 1, __ATOMIC_RELEASE);
}
bool StereoQueue::push(uint32_t sample) {
    const unsigned at = __atomic_load_n(&write, __ATOMIC_RELAXED);
    if (at - __atomic_load_n(&read, __ATOMIC_ACQUIRE) >= capacity) return false;
    samples[at & (capacity - 1)] = sample;
    __atomic_store_n(&write, at + 1, __ATOMIC_RELEASE);
    return true;
}
void StereoQueue::volume(unsigned percent) {
    __atomic_store_n(&gain, percent * 256 / 100, __ATOMIC_RELAXED);
}
uint32_t StereoQueue::consume(void* context) {
    auto& queue = *(StereoQueue*)context;
    const unsigned mode = __atomic_load_n(&queue.state, __ATOMIC_ACQUIRE);
    if (mode == DISCARD) {
        const unsigned written = __atomic_load_n(&queue.write, __ATOMIC_RELAXED);
        __atomic_store_n(&queue.read, written, __ATOMIC_RELEASE);
        __atomic_store_n(&queue.state, MUTED, __ATOMIC_RELEASE);
    }
    if (mode != PLAYING) return 0;

    const unsigned at = __atomic_load_n(&queue.read, __ATOMIC_RELAXED);
    if (at == __atomic_load_n(&queue.write, __ATOMIC_ACQUIRE)) {
        if (!__atomic_load_n(&queue.finished, __ATOMIC_ACQUIRE)) {
            // No read-modify-write helper: the IRQ is the only writer.
            const unsigned lost = __atomic_load_n(&queue.underruns, __ATOMIC_RELAXED);
            __atomic_store_n(&queue.underruns, lost + 1, __ATOMIC_RELAXED);
        }
        return 0;
    }
    const uint32_t sample = queue.samples[at & (capacity - 1)];
    __atomic_store_n(&queue.read, at + 1, __ATOMIC_RELEASE);
    const unsigned rendered = __atomic_load_n(&queue.rendered, __ATOMIC_RELAXED);
    __atomic_store_n(&queue.rendered, rendered + 1, __ATOMIC_RELAXED);
    const int volume = (int)__atomic_load_n(&queue.gain, __ATOMIC_RELAXED);
    const int left = (int16_t)sample * volume >> 8;
    const int right = (int16_t)(sample >> 16) * volume >> 8;
    if (left != right) {
        const unsigned separated = __atomic_load_n(&queue.separated, __ATOMIC_RELAXED);
        __atomic_store_n(&queue.separated, separated + 1, __ATOMIC_RELAXED);
    }
    const auto output = stereo(left, right);
    if (!(rendered & 31)) __atomic_store_n(&queue.level, output, __ATOMIC_RELAXED);
    return output;
}
}
