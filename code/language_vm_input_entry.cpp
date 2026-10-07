#if defined(MK61_BUILD_LANGUAGE_INPUT_MODULE)
#include <string.h>
#include "language_vm_abi.hpp"
#include "loadable_module_abi.hpp"
#include "mk_math.hpp"
#include "text_editor.hpp"

namespace {
using namespace language_vm;
void invalid_number() {
  const char* rows[] = {"Invalid number", "Try again"};
  portable_system::text_rows(rows, 2);
  delay(500);
}
uint32_t validate(OverlayRequest* p) {
  const auto result = validate_execution(p);
  if (result && p->execution->result.error == Error::NONE && p->action == OverlayAction::START) {
    const bool shared_screen = p->state->language == Language::BASIC &&
                               p->execution->mode == 1;
    if(!shared_screen) main_lcd().endUiText();
    if (portable_system::call(MK61_SERVICE_CAPABILITIES) & MK61_SERVICE_CAP_TEXT_FONT)
      portable_system::call(MK61_SYS_TEXT_FONT, MK61_SYS_TEXT_FONT_ACTIVATE);
    if(!shared_screen) main_lcd().clear();
  }
  return result;
}
uint32_t finish(OverlayRequest* p) {
  if (!execution_compatible(p)) return 0;
  auto& r = *p->execution;
  auto& s = *p->state;
  if (s.cancelled) r.result.error = s.normal_stop ? Error::NONE : Error::STOPPED;
  else if (s.failure != Error::NONE) r.result.error = s.failure;
  if (r.result.error != Error::NONE &&
      !(r.mode == 1 && r.result.error == Error::STOPPED)) {
    const char* rows[] = {error_name(r.result.error),
                          s.language == Language::BASIC ? "TinyBASIC" : "FOCAL"};
    portable_system::text_rows(rows, 2);
  }
  if (r.mode == 0 && (s.language == Language::FOCAL || !r.pause_final)) {
    for (;;) {
      idle_main_process();
      const auto event = kbd::poll_event();
      if (event.code() >= 0 && event.code() < (i32)key_state::RELEASED) {
        kbd::handoff(event); break;
      }
      delay(10);
    }
  }
  return 1;
}
uint32_t input(InputRequest* r) {
  if (!r || r->size != sizeof(*r) || r->version != REQUEST_VERSION ||
      !r->image || r->capacity != INPUT_IMAGE_CAPACITY ||
      (r->prompt_length && !r->prompt) ||
      (r->language != Language::BASIC && r->language != Language::FOCAL)) return 0;
  for (uint8_t byte : r->reserved) if (byte) return 0;
  r->result = InputResult::NONE; r->image_size = 0;
  if (r->invalid) invalid_number();
  char text[65] = {};
  text_editor::Buffer editor;
  text_editor::init(editor, text, sizeof(text));
  for (;;) {
    {
      MK61DisplayUpdate update(main_lcd());
      main_lcd().clear();
      const uint8_t rows = main_lcd().rows();
      const uint8_t n = rows > 1 ? main_lcd().printWrappedText(
          r->prompt, r->prompt_length, 0, (u8)(rows - 1), true, false) : 0;
      main_lcd().setCursor(0, n);
      main_lcd().print("> "); main_lcd().print(text);
    }
    const i32 key = kbd::get_key_wait();
    if (editor.shift == text_editor::Shift::NONE &&
        (key == KEY_ESC || key == KEY_ESC_PRESS)) {
      kbd::handoff(kbd::Event(KEY_ESC_PRESS));
      r->result = InputResult::CANCELLED; return 1;
    }
    if (editor.shift == text_editor::Shift::NONE &&
        (key == KEY_OK || key == KEY_OK_PRESS)) {
      if (r->language == Language::FOCAL) {
        const char* end = nullptr;
        if (portable_system::parse_number(text, r->value, end)) {
          while (*end == ' ' || *end == '\t') ++end;
          if (!*end && mk_math::is_finite(r->value)) {
            r->result = InputResult::VALUE; return 1;
          }
        }
      } else {
        const auto compiled = compile_expression(
            Language::BASIC, text, editor.len, r->image, r->capacity);
        if (compiled.error == Error::NONE) {
          r->image_size = compiled.size;
          r->result = InputResult::EXPRESSION; return 1;
        }
      }
      invalid_number(); text_editor::init(editor, text, sizeof(text)); continue;
    }
    text_editor::portable_handle_default_key(editor, "", key, millis());
  }
}
}  // namespace
extern "C" u32 mk61_app_initialize(const mk61_app_api* api, u32 crc, u32 kind) {
  return portable_system::bind(api, crc, kind) ? 0 : MK61_APP_RUNTIME_ERROR;
}
extern "C" u32 mk61_app_command(u32 command, u32 argument0, u32, u32, u32) {
  if (command == (u32)loadable_module::Command::LANGUAGE_VM_INFO) return INPUT_MAGIC;
  if (command == (u32)loadable_module::Command::LANGUAGE_VM_VALIDATE)
    return validate((OverlayRequest*)(usize)argument0);
  if (command == (u32)loadable_module::Command::LANGUAGE_VM_FINISH)
    return finish((OverlayRequest*)(usize)argument0);
  return command == (u32)loadable_module::Command::LANGUAGE_INPUT
      ? input((InputRequest*)(usize)argument0) : 0;
}
#endif
