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
_Static_assert(MK61_RUNTIME_COUNT == 26, "runtime service slots are append-only");
_Static_assert(MK61_SERVICE_DISPLAY_END_UI_TEXT == 15 &&
               MK61_SERVICE_DISPLAY_WRITE_CODEPOINT == 16 &&
               MK61_SERVICE_DISPLAY_FLOW_TEXT == 17,
               "display operations are append-only");
_Static_assert(sizeof(mk61_system_text_flow) == 20 &&
               offsetof(mk61_system_text_flow, text) == 0 &&
               offsetof(mk61_system_text_flow, flags) == 16,
               "text-flow wire layout");
_Static_assert(sizeof(mk61_setup_datetime) == 24, "RTC wire layout");
_Static_assert(sizeof(mk61_setup_hardware) == 56, "hardware snapshot layout");
_Static_assert(offsetof(mk61_setup_hardware, rtc_source) == 36, "hardware text boundary");
_Static_assert(sizeof(mk61_setup_profile) == 4, "font profile layout");
_Static_assert(MK61_SETUP_UI_FONT_READ == 14 && MK61_SETUP_UI_FONT_APPLY == 15 &&
               MK61_SETUP_TEXT_MODE == 16, "append-only SETUP font operations");
_Static_assert(MK61_SETUP_UI_FONT_COUNT == 17 && MK61_SETUP_UI_FONT_ITEM == 18 &&
               MK61_SETUP_UI_FONT_CURRENT == 19 &&
               MK61_SETUP_UI_FONT_APPLY_ITEM == 20 &&
               MK61_SETUP_UI_FONT_STEP == 21,
               "append-only SETUP font catalog operations");
_Static_assert(MK61_SETUP_PREPARED_FONT_INSTALL == 22 &&
               MK61_SETUP_UI_FONT_SOURCE == 23,
               "append-only SETUP font compiler operations");
_Static_assert(MK61_SETUP_API_VERSION == 2,
               "SETUP compiler handoff requires service v2");
_Static_assert(sizeof(mk61_setup_ui_font_item) == 40,
               "UI font catalog item wire layout");
_Static_assert(sizeof(mk61_setup_prepared_font) == 20 &&
               offsetof(mk61_setup_prepared_font, role) == 16,
               "prepared-font handoff wire layout");
_Static_assert(sizeof(mk61_setup_ui_font_source) == 8,
               "UI font source wire layout");
_Static_assert(MK61_SETUP_FEATURE_TEXT_PROFILE == 1 &&
               MK61_SETUP_FEATURE_EXTENDED_TEXT_PROFILE == 2 &&
               MK61_SETUP_FEATURE_UI_FONT == 4 &&
               MK61_SETUP_FEATURE_UI_TEXT_MODE == 8 &&
               MK61_SETUP_FEATURE_FIXED_CALCULATOR_FACE == 16 &&
               MK61_SETUP_FEATURE_UI_FONT_CATALOG == 32,
               "append-only SETUP feature bits");
_Static_assert(MK61_SYS_EDITOR_KEY == 24 && MK61_SYS_SETUP == 25, "append-only System operations");
_Static_assert(MK61_SERVICE_CAPABILITIES == 26, "public service capability query");
_Static_assert(MK61_SERVICE_UI_FONT == 27, "append-only proportional font operation");
_Static_assert(MK61_SERVICE_NUMBER_FORMAT == 28,
               "append-only number-format operation");
_Static_assert(sizeof(mk61_service_number_format) == 24,
               "number-format wire layout");
_Static_assert(offsetof(mk61_service_number_format, output) == 8,
               "number-format output pointer");
_Static_assert(MK61_SERVICE_NUMBER_PARSE == 29,
               "append-only number-parse operation");
_Static_assert(sizeof(mk61_service_number_parse) == 16,
               "number-parse wire layout");
_Static_assert(offsetof(mk61_service_number_parse, input) == 8 &&
               offsetof(mk61_service_number_parse, consumed) == 12,
               "number-parse result layout");
_Static_assert(MK61_SERVICE_REF_PARSE == 30,
               "append-only register-reference parser");
_Static_assert(sizeof(mk61_service_ref_parse) == 12,
               "register-reference parser wire layout");
_Static_assert(MK61_SERVICE_TEXT_FONT == 31,
               "append-only temporary text-font service");
_Static_assert(MK61_SERVICE_CAP_TEXT_FONT == (1U << 13),
               "append-only text-font capability");
_Static_assert(MK61_SERVICE_FLOAT_CONVERT == 32,
               "append-only float-conversion operation");
_Static_assert(MK61_SERVICE_CAP_FLOAT_CONVERT == (1U << 14),
               "append-only float-conversion capability");
_Static_assert(MK61_FLOAT_FROM_DOUBLE == 0 && MK61_DOUBLE_FROM_FLOAT == 1,
               "float-conversion operation wire values");
_Static_assert(sizeof(mk61_service_float_convert) == 16 &&
               offsetof(mk61_service_float_convert, bits) == 8,
               "float-conversion wire layout");
_Static_assert(MK61_SERVICE_USBDISK == 33 &&
               MK61_SERVICE_CAP_USBDISK == (1U << 15),
               "append-only private USBDISK service");
_Static_assert(sizeof(mk61_service_usbdisk_geometry) == 64 &&
               offsetof(mk61_service_usbdisk_geometry, logical_sectors) == 60,
               "USBDISK geometry wire layout");
_Static_assert(sizeof(mk61_service_usbdisk_name) == 20 &&
               offsetof(mk61_service_usbdisk_name, name) == 16,
               "USBDISK name wire layout");
_Static_assert(sizeof(mk61_service_usbdisk_extent) == 16,
               "USBDISK extent wire layout");
_Static_assert(sizeof(mk61_service_usbdisk_source) == 52 &&
               offsetof(mk61_service_usbdisk_source, contiguous_data) == 48,
               "USBDISK source wire layout");
_Static_assert(sizeof(mk61_service_usbdisk_stage_filter) == 16 &&
               sizeof(mk61_service_usbdisk_app_validation) == 16,
               "USBDISK callback wire layouts");
_Static_assert(sizeof(mk61_service_usbdisk_stage_snapshot) == 12 &&
               offsetof(mk61_service_usbdisk_stage_snapshot, count) == 8,
               "USBDISK stage snapshot wire layout");
_Static_assert(MK61_USBDISK_STAGE_SNAPSHOT ==
                   MK61_USBDISK_STARTUP_STAGE + 1 &&
               MK61_USBDISK_TRIM_DIRECTORY_EXTENTS ==
                   MK61_USBDISK_STAGE_SNAPSHOT + 1,
               "USBDISK operations are append-only");
_Static_assert(MK61_USBDISK_TRIM_FAILED == 0 &&
               MK61_USBDISK_TRIM_COMPLETE == 1 &&
               MK61_USBDISK_TRIM_MORE == 2,
               "USBDISK trim result wire values");
_Static_assert(MK61_TEXT_FONT_BEGIN == 0 && MK61_TEXT_FONT_LOAD == 1 &&
               MK61_TEXT_FONT_RESTORE == 2 && MK61_TEXT_FONT_END == 3 &&
               MK61_TEXT_FONT_ACTIVATE == 4,
               "text-font operation wire values");
_Static_assert(MK61_TEXT_FONT_NOT_FOUND == 0 && MK61_TEXT_FONT_OK == 1 &&
               MK61_TEXT_FONT_INVALID == -1 &&
               MK61_TEXT_FONT_UNSUPPORTED == -2 &&
               MK61_TEXT_FONT_UNAVAILABLE == -3,
               "text-font signed result values");
_Static_assert(sizeof(mk61_service_ui_font_info) == 6, "UI font metadata wire layout");
_Static_assert(sizeof(mk61_service_ui_glyph) == 40, "UI glyph wire layout");
_Static_assert(offsetof(mk61_service_ui_glyph, pixels) == 8, "UI glyph raster offset");
