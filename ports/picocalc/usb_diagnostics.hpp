#ifndef MK61_PICOCALC_USB_DIAGNOSTICS_HPP
#define MK61_PICOCALC_USB_DIAGNOSTICS_HPP
#include "rust_types.h"
namespace picocalc { namespace usb {
struct Counters {
    u32 reads, writes, read_errors, write_errors, last_lba;
    u8 last_scsi;
    u64 sd_read_us, read_started_us;
    u32 read_commands, active_read_lba, active_read_bytes;
    u32 max_read_us, max_read_bytes, max_read_lba;
};
const Counters& counters();
} }
#endif
