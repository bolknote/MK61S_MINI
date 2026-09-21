#ifndef MK61_USB_MASS_STORAGE_HPP
#define MK61_USB_MASS_STORAGE_HPP

namespace usb_mass_storage {
struct StartupDiagnostic {
  bool valid;
  unsigned stage;
};
bool init(void);
// Loads and validates USBDISK.APP, acquires its caches and opens the virtual
// FAT session while CDC is still available. init() may call this itself, but
// the mode switch uses the explicit phase so only the short USB-core handoff
// happens after Serial.end().
bool prepare(void);
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
// The marker lives in .noinit so a watchdog reset during USB startup still
// identifies the last entered stage after CDC comes back.
StartupDiagnostic startup_diagnostic(void);
void clear_startup_diagnostic(void);
// Internal breadcrumb hook for resident services called by USBDISK.APP while
// init() is still in progress. Calls after successful startup are ignored.
void note_startup_stage(unsigned stage);
}

#endif
