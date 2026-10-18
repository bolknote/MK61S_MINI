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
int raw_key(u8 code);
int native_key(KeyEvent event);
bool raw_pressed(i32 key,u32 now);
bool any_pressed(u32 now);
using Listener=void(*)(void*,KeyEvent);
void set_listener(Listener callback,void* context);
void service(u32 now);
u8 from_scan(unsigned scan);
u16 chip8_keys(u32 now);
} // namespace controls
} // namespace picocalc
#endif
