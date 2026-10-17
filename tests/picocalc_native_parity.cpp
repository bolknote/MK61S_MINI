/* Native Pico H contract test. Built both with and without shared runtime. */
#include "basic_graphics_protocol.hpp"
#include "mk61_app.h"
#include <stdint.h>
#include <string.h>
#ifndef PICO_TEST_ROOT
#define PICO_TEST_ROOT "/MK61S-PARITY"
#endif
static unsigned initialized = 42;
static unsigned visits;
static bool last_selected;
static const mk61_app_services *services;
static void log_text(const char *text) {
  services->call(MK61_SERVICE_DEBUG_WRITE, (uint32_t)strlen(text), 0, 0,
                 (void *)text);
}
static bool stay(void) { return false; }
static bool last(void) {
  last_selected = true;
  return true;
}
int main(void) {
  return 17;
} /* Direct legacy call from the cooperative child. */
uint32_t mk61_app_open_file(uint32_t file) {
  services = mk61_app_get_services(mk61_api, MK61_SERVICE_CAP_RUNTIME);
  char bytes[4];
  if (!services || initialized != 42 || visits++ ||
      mk61_api->file_size(file) != sizeof(bytes) ||
      mk61_api->file_read(file, 0, (uint8_t *)bytes, sizeof(bytes)) !=
          sizeof(bytes) ||
      memcmp(bytes, "S1OK", sizeof(bytes)))
    return 29;
  log_text("PICO PARITY FILE_OPEN PASS\n");
  return 0;
}
uint32_t mk61_app_flow_step(mk61_app_flow *flow) {
  if (!mk61_app_flow_compatible(flow) || flow->context_size != 64 ||
      initialized != 42 || visits++)
    return 0;
  services = mk61_app_get_services(
      mk61_api, MK61_SERVICE_CAP_RUNTIME | MK61_SERVICE_CAP_APP_FLOW |
                    MK61_SERVICE_CAP_UI_FONT | MK61_SERVICE_CAP_TEXT_FONT |
                    MK61_SERVICE_CAP_RESOURCES | MK61_SERVICE_CAP_EXPLORER |
                    MK61_SERVICE_CAP_BASIC_GRAPHICS | MK61_SERVICE_CAP_SETUP);
  if (!services)
    return 2;
  uint32_t *context = (uint32_t *)flow->context;
  if (flow->current.phase == 0) {
    volatile uint64_t dividend = UINT64_C(123456789012345),
                      divisor = UINT64_C(1234567);
    if (dividend / divisor != UINT64_C(100000072) ||
        dividend % divisor != UINT64_C(123521))
      return 3;
    volatile double value = 1.25;
    if (value * 2.0 + 0.5 != 3.0 || (uint64_t)value != 1 ||
        (double)divisor != 1234567.0)
      return 4;
    char moved[16] = "abcdef";
    memmove(moved + 1, moved, 6);
    moved[7] = 0;
    if (strcmp(moved, "aabcdef") || strchr(moved, 'd') != moved + 4)
      return 5;
    mk61_service_ui_font_info info = {};
    mk61_service_ui_glyph glyph = {};
    if (!services->call(MK61_SERVICE_UI_FONT, MK61_UI_FONT_INFO, 0,
                        sizeof(info), &info) ||
        info.family != 1)
      return 6;
    glyph.family = info.family;
    glyph.size = info.size;
    if (!services->call(MK61_SERVICE_UI_FONT, MK61_UI_FONT_GLYPH, 0x416,
                        sizeof(glyph), &glyph) ||
        !glyph.width || !glyph.height)
      return 7;
    mk61_service_file fixture = {};
    if (services->call(MK61_SERVICE_FILE_RESOLVE, MK61_SERVICE_ROOT_ID,
                       MK61_SERVICE_FILE_TEXT,
                       (uint32_t)(uintptr_t)(PICO_TEST_ROOT "/fixture.txt"),
                       &fixture) != 0 ||
        fixture.size != 6)
      return 8;
    const uint32_t revision =
        services->call(MK61_SERVICE_RESOURCE_READ, 0, 0, 0, 0);
    uint8_t bytes[6] = {};
    mk61_service_resource resource = {
        revision, (uint16_t)fixture.id, 0, bytes, 6, 0};
    if (!services->call(MK61_SERVICE_RESOURCE_READ, 1, 0, 0, &resource) ||
        memcmp(bytes, "abcdef", 6))
      return 9;
    mk61_service_write created = {"PARITY-created", bytes, 6,
                                  MK61_SERVICE_INVALID_ID};
    if (!services->call(MK61_SERVICE_FILE_WRITE, fixture.parent,
                        MK61_SERVICE_INVALID_ID, MK61_SERVICE_FILE_TEXT,
                        &created))
      return 10;
    if (services->call(MK61_SERVICE_RESOURCE_READ, 1, 0, 0, &resource))
      return 11;
    if (!services->call(MK61_SERVICE_FILE_REMOVE, created.id, 0, 0, 0))
      return 12;
    if (!services->call(MK61_SERVICE_FILE_CHILD_COUNT, fixture.parent, 0, 0, 0))
      return 13;
    if (!(services->call(MK61_SERVICE_FILE_ACTIONS, fixture.id, 0, 0, 0) & 8U))
      return 14;
    const uint32_t columns = mk61_api->display_columns(),
                   rows = mk61_api->display_rows();
    if ((int32_t)services->call(MK61_SERVICE_TEXT_FONT, MK61_TEXT_FONT_BEGIN, 0,
                                0, 0) != 1 ||
        (int32_t)services->call(MK61_SERVICE_TEXT_FONT, MK61_TEXT_FONT_LOAD, 0,
                                0, (void *)(PICO_TEST_ROOT "/Face.FMK")) != 1 ||
        mk61_api->display_columns() != 27 || mk61_api->display_rows() != 9)
      return 15;
    if ((int32_t)services->call(MK61_SERVICE_TEXT_FONT, MK61_TEXT_FONT_END, 0,
                                0, 0) != 1 ||
        mk61_api->display_columns() != columns ||
        mk61_api->display_rows() != rows)
      return 16;
    mk61_setup_profile profile = {};
    if (!services->call(MK61_SERVICE_SETUP, MK61_SETUP_FONT_READ, 0, 0,
                        &profile))
      return 18;
    const mk61_setup_profile original = profile;
    profile.rows = 10;
    profile.width = 3;
    profile.height = 5;
    profile.gap = 0;
    if (!services->call(MK61_SERVICE_SETUP, MK61_SETUP_FONT_APPLY, 0, 0,
                        &profile) ||
        mk61_api->display_columns() != 48)
      return 19;
    profile.rows = 255;
    if (services->call(MK61_SERVICE_SETUP, MK61_SETUP_FONT_APPLY, 0, 0,
                       &profile))
      return 20;
    profile = original;
    if (!services->call(MK61_SERVICE_SETUP, MK61_SETUP_FONT_APPLY, 0, 0,
                        &profile))
      return 21;
    const uint32_t width =
        services->call(MK61_SERVICE_BASIC_GRAPHICS, 0, 0, 0, 0);
    if (width != 192)
      return 22;
    basic_graphics::Request graph = {};
    graph.operation = basic_graphics::Operation::PSET;
    graph.count = 2;
    graph.args[0] = 7;
    graph.args[1] = 9;
    if (services->call(MK61_SERVICE_BASIC_GRAPHICS, 0, 0, sizeof(graph),
                       &graph) != 1)
      return 23;
    graph.operation = basic_graphics::Operation::POINT;
    if (services->call(MK61_SERVICE_BASIC_GRAPHICS, 0, 0, sizeof(graph),
                       &graph) != 1 ||
        graph.value != 1)
      return 24;
    services->call(MK61_SERVICE_BASIC_GRAPHICS, 3, 0, 0, 0);
    char text[64];
    mk61_app_snprintf(services, text, sizeof(text), "PICO PARITY VOLUME=%lu\n",
                      (unsigned long)services->call(
                          MK61_SERVICE_SETTINGS, MK61_SERVICE_VOLUME, 0, 0, 0));
    log_text(text);
    context[0] = 1;
    context[1] = columns;
    context[2] = rows;
    mk61_app_flow_call(
        flow,
        mk61_app_flow_to(MK61_APP_KIND_APPLICATION, flow->current.file_id, 1),
        3);
    return 1;
  }
  if (flow->current.phase == 1) {
    if (context[0] != 1 || mk61_api->display_columns() != context[1] ||
        mk61_api->display_rows() != context[2])
      return 25;
    context[0] = 2;
    mk61_app_flow_call(flow,
                       mk61_app_flow_direct(MK61_APP_KIND_APPLICATION,
                                            flow->current.file_id, MK61_APP_RUN,
                                            4),
                       2);
    return 1;
  }
  if (flow->current.phase == 2) {
    if (flow->result != 17 || flow->status != MK61_FLOW_OK)
      return 26;
    mk61_app_flow_return(flow, 61, MK61_FLOW_OK);
    return 1;
  }
  if (flow->current.phase != 3 || context[0] != 2 || flow->result != 61 ||
      flow->status != MK61_FLOW_OK)
    return 27;
  static const mk61_service_menu_item menu[] = {
      {"1", stay, 0}, {"2", stay, 0},         {"3", stay, 0}, {"4", stay, 0},
      {"5", stay, 0}, {"6", stay, 0},         {"7", stay, 0}, {"8", stay, 0},
      {"9", stay, 0}, {"10: finish", last, 0}};
  log_text("PICO PARITY MENU READY\n");
  if (!services->call(MK61_SERVICE_MENU, 10, 0, 0, (void *)menu) ||
      !last_selected)
    return 28;
  log_text("PICO PARITY API AND FLOW PASS\n");
  mk61_app_flow_exit(flow, 0, MK61_FLOW_OK);
  return 1;
}
