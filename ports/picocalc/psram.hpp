#ifndef MK61_PICOCALC_PSRAM_HPP
#define MK61_PICOCALC_PSRAM_HPP
#include "rust_types.h"
#include "cosmic_clock.hpp"
#include "psram_probe.hpp"
#include "block_read.hpp"
namespace picocalc::psram {
constexpr u32 CAPACITY=8U*1024*1024;
struct Statistics {
    bool ready,qpi;
    u32 id,hz,read_bytes,write_bytes,errors,qpi_fallbacks,read_batches,write_batches;
    u32 tail_timeouts,tail_state;
    BootProbe boot;
};
bool init();
#if MK61_PICOCALC_MANAGED_CLOCK
bool diagnostic_clock_divider(u32 divider256);
u32 diagnostic_clock_divider256(); // Read the actual PIO register.
#endif
bool ready();
void prepare_reset(); // Return retained powered RAM to SPI before ROM/old firmware.
bool read(u32 address,void* bytes,unsigned count);
// Optional zero-copy QPI/DMA read. Aligned 16-byte spans must concatenate into
// one aligned SRAM destination, at most 2048 bytes. Refusal starts no DMA.
// The calling core owns the bus/destination until read_finish() returns.
bool read_begin(u32 base,const block_io::ReadSpan* spans,unsigned count);
bool read_finish();
bool write(u32 address,const void* bytes,unsigned count);
Statistics statistics();
bool self_test(void (*service)()=nullptr);
#if !defined(PICO_ON_DEVICE)
// Explicit injection leaves the normal host suite on the no-PSRAM fallback.
void test_memory(u8* bytes,unsigned capacity);
#endif
}
#endif
