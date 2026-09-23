#ifndef MK61_BASE91_HPP
#define MK61_BASE91_HPP
#include "rust_types.h"

namespace base91 {
struct Output { void* context; bool (*put)(void*, char); };
bool encode(const u8* bytes, usize size, const Output& output);
// Strict, canonical basE91: no ignored characters, whitespace or extra tails.
bool decode(const char* text, usize size, u8* bytes, usize capacity, usize& written);
} // namespace base91
#endif
