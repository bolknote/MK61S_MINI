#ifndef MK61_USB_MASS_STORAGE_HPP
#define MK61_USB_MASS_STORAGE_HPP

namespace usb_mass_storage {
bool init(void);
bool deinit(void);
bool active(void);
// True only when STOP can retain the live MSC session without interrupting a
// BOT command or stranding acknowledged dirty cache data.
bool deep_idle_quiescent(void);
void service(void);
}

#endif
