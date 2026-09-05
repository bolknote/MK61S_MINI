#include "system_compat.hpp"
#include "text_editor.hpp"

namespace text_editor {
static u32 call_hook(u32 operation, mk61_system_edit_hook* event) {
  const Hooks& hooks = *(const Hooks*) event->context;
  u16 len = (u16) event->length, cursor = (u16) event->cursor;
  u32 result = 0;
  switch(operation) {
    case MK61_EDIT_INSERT:
      return (u32) (usize) hooks.insert_text_for_key((Shift) event->shift,
          event->key, event->source, cursor, hooks.context);
    case MK61_EDIT_ALPHA:
      result = hooks.apply_alpha_macro(event->source, len, cursor,
          (u16) event->capacity, event->key, hooks.context); break;
    case MK61_EDIT_MOVE:
      result = hooks.move_cursor_horizontal(event->source, len, cursor,
          (int) event->delta, hooks.context); break;
    case MK61_EDIT_BACKSPACE:
      result = hooks.backspace(event->source, len, cursor,
          (u16) event->capacity, hooks.context); break;
  }
  event->length = len; event->cursor = cursor;
  return result;
}
KeyResult portable_handle_key(Buffer& editor, const KeyMap& keys, const Hooks& hooks,
                               const Options& options, i32 key, u32 now) {
  mk61_system_edit_key request = {
      editor.source, editor.capacity, editor.len, editor.cursor, editor.view_top,
      (u32) editor.shift, editor.sms.active, editor.sms.index,
      editor.sms.deadline_ms, editor.sms.key_code,
      {keys.left, keys.left_press, keys.right, keys.right_press,
       keys.ok, keys.ok_press, keys.esc, keys.esc_press, keys.shg_left_press,
       keys.shg_right_press, keys.k, keys.alpha, keys.pp},
      options.ok_insert_text, (u32) (options.sms_enabled | options.alpha_digit_symbols << 1 |
          options.alpha_cx_clear_line << 2), options.backspace_key, key, now,
      (u32) ((hooks.insert_text_for_key != nullptr) | (hooks.apply_alpha_macro != nullptr) << 1 |
          (hooks.move_cursor_horizontal != nullptr) << 2 | (hooks.backspace != nullptr) << 3),
      call_hook, (void*) &hooks};
  const u32 result = portable_system::call(MK61_SYS_EDITOR_KEY, 0, 0, 0, &request);
  editor.len = (u16) request.length; editor.cursor = (u16) request.cursor;
  editor.view_top = (u16) request.top; editor.shift = (Shift) request.shift;
  editor.sms = {request.sms_active != 0, request.sms_key, (u8) request.sms_index,
                request.sms_deadline};
  return (KeyResult) result;
}
}
