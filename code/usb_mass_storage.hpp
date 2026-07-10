#ifndef MK61_USB_MASS_STORAGE_HPP
#define MK61_USB_MASS_STORAGE_HPP

namespace usb_mass_storage {
bool init(void);
bool deinit(void);
bool active(void);
void service(void);
}

#endif
