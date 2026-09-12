#include <assert.h>

namespace program_store {

enum class NodeKind {
  FILE,
  DIRECTORY,
};

enum class ProgramType {
  MK61,
  FOCAL,
  TINYBASIC,
  TEXT,
  MK61_STATE,
  MARKDOWN,
  FONT,
  IMAGE1,
  APP,
  CHIP8,
};

struct Entry {
  NodeKind kind;
  ProgramType type;
};

}  // namespace program_store

namespace file_handlers {

static bool handler_available = false;

bool available(const program_store::Entry&) {
  return handler_available;
}

}  // namespace file_handlers

#include "explorer_entry_can_run.inc"

int main() {
  using program_store::Entry;
  using program_store::NodeKind;
  using program_store::ProgramType;

  const Entry app = {NodeKind::FILE, ProgramType::APP};
#if MK61_ANY_LOADABLE_MODULE
  assert(entry_can_run(app));
#else
  assert(!entry_can_run(app));
#endif

  const Entry directory = {NodeKind::DIRECTORY, ProgramType::APP};
  assert(!entry_can_run(directory));

  const Entry text = {NodeKind::FILE, ProgramType::TEXT};
  assert(!entry_can_run(text));

  const Entry markdown = {NodeKind::FILE, ProgramType::MARKDOWN};
  file_handlers::handler_available = false;
  assert(!entry_can_run(markdown));
  file_handlers::handler_available = true;
  assert(entry_can_run(markdown));
}
