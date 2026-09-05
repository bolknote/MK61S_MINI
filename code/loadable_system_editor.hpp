#ifndef MK61_LOADABLE_SYSTEM_EDITOR_HPP
#define MK61_LOADABLE_SYSTEM_EDITOR_HPP
#include "loadable_system_api.h"
#include "text_editor.hpp"

namespace loadable_module { namespace system_editor {
static const char* insert(text_editor::Shift shift, i32 key, const char* source, u16 cursor, void* context) {
  auto& request = *(mk61_system_edit_key*) context;
  mk61_system_edit_hook event = {(char*) source, 0, cursor, 0, (u32) shift, key, 0, request.context};
  return (const char*) (usize) request.hook(MK61_EDIT_INSERT, &event);
}
static bool alpha(char* source, u16& len, u16& cursor, u16 capacity, i32 key, void* context) {
  auto& request = *(mk61_system_edit_key*) context;
  mk61_system_edit_hook event = {source, len, cursor, capacity, 0, key, 0, request.context};
  const bool result = request.hook(MK61_EDIT_ALPHA, &event);
  len = (u16) event.length; cursor = (u16) event.cursor; return result;
}
static bool move(const char* source, u16 len, u16& cursor, int delta, void* context) {
  auto& request = *(mk61_system_edit_key*) context;
  mk61_system_edit_hook event = {(char*) source, len, cursor, 0, 0, 0, delta, request.context};
  const bool result = request.hook(MK61_EDIT_MOVE, &event);
  cursor = (u16) event.cursor; return result;
}
static bool backspace(char* source, u16& len, u16& cursor, u16 capacity, void* context) {
  auto& request = *(mk61_system_edit_key*) context;
  mk61_system_edit_hook event = {source, len, cursor, capacity, 0, 0, 0, request.context};
  const bool result = request.hook(MK61_EDIT_BACKSPACE, &event);
  len = (u16) event.length; cursor = (u16) event.cursor; return result;
}
static u32 handle(mk61_system_edit_key& request) {
  if(request.capacity > 0xFFFFU || request.length > 0xFFFFU ||
      request.cursor > 0xFFFFU || request.top > 0xFFFFU || request.shift > 2 ||
      request.sms_index > 0xFFU || (request.hook_mask && !request.hook)) return 0;
  text_editor::Buffer editor = {request.source, (u16) request.capacity,
      (u16) request.length, (u16) request.cursor, (u16) request.top,
      (text_editor::Shift) request.shift,
      {request.sms_active != 0, request.sms_key, (u8) request.sms_index, request.sms_deadline}};
  const i32* k = request.keys;
  const text_editor::KeyMap keys = {k[0], k[1], k[2], k[3], k[4], k[5], k[6],
                                    k[7], k[8], k[9], k[10], k[11], k[12]};
  const text_editor::Hooks hooks = {request.hook_mask & 1 ? insert : nullptr,
      request.hook_mask & 2 ? alpha : nullptr, request.hook_mask & 4 ? move : nullptr,
      request.hook_mask & 8 ? backspace : nullptr, &request};
  const text_editor::Options options = {request.ok_text,
      (request.options & 1) != 0, (request.options & 2) != 0,
      (request.options & 4) != 0, request.backspace_key};
  const u32 result = (u32) text_editor::handle_key(editor, keys, hooks, options, request.key, request.now);
  request.length = editor.len; request.cursor = editor.cursor; request.top = editor.view_top;
  request.shift = (u32) editor.shift; request.sms_active = editor.sms.active;
  request.sms_key = editor.sms.key_code; request.sms_index = editor.sms.index;
  request.sms_deadline = editor.sms.deadline_ms;
  return result;
}
} }
#endif
