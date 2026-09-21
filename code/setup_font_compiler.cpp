#if defined(MK61_BUILD_SETUP_MODULE) && MK61_UI_FONT_CLIENT

#include "setup_font_compiler.hpp"

#include "fmk_font.hpp"
#include "language_workspace.hpp"
#include "loadable_app_services.h"
#include "prepared_font.hpp"
#include "setup_service.hpp"
#include "system_compat.hpp"

namespace setup_font_compiler {
namespace {

// FMK is transient input.  Keeping it in SETUP.APP BSS leaves the shared
// workspace available for the complete PFK2 candidate, so the resident can
// validate and install atomically without overwriting the active font first.
alignas(8) static u8 source[prepared_font::MAX_IMAGE_SIZE];

} // namespace

i32 install(u16 id, u8 role, u8 expected_height,
            u32 ui_key, u8 flags) {
  if(role > MK61_PREPARED_FONT_UI ||
     (role == MK61_PREPARED_FONT_UI && expected_height != 0 &&
      expected_height != 12 && expected_height != 14 &&
      expected_height != 16)) return MK61_TEXT_FONT_INVALID;
  const u32 source_size = portable_system::app->file_size(id);
  if(source_size < fmk::HEADER_SIZE || source_size > sizeof(source))
    return MK61_TEXT_FONT_INVALID;
  if(portable_system::app->file_read(id, 0, source, source_size) != source_size)
    return MK61_TEXT_FONT_UNAVAILABLE;

  fmk::Face face;
  if(!face.open(source, source_size)) return MK61_TEXT_FONT_INVALID;
  language_workspace::Lease workspace(language_workspace::Owner::SETUP,
                                       language_workspace::SIZE);
  if(!workspace.ok()) return MK61_TEXT_FONT_UNAVAILABLE;
  usize prepared_size = 0;
  if(!fmk::prepare(face, static_cast<u8*>(workspace.data()), workspace.size(),
                   prepared_size) || prepared_size > 0xFFFFU) {
    return MK61_TEXT_FONT_INVALID;
  }

  mk61_setup_prepared_font request = {
      static_cast<const u8*>(workspace.data()), (u32) prepared_size,
      id, ui_key, role, expected_height, flags, 0};
  return (i32) setup_ui::service(MK61_SETUP_PREPARED_FONT_INSTALL,
                                 0, 0, &request);
}

} // namespace setup_font_compiler

#endif
