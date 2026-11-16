#ifndef PICOCALC_LCD_READBACK_H
#define PICOCALC_LCD_READBACK_H

#include <stdbool.h>
#include <stdint.h>

/* A small, testable diagnostic SPI protocol. The caller owns an idle LCD bus
 * and restores its normal configuration after reading. Coordinates are GRAM
 * addresses, not scrolled or partially masked screen coordinates. */
typedef struct {
    void *ctx;
    bool (*lines)(void *ctx, bool selected, bool data);
    bool (*transfer)(void *ctx, uint8_t out, uint8_t *in);
} picocalc_lcd_read_bus;

static inline bool picocalc_lcd_command(picocalc_lcd_read_bus *bus, uint8_t op,
                                        const uint8_t *data, unsigned count) {
    uint8_t ignored;
    bool ok = bus->lines(bus->ctx, true, false) && bus->transfer(bus->ctx, op, &ignored);
    if (ok && count) ok = bus->lines(bus->ctx, true, true);
    for (unsigned i = 0; ok && i < count; ++i) ok = bus->transfer(bus->ctx, data[i], &ignored);
    return bus->lines(bus->ctx, false, true) && ok;
}

static inline bool picocalc_lcd_read_pixel(picocalc_lcd_read_bus *bus, unsigned x, unsigned y, uint8_t rgb[3]) {
    if (!bus || !bus->lines || !bus->transfer || !rgb || x >= 320 || y >= 480) return false;
    const uint8_t column[] = {(uint8_t)(x >> 8), (uint8_t)x, (uint8_t)(x >> 8), (uint8_t)x};
    const uint8_t row[] = {(uint8_t)(y >> 8), (uint8_t)y, (uint8_t)(y >> 8), (uint8_t)y};
    uint8_t ignored;
    if (!picocalc_lcd_command(bus, 0x2a, column, sizeof(column)) ||
        !picocalc_lcd_command(bus, 0x2b, row, sizeof(row))) return false;
    bool ok = bus->lines(bus->ctx, true, false) && bus->transfer(bus->ctx, 0x2e, &ignored) &&
              bus->lines(bus->ctx, true, true) && bus->transfer(bus->ctx, 0, &ignored);
    /* On the PicoCalc panel RAMRD returns RGB565 as two big-endian bytes,
     * followed by the next pixel. Expand to the probe's three 6-bit channels. */
    uint8_t high = 0, low = 0;
    if (ok) ok = bus->transfer(bus->ctx, 0, &high);
    if (ok) ok = bus->transfer(bus->ctx, 0, &low);
    if (ok) {
        const uint16_t value = (uint16_t)((uint16_t)high << 8) | low;
        const unsigned r = (value >> 11) & 31, g = (value >> 5) & 63, b = value & 31;
        rgb[0] = (uint8_t)(((r << 1) | (r >> 4)) << 2);
        rgb[1] = (uint8_t)(g << 2);
        rgb[2] = (uint8_t)(((b << 1) | (b >> 4)) << 2);
    }
    return bus->lines(bus->ctx, false, true) && ok;
}

/* Read one physical GRAM row, preserving the 5/6/5 significant input bits.
 * Channel order is checked independently against the calibration pattern. */
static inline bool picocalc_lcd_read_row565(picocalc_lcd_read_bus *bus, unsigned y, uint8_t out[640]) {
    if (!bus || !bus->lines || !bus->transfer || !out || y >= 480) return false;
    const uint8_t column[] = {0,0,1,63};
    const uint8_t row[] = {(uint8_t)(y >> 8),(uint8_t)y,(uint8_t)(y >> 8),(uint8_t)y};
    uint8_t ignored;
    if (!picocalc_lcd_command(bus,0x2a,column,sizeof(column)) ||
        !picocalc_lcd_command(bus,0x2b,row,sizeof(row))) return false;
    bool ok=bus->lines(bus->ctx,true,false) && bus->transfer(bus->ctx,0x2e,&ignored) &&
            bus->lines(bus->ctx,true,true) && bus->transfer(bus->ctx,0,&ignored);
    for(unsigned x=0;ok && x<320;++x) {
        uint8_t high, low;
        ok=bus->transfer(bus->ctx,0,&high) && bus->transfer(bus->ctx,0,&low);
        if(ok) { out[2*x]=low;out[2*x+1]=high; }
    }
    return bus->lines(bus->ctx,false,true) && ok;
}
#endif
