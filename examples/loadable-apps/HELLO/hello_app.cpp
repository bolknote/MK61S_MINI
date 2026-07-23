#include "loadable_app_api.hpp"
#include "loadable_module_abi.hpp"

namespace {

const loadable_app::Api* app_api;

bool accept_api(u32 argument0) {
  const loadable_app::Api* candidate =
      loadable_app::from_argument(argument0);
  if(!loadable_app::compatible(candidate)) return false;
  app_api = candidate;
  return true;
}

} // namespace

extern "C" __attribute__((used, section(".mk61_module_entry")))
u32 mk61_module_entry(u32 raw_command, u32 argument0, u32, u32, u32) {
  const loadable_module::Command command =
      (loadable_module::Command) raw_command;
  switch(command) {
    case loadable_module::Command::INITIALIZE:
      return accept_api(argument0) ? 0 : 1;

    case loadable_module::Command::APPLICATION_RUN: {
      if(!accept_api(argument0)) return 1;
      if((app_api->capabilities & loadable_app::CAP_TEXT_DISPLAY) != 0) {
        static const char title[] = "HELLO APP";
        static const char prompt[] = "KEY TO EXIT";
        app_api->display_clear();
        app_api->display_write_utf8(0, 0, title, sizeof(title) - 1);
        if(app_api->display_rows() > 1) {
          app_api->display_write_utf8(0, 1, prompt, sizeof(prompt) - 1);
        }
      }
      if((app_api->capabilities & loadable_app::CAP_LED) != 0) {
        app_api->led_blink(2, 80, 80);
      }
      if((app_api->capabilities & loadable_app::CAP_SOUND) != 0) {
        app_api->beep(880, 80, 35);
      }
      return (app_api->capabilities & loadable_app::CAP_KEYBOARD) != 0
          ? (u32) app_api->key_wait() : 0;
    }

    default:
      return 0;
  }
}
