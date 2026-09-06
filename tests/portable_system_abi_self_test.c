#include "loadable_system_api.h"
#include <stddef.h>

/* Public wire records use the ARM AAPCS layout on both F401 and F411. */
_Static_assert(sizeof(void*) == 4, "compile for ARM");
_Static_assert(offsetof(mk61_app_api, query_service) == 104, "original APP prefix unchanged");
_Static_assert(sizeof(mk61_app_api) == 108, "append-only service query");
_Static_assert(sizeof(mk61_system_api) == 28, "System API v1");
_Static_assert(offsetof(mk61_system_api, runtime) == 24, "runtime table slot");
_Static_assert(sizeof(mk61_system_keyboard) == 42, "keyboard wire layout");
_Static_assert(sizeof(mk61_system_file) == 52, "file wire layout");
_Static_assert(offsetof(mk61_system_file, name) == 20, "file name offset");
_Static_assert(sizeof(mk61_system_lease) == 48, "lease wire layout");
_Static_assert(_Alignof(mk61_system_lease) == 8, "lease alignment");
_Static_assert(offsetof(mk61_system_lease, data) == 32, "opaque lease boundary");
_Static_assert(offsetof(mk61_system_lease, image_crc) == 44, "workspace schema key");
_Static_assert(sizeof(mk61_system_menu_item) == 12, "menu wire layout");
_Static_assert(sizeof(mk61_system_edit_hook) == 32, "editor callback wire layout");
_Static_assert(sizeof(mk61_system_edit_key) == 124, "editor state wire layout");
_Static_assert(MK61_RUNTIME_COUNT == 22, "runtime service slots are append-only");
_Static_assert(sizeof(mk61_setup_datetime) == 24, "RTC wire layout");
_Static_assert(sizeof(mk61_setup_hardware) == 56, "hardware snapshot layout");
_Static_assert(offsetof(mk61_setup_hardware, rtc_source) == 36, "hardware text boundary");
_Static_assert(sizeof(mk61_setup_profile) == 4, "font profile layout");
_Static_assert(MK61_SYS_EDITOR_KEY == 24 && MK61_SYS_SETUP == 25, "append-only System operations");
_Static_assert(MK61_SERVICE_CAPABILITIES == 26, "public service capability query");
