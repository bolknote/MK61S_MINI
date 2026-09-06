#ifndef MK61_SETUP_UI_HPP
#define MK61_SETUP_UI_HPP
#include "rust_types.h"
namespace setup_ui {
bool hardware();
bool date_time();
bool calibration();
bool font();
void step_font(i8 delta);
// The caller retains the source buffer until preview returns.
void preview(const char* name, const u8* data, u16 size);
}
#endif
