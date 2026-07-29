#include "file_handlers.hpp"

#include "config.h"
#if MK61_IMAGE1_VIEWER_IS_BUILTIN
  #include "image1_viewer.hpp"
  #include "menu.hpp"
#endif
#if MK61_MARKDOWN_VIEWER_IS_BUILTIN
  #include "markdown_viewer.hpp"
#endif
#if MK61_CHIP8_IS_BUILTIN
  #include "chip8_runner.hpp"
#endif
#if MK61_ANY_LOADABLE_MODULE
  #include "loadable_module_runtime.hpp"
#endif

namespace file_handlers {
namespace {

static bool valid_file(const program_store::Entry& entry) {
  return entry.kind == program_store::NodeKind::FILE &&
         program_store::type_magic(entry.type) !=
             program_store::TYPE_MAGIC_NONE;
}

#if MK61_IMAGE1_VIEWER_IS_BUILTIN
static loadable_module::FileOpenResult image_result(
    image1_viewer::Result result) {
  using loadable_module::FileOpenResult;
  switch(result) {
    case image1_viewer::Result::OK:
      return FileOpenResult::OK;
    case image1_viewer::Result::BUSY:
      return FileOpenResult::BUSY;
    case image1_viewer::Result::READ_ERROR:
      return FileOpenResult::IO_ERROR;
    case image1_viewer::Result::INVALID_IMAGE:
    case image1_viewer::Result::DECODE_ERROR:
      return FileOpenResult::INVALID_FILE;
    case image1_viewer::Result::UNSUPPORTED_DISPLAY:
      return FileOpenResult::UNSUPPORTED_DISPLAY;
    case image1_viewer::Result::DISPLAY_ERROR:
      return FileOpenResult::RUNTIME_ERROR;
  }
  return FileOpenResult::RUNTIME_ERROR;
}
#endif

#if MK61_MARKDOWN_VIEWER_IS_BUILTIN
static loadable_module::FileOpenResult markdown_result(
    markdown_viewer::Result result) {
  using loadable_module::FileOpenResult;
  switch(result) {
    case markdown_viewer::Result::OK:
      return FileOpenResult::OK;
    case markdown_viewer::Result::BUSY:
      return FileOpenResult::BUSY;
    case markdown_viewer::Result::READ_ERROR:
      return FileOpenResult::IO_ERROR;
    case markdown_viewer::Result::INVALID_DOCUMENT:
      return FileOpenResult::INVALID_FILE;
    case markdown_viewer::Result::DISPLAY_ERROR:
      return FileOpenResult::RUNTIME_ERROR;
  }
  return FileOpenResult::RUNTIME_ERROR;
}
#endif

} // namespace

bool available(const program_store::Entry& entry) {
  if(!valid_file(entry)) return false;
  const program_store::TypeMagic magic =
      program_store::type_magic(entry.type);

#if MK61_IMAGE1_VIEWER_IS_BUILTIN
  if(magic == program_store::TYPE_MAGIC_IMAGE1) return true;
#endif

#if MK61_MARKDOWN_VIEWER_IS_BUILTIN
  if(magic == program_store::TYPE_MAGIC_MARKDOWN) return true;
#endif

#if MK61_CHIP8_IS_BUILTIN
  if(magic == program_store::TYPE_MAGIC_CHIP8) return true;
#endif

#if MK61_ANY_LOADABLE_MODULE
  loadable_module::FileHandler handler = {};
  return loadable_module::find_file_handler(magic, handler);
#else
  return false;
#endif
}

loadable_module::FileOpenResult open(const program_store::Entry& entry) {
  using loadable_module::FileOpenResult;
  if(!valid_file(entry)) return FileOpenResult::INVALID_FILE;
  const program_store::TypeMagic magic =
      program_store::type_magic(entry.type);

#if MK61_IMAGE1_VIEWER_IS_BUILTIN
  if(magic == program_store::TYPE_MAGIC_IMAGE1) {
    return image_result(image1_viewer::view_entry(main_lcd(), entry));
  }
#endif

#if MK61_MARKDOWN_VIEWER_IS_BUILTIN
  if(magic == program_store::TYPE_MAGIC_MARKDOWN) {
    return markdown_result(markdown_viewer::view_entry(main_lcd(), entry));
  }
#endif

#if MK61_CHIP8_IS_BUILTIN
  if(magic == program_store::TYPE_MAGIC_CHIP8) {
    return chip8_runner::run_entry(entry);
  }
#endif

#if MK61_ANY_LOADABLE_MODULE
  loadable_module::FileHandler handler = {};
  if(!loadable_module::find_file_handler(magic, handler)) {
    return FileOpenResult::INVALID_FILE;
  }
  u32 raw_result = (u32) FileOpenResult::RUNTIME_ERROR;
  const loadable_module::RuntimeStatus status =
      loadable_module::open_file(handler, entry.id, raw_result);
  if(status != loadable_module::RuntimeStatus::OK) {
    return status == loadable_module::RuntimeStatus::BUSY
        ? FileOpenResult::BUSY : FileOpenResult::RUNTIME_ERROR;
  }
  if(raw_result > (u32) FileOpenResult::RUNTIME_ERROR) {
    return FileOpenResult::RUNTIME_ERROR;
  }
  return (FileOpenResult) raw_result;
#else
  return FileOpenResult::INVALID_FILE;
#endif
}

} // namespace file_handlers
