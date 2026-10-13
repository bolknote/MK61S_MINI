#include "config.h"
#if (defined(MK61_BUILD_SETUP_MODULE) || MK61_SETUP_IS_BUILTIN) && MK61_UI_FONT_CLIENT

#include "setup_font_compiler.hpp"

#include "fmk_font.hpp"
#include "language_workspace.hpp"
#include "loadable_app_services.h"
#include "prepared_font.hpp"
#include "setup_service.hpp"
#if MK61_SETUP_IS_LOADABLE
#include "system_compat.hpp"
#else
#include "program_store.hpp"
#endif

namespace setup_font_compiler {
namespace {

static_assert(prepared_font::MAX_IMAGE_SIZE <= 0xFFFFU,
              "prepared font handoff length must fit 16 bits");

struct Source {
  u16 id;
  u32 revision;
  bool failed;
  u16 size;
};

u32 source_revision() {
#if MK61_SETUP_IS_LOADABLE
  return portable_system::call(MK61_SERVICE_RESOURCE_READ, 0, 0, 0, nullptr);
#else
  return program_store::media_revision();
#endif
}

u32 file_size(u16 id) {
#if MK61_SETUP_IS_LOADABLE
  return portable_system::app->file_size(id);
#else
  program_store::Entry entry = {};
  return program_store::entry_by_id(id, entry) ? entry.data_len : 0;
#endif
}

bool stream_source(void* raw, bool (*next)(void*, u8), void* consumer) {
  Source& source = *static_cast<Source*>(raw);
  struct Consumer {
    bool (*next)(void*, u8);
    void* context;
    bool rejected;
    static bool append(void* raw, u8 value) {
      auto& consumer = *static_cast<Consumer*>(raw);
      const bool accepted = consumer.next(consumer.context, value);
      consumer.rejected = !accepted;
      return accepted;
    }
  } callback = {next, consumer, false};
#if MK61_SETUP_IS_LOADABLE
  mk61_service_resource_bytes request = {
      source.revision, source.id, source.size, &callback, Consumer::append};
  const bool ok = portable_system::call(MK61_SERVICE_RESOURCE_READ,
                                        3, 0, 0, &request) != 0;
#else
  const program_store::FileSink sink = {&callback, Consumer::append};
  const bool ok = source_revision() == source.revision &&
      program_store::stream_file_id(source.id, sink);
#endif
  if(!ok && !callback.rejected) source.failed = true;
  return ok;
}

} // namespace

i32 install(u16 id, u8 role, u8 expected_height,
            u32 ui_key, u8 flags) {
  if(role > MK61_PREPARED_FONT_UI ||
     (role == MK61_PREPARED_FONT_UI && expected_height != 0 &&
      expected_height != 12 && expected_height != 14 &&
      expected_height != 16)) return MK61_TEXT_FONT_INVALID;
  Source source = {id, source_revision(), false, 0};
  const u32 source_size = file_size(id);
  if(source_size < fmk::HEADER_SIZE || source_size > fmk::MAX_FILE_SIZE)
    return MK61_TEXT_FONT_INVALID;
  source.size = (u16) source_size;
  language_workspace::Lease workspace(language_workspace::Owner::SETUP,
                                       language_workspace::SIZE);
  if(!workspace.ok()) return MK61_TEXT_FONT_UNAVAILABLE;
  usize prepared_size = 0;
  // Decode the immutable source once into a complete candidate in WORKSPACE.
  // BULK still holds the old font until the resident atomically installs it.
  const fmk::StreamSource reader = {&source, source_size, stream_source};
  if(!fmk::prepare(reader, static_cast<u8*>(workspace.data()), workspace.size(),
                   prepared_size)) {
    return source.failed ? MK61_TEXT_FONT_UNAVAILABLE : MK61_TEXT_FONT_INVALID;
  }
  if(source_revision() != source.revision) return MK61_TEXT_FONT_UNAVAILABLE;

  mk61_setup_prepared_font request = {
      static_cast<const u8*>(workspace.data()), (u32) prepared_size,
      id, ui_key, role, expected_height, flags, 0};
  return (i32) setup_ui::service(MK61_SETUP_PREPARED_FONT_INSTALL,
                                 0, 0, &request);
}

} // namespace setup_font_compiler

#endif
