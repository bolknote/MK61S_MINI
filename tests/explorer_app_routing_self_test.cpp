#include <assert.h>
#include <string.h>

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

#define M8(text) text
static unsigned messages = 0;
static unsigned waits = 0;
static void show_message(const char* en0, const char* ru0,
                         const char* en1, const char* ru1) {
  assert(strcmp(en0, "CHIP-8") == 0 && strcmp(ru0, "CHIP-8") == 0);
  assert(strcmp(en1, "unavailable") == 0);
  assert(strcmp(ru1, "недоступен") == 0);
  messages++;
}
static int wait_explorer_key(bool repeat) {
  assert(!repeat);
  waits++;
  return 0;
}

#include "explorer_entry_can_run.inc"

int main() {
  using program_store::Entry;
  using program_store::NodeKind;
  using program_store::ProgramType;

  const Entry app = {NodeKind::FILE, ProgramType::APP};
#if MK61_APP_RUNTIME_AVAILABLE
  assert(entry_can_run(app));
#else
  assert(!entry_can_run(app));
#endif

  const Entry directory = {NodeKind::DIRECTORY, ProgramType::APP};
  assert(!entry_can_run(directory));

  const Entry text = {NodeKind::FILE, ProgramType::TEXT};
  assert(!entry_can_run(text));
  assert(!reject_unavailable_chip8(text));
  assert(!reject_unavailable_chip8(directory));

  const Entry chip8 = {NodeKind::FILE, ProgramType::CHIP8};
  file_handlers::handler_available = false;
  assert(!entry_can_run(chip8));
  assert(reject_unavailable_chip8(chip8));
  assert(messages == 1 && waits == 1);
  // Both a built-in interpreter and a discovered CHIP8.APP are available
  // through this same policy; neither should be blocked by the diagnostic.
  file_handlers::handler_available = true;
  assert(entry_can_run(chip8));
  assert(!reject_unavailable_chip8(chip8));
  assert(messages == 1 && waits == 1);

  const Entry markdown = {NodeKind::FILE, ProgramType::MARKDOWN};
  file_handlers::handler_available = false;
  assert(!entry_can_run(markdown));
  file_handlers::handler_available = true;
  assert(entry_can_run(markdown));
}
