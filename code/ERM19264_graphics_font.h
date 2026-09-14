/*!
* @file ERM19264_graphics_font.h
* @brief Fonts used by the MK61 UC1609 renderer.
* @author Gavin Lyons.
* @details <https://github.com/gavinlyonsrepo/ERM19264_UC1609>
*/

#ifndef ERM19264_FONT_S_H
#define ERM19264_FONT_S_H

#if (ARDUINO >=100)
  #include "Arduino.h"
#else
  #include "WProgram.h"
#endif

#ifdef __AVR__
 #include <avr/io.h>
 #include <avr/pgmspace.h>
#else
#ifndef ESP8266
 #define PROGMEM
#endif
#endif
 
#define UC1609_Font_One

// Font data is in the cpp file.  The default table is exported directly so
// using it does not spend a mutable pointer in .data/RAM.
#ifdef UC1609_Font_One
extern const unsigned char UC_Font_One[];
const unsigned char* font3x5Glyph(uint16_t codepoint);
#endif

#endif // font file guard header
