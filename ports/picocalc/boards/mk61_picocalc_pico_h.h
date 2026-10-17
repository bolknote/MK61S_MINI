#ifndef MK61_PICOCALC_PICO_H_BOARD_H
#define MK61_PICOCALC_PICO_H_BOARD_H

// ClockworkPi v2.0 with the original Raspberry Pi Pico H (RP2040).
// No overclock: flash, core and peripheral clocks use the Pico SDK defaults.
pico_board_cmake_set(PICO_PLATFORM, rp2040)
#define MK61_BOARD_PICOCALC_PICO_H 1
#define PICO_DEFAULT_I2C 1
#define PICO_DEFAULT_I2C_SDA_PIN 6
#define PICO_DEFAULT_I2C_SCL_PIN 7
#define PICO_DEFAULT_SPI 1
#define PICO_DEFAULT_SPI_SCK_PIN 10
#define PICO_DEFAULT_SPI_TX_PIN 11
#define PICO_DEFAULT_SPI_RX_PIN 12
#define PICO_DEFAULT_SPI_CSN_PIN 13
#define MK61_PICOCALC_LCD_DC_PIN 14
#define MK61_PICOCALC_LCD_RESET_PIN 15
#include "boards/pico.h"

#endif
