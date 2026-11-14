#ifndef FL_M3_DIAGNOSTIC_PINS_H
#define FL_M3_DIAGNOSTIC_PINS_H
/* Read-only fields in the exact KEY25 body, CRC3BE158B4 / SHA256
 * 4c65bec8684ce551eb993cd9253b8a5704e92737553da94ffba99919c8ae233f.
 * hi2c1 ELF symbol=0x200005EC,size84; native build uses -fshort-enums.
 * HAL_Interface_I2C1_reset at0x08003890 writes State at hi2c1+61 (STRB)
 * and ErrorCode at+64 (STR). These are observations, never native writes. */
#define FL_M3_HAL_STATE 0x20000629u
#define FL_M3_HAL_ERROR 0x2000062cu
#define FL_M3_I2CS_STATE 0x20000640u
#define FL_M3_I2CS_RECOVER 0x20000641u
#endif
