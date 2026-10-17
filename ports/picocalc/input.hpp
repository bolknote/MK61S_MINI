#ifndef MK61_PICOCALC_INPUT_HPP
#define MK61_PICOCALC_INPUT_HPP
#include "calculator.hpp"
namespace picocalc {
namespace controls {
enum class Source : u8 { PHYSICAL, REMOTE };
void event(KeyEvent event, Source source = Source::PHYSICAL);
void pulse(u8 code, u32 now);
void clear();
bool pressed(u8 code, u32 now);
int logical(u8 code);
int scan(u8 code);
u8 from_scan(unsigned scan);
u16 chip8_keys(u32 now);
} // namespace controls
} // namespace picocalc
#endif
