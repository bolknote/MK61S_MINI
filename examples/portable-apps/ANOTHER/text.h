#ifndef MK61_ANOTHER_TEXT_H
#define MK61_ANOTHER_TEXT_H
#include <stdint.h>
typedef struct { uint16_t id; const char *text; } aw_string;
extern const uint8_t aw_font[];
extern const aw_string aw_strings[];
#endif
