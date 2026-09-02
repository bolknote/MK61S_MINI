#ifndef MK61_USB_MASS_STORAGE_HPP
#define MK61_USB_MASS_STORAGE_HPP

namespace usb_mass_storage {
bool init(void);
bool deinit(void);
bool active(void);
// Distinguishes a running USB device from one that the host has accepted and
// configured. macOS Restricted Mode can enumerate a descriptor while
// deliberately refusing SET_CONFIGURATION.
bool host_configured(void);
// True after a successful host START STOP UNIT/EJECT.  This lets the UI leave
// USB Disk mode without requiring a second, physical ESC after the operating
// system has already committed and detached the volume.
bool host_ejected(void);
// True only when STOP can retain the live MSC session without interrupting a
// BOT command or stranding acknowledged dirty cache data.
bool deep_idle_quiescent(void);
void service(void);
}

#endif
