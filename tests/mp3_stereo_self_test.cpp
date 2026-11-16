#include "audio.hpp"
#include "mk8_literal.hpp"

#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iterator>
#include <vector>

namespace {
bool read(void* object, uint32_t offset, void* data, unsigned count) {
    const auto& input = *static_cast<std::vector<uint8_t>*>(object);
    if (offset > input.size() || count > input.size() - offset) return false;
    std::memcpy(data, input.data() + offset, count);
    return true;
}

struct Frames {
    std::vector<uint32_t> audio;
    mp3::Tags tags;
    mp3::Timing time;
};

Frames decode(const char* path, unsigned seek = 0, unsigned target = mp3::output_rate) {
    std::ifstream stream(path, std::ios::binary);
    std::vector<uint8_t> bytes{std::istreambuf_iterator<char>(stream), {}};
    assert(!bytes.empty());
    const mp3::File file{&bytes, read, (uint32_t)bytes.size()};
    Frames result{};
    mp3::tags(file, result.tags);
    assert(mp3::timing(file, result.tags, result.time));
    const uint32_t start = result.time.offset(seek);
    assert(start >= result.time.first && start < result.time.end);
    mp3::Decoder decoder{};
    decoder.reset(file, start, result.time.end);
    mp3::Resampler resampler{};
    resampler.reset();
    mp3::StereoQueue queue{};
    queue.reset();
    queue.volume(100);
    queue.play();
    for (unsigned iteration = 0; !decoder.eof; ++iteration) {
        assert(iteration < 40000);
        if (!decoder.step(target == mp3::full_rate)) continue;
        if (target == mp3::full_rate && result.time.rate == 44100)
            assert(decoder.synth.pcm.samplerate == 44100);
        for (; decoder.pcm_at < decoder.synth.pcm.length; ++decoder.pcm_at) {
            const uint32_t input = decoder.source_sample();
            uint32_t frame;
            while (resampler.output(input, frame, target)) {
                assert(queue.push(frame));
                result.audio.push_back(mp3::StereoQueue::consume(&queue));
            }
            resampler.advance(input, decoder.synth.pcm.samplerate, target);
        }
    }
    assert(!decoder.failed && !queue.underruns);
    assert(!result.audio.empty());
    return result;
}
double energy(const Frames& data, unsigned channel, unsigned begin, unsigned end) {
    double power = 0;
    unsigned span = (end - begin) * mp3::output_rate / 10;
    for (unsigned at = begin * mp3::output_rate / 10; span--; ++at) {
        const double value = (int16_t)(data.audio.at(at) >> (16 * channel));
        power += value * value;
    }
    return power;
}
double speaker_energy(unsigned frequency, unsigned rate) {
    mp3::Loudness sound;
    double power = 0;
    for (unsigned at = 0; at < rate; ++at) {
        const int16_t input = 9000 * std::sin(6.283185307179586 * frequency * at / rate);
        const uint32_t frame = sound.process(uint16_t(input), true, rate);
        assert(!(frame >> 16));
        const int16_t left = frame;
        assert(std::abs(left) <= 27000);
        if (at >= rate / 2) power += double(left) * left;
    }
    return power;
}
}

int main(int argc, char** argv) {
    assert(argc == 3);
    assert(mp3::ends_in_mp3("Music.Mp3") && !mp3::ends_in_mp3("mp3") && !mp3::ends_in_mp3("Music.mp3.bak"));
    auto stereo = decode(argv[1]);
    assert(!std::strcmp(stereo.tags.title, M8("Ночной сигнал")));
    assert(!std::strcmp(stereo.tags.artist, M8("Линия 12")));
    assert(stereo.time.rate == 44100 && stereo.time.seconds() == 4);
    assert(stereo.audio.size() >= 100000 && stereo.audio.size() < 103000);
    const auto full = decode(argv[1], 0, mp3::full_rate);
    assert(full.audio.size() >= 176400 && full.audio.size() < 182000);
    for (unsigned rate : {mp3::output_rate, mp3::full_rate})
        assert(speaker_energy(60, rate) < speaker_energy(1200, rate) / 6);
    assert(energy(stereo, 0, 2, 8) > 1e11 && energy(stereo, 0, 2, 8) > 200 * energy(stereo, 1, 2, 8));
    assert(energy(stereo, 1, 12, 18) > 1e11 && energy(stereo, 1, 12, 18) > 200 * energy(stereo, 0, 12, 18));
    auto seek = decode(argv[1], 2);
    assert(seek.audio.size() >= 48200 && seek.audio.size() < 53400);
    auto mono = decode(argv[2]);
    assert(!std::strcmp(mono.tags.title, M8("Чёрная вода")));
    assert(!std::strcmp(mono.tags.artist, M8("Малая волна")));
    assert(mono.time.rate == 24000 && mono.time.seconds() == 2);
    assert(mono.audio.size() >= 50000 && mono.audio.size() < 52400);
    assert(std::all_of(mono.audio.begin(), mono.audio.end(), [](uint32_t value) {
        return (uint16_t)value == value >> 16;
    }));
    assert(energy(mono, 0, 2, 8) > 1e10);
    mp3::Loudness loudness;
    assert(loudness.process(0xF8300FA0u) == 0xF0601F40u); // -2000 / 4000, +6 dB.
    const auto limited = loudness.process(0xC0008000u);
    assert((int16_t)limited == -32640 && (int16_t)(limited >> 16) == -16320);
    assert(loudness.process(0) == 0);
    for (unsigned sample = 0; sample < mp3::output_rate; ++sample) loudness.process(0);
    assert(loudness.process(0xF8300FA0u) == 0xF0601F40u);
    mp3::StereoQueue queue{};
    queue.reset();
    queue.volume(50);
    assert(queue.push(0x80007ffeu));
    assert(mp3::StereoQueue::consume(&queue) == 0 && queue.queued() == 1);
    queue.play();
    assert(mp3::StereoQueue::consume(&queue) == 0xc0003fffu);
    assert(queue.rendered == 1 && queue.separated == 1);
    assert(mp3::StereoQueue::consume(&queue) == 0 && queue.underruns == 1);
    queue.finish();
    assert(mp3::StereoQueue::consume(&queue) == 0 && queue.underruns == 1);
    assert(queue.push(0x80007ffeu));
    queue.discard();
    assert(!queue.ready());
    assert(mp3::StereoQueue::consume(&queue) == 0 && queue.queued() == 0 && queue.ready());
    assert(queue.push(0x80007ffeu));
    queue.play();
    assert(mp3::StereoQueue::consume(&queue) == 0xc0003fffu && queue.rendered == 2);
}
