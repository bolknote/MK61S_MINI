#ifndef MK61_MP3_AUDIO_HPP
#define MK61_MP3_AUDIO_HPP

#include "metadata.hpp"
#define MK61_MAD_APP 1
#include "mad.h"

namespace mp3 {
constexpr unsigned output_rate = 25000;

struct Decoder {
    struct mad_stream stream;
    struct mad_frame frame;
    struct mad_synth synth;
    unsigned char reservoir[MAD_BUFFER_MDLEN];
    mad_fixed_t overlap[2][32][18];
    uint8_t input[4096 + MAD_BUFFER_GUARD];
    File file;
    uint32_t next, end;
    unsigned length, pcm_at;
    bool padded, eof, failed;

    void reset(File source, uint32_t begin, uint32_t stop);
    // One decoder frame or one refill step. True when there is PCM to drain.
    bool step();
    // Drain one source sample into the resampler.
    uint32_t source_sample() const;
private:
    bool refill();
};

struct Resampler {
    unsigned rate, phase;
    uint32_t previous;
    bool have_previous;
    void reset();
    // Pull outputs before feeding another source sample. At valid MP3 rates
    // this yields at most four samples per input, for each channel separately.
    bool output(uint32_t current, uint32_t& frame);
    void advance(uint32_t current, unsigned source_rate);
};

struct Loudness {
    unsigned envelope = 0, gain = 512, step = 0;
    uint32_t process(uint32_t sample);
};

struct StereoQueue {
    static constexpr unsigned capacity = 1024;
    enum State : uint32_t { MUTED, PLAYING, DISCARD };
    alignas(4) uint32_t write, read, underruns, rendered, separated, gain, finished, state, level;
    uint32_t samples[capacity];

    // Called by the producer only, with the consumer stopped when resetting.
    void reset();
    unsigned queued() const;
    bool ready() const;
    void play();
    void mute();
    void discard();
    void finish();
    bool push(uint32_t sample);
    void volume(unsigned percent);
    static uint32_t consume(void* context);
};
}
#endif
