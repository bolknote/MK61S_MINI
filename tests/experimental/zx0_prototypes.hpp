#ifndef MK61_ZX0_PROTOTYPES_HPP
#define MK61_ZX0_PROTOTYPES_HPP
#include "zx0.hpp"
namespace zx0_prototypes {
using Decode = bool(*)(const zx0::Input&, u32, u8*, u32, u32&);
using Encode = bool(*)(const u8*, u32, u8*, usize, const zx0::Output&, zx0::EncodeResult&);
#define ZX0_PROTOTYPE(name) \
bool decode_##name(const zx0::Input&, u32, u8*, u32, u32&); \
bool encode_##name(const u8*, u32, u8*, usize, const zx0::Output&, zx0::EncodeResult&);
ZX0_PROTOTYPE(scalar)
ZX0_PROTOTYPE(word)
ZX0_PROTOTYPE(dsp)
#undef ZX0_PROTOTYPE
}
#endif
