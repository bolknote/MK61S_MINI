#ifndef MK61_MP3_METADATA_HPP
#define MK61_MP3_METADATA_HPP

#include <cstdint>

namespace mp3 {
struct File {
    void* context;
    bool (*read)(void*, uint32_t offset, void* data, unsigned count);
    uint32_t size;
};
struct Tags {
    char title[96], artist[96]; // M8
    uint32_t begin, end;        // Audio byte range, excluding leading/trailing tags.
};
struct Timing {
    uint32_t first, end, rate, frames, samples;
    uint8_t toc[100];
    bool has_toc;

    uint32_t seconds() const;
    uint32_t offset(uint32_t seconds) const;
};
bool ends_in_mp3(const char* name);
void tags(File file, Tags& out);
bool timing(File file, const Tags& tags, Timing& out);
}
#endif
