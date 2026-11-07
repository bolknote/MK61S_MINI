#ifndef MK61_AI_HARNESS_HPP
#define MK61_AI_HARNESS_HPP
#include <cstddef>
#include <cstdint>
namespace mk61ai {
constexpr unsigned PROGRAM_SIZE = 105, TEST_COUNT = 8, INPUT_COUNT = 19;
constexpr unsigned SCENARIO_STEPS = 4, SESSION_BYTES = 12288;
constexpr std::uint32_t X_MASK = 1U << 15;
enum class Intent : std::uint8_t { WRITE, FIX, EXPLAIN };
enum class RunState : std::uint8_t {
  DRAFT,
  RUNNING,
  NEEDS_INPUT,
  PAUSED,
  FINISHED,
  LIMIT,
  ERROR
};
enum class Execution : std::uint8_t {
  NONE,
  STOPPED,
  LIMIT,
  ERROR,
  CANCELLED,
  BUSY,
  INVALID
};
struct Program {
  std::uint32_t version = 0, task_revision = 0;
  std::uint16_t size = 0;
  std::uint8_t bytes[PROGRAM_SIZE]{};
};
struct ScenarioStep {
  double input = 0, expected = 0;
  std::uint8_t input_index = 255, output_index = 255,
               key = 0x29; // Physical x/y nibbles; 0x29 is R/S.
};
struct Example {
  char name[24]{};
  std::uint32_t inputs = 0, revision = 1;
  double values[INPUT_COUNT]{}, expected = 0, absolute = 0.000002,
                                relative = 0.000002;
  std::uint16_t max_commands = 256, max_frames = 2048;
  std::uint8_t angle = 1; // 0 degrees, 1 radians, 2 grads (wire values).
  bool has_expected = false;
  std::uint32_t expected_mask = 0, preserve = 0;
  double expected_values[INPUT_COUNT]{};
  ScenarioStep scenario[SCENARIO_STEPS];
  std::uint8_t scenario_count = 0;
  bool public_case = true;
};
struct Result {
  std::uint32_t version = 0, task_revision = 0, test_revision = 0, commands = 0;
  double x = 0;
  std::uint16_t pc = 0;
  Execution status = Execution::NONE;
  bool passed = false;
  double actual[INPUT_COUNT]{}, stage_values[SCENARIO_STEPS]{};
  std::uint32_t mismatch = 0;
  std::uint8_t failed_stage = 255, completed_stages = 0;
};
struct Trace {
  std::uint16_t pc = 0, opcode = 0;
  double x = 0;
};
struct Session {
  std::uint32_t id = 0, task_revision = 1, last_version = 0, event = 0;
  Program program;
  Example tests[TEST_COUNT];
  Result results[TEST_COUNT];
  char task[1025]{}, draft[513]{}, form[1537]{}, reply[1025]{}, plan[385]{},
      feedback[257]{};
  char model[65]{};
  std::uint16_t attempts = 0, attempt_limit = 4;
  std::uint8_t test_count = 0, view = 0, form_kind = 0, form_index = 0;
  Intent intent = Intent::WRITE;
  RunState state = RunState::DRAFT;
  std::uint32_t failed_programs[8]{}, failed_replies[8]{}, best_version = 0;
  std::uint8_t failed_program_count = 0, failed_reply_count = 0, best_score = 0;
  bool planning = true;
};
struct Store {
  void *context = nullptr;
  bool (*read)(void *, const char *, void *, unsigned, unsigned &) = nullptr;
  bool (*write)(void *, const char *, const void *,
                unsigned) = nullptr; // Atomic replacement.
  bool (*exists)(void *, const char *) = nullptr;
  bool (*size)(void *, const char *, unsigned &) = nullptr;
};
void allocation_observer(void (*sample)(void *), void *context);
struct Reply {
  std::uint8_t program[PROGRAM_SIZE]{};
  unsigned size = 0;
  char plan[385]{};
  char question[513]{};
  std::uint8_t patch_mask[(PROGRAM_SIZE + 7) / 8]{};
  bool write = false, patch = false, run = false, trace = false, done = false;
};
bool parse_reply(const char *text, Reply &reply);
bool reply_program(const Program &current, const Reply &reply, Program &out);
unsigned program_text_size(const Program &p);
std::uint32_t program_fingerprint(const Program &p);
bool has_expectations(const Example &e);
std::uint32_t expectation_mask(const Example &e);
double expected_value(const Example &e, unsigned index);
bool format_example(const Example &e, char *out, unsigned capacity,
                    bool compact = false);
void reset_attempt_history(Session &s);
bool valid_program(const Program &p);
bool result_current(const Session &s, unsigned index);
unsigned passed_examples(const Session &s);
bool all_passed(const Session &s);
void invalidate(Session &s);
bool set_task(Session &s, const char *text, bool append);
bool set_example(Session &s, unsigned index, const Example &example);
bool parse_example(const char *text, Example &example);
bool build_prompt(const Session &s, char *out, unsigned capacity,
                  const char *prefix = nullptr);
const char *default_prompt_prefix();
// Deterministic wire codec with length/CRC checks and transactional decode.
unsigned encode_session(const Session &s, std::uint8_t *out, unsigned capacity);
bool decode_session(const std::uint8_t *data, unsigned bytes, Session &out);
bool save_session(Store store, const Session &s);
bool load_session(Store store, std::uint32_t id, Session &s);
bool archive_program(Store store, const Session &s);
bool select_program(Store store, Session &s, std::uint32_t version);
bool append_event(Store store, Session &s, const char *type, const char *text);
bool accept_program(Store store, Session &s, const std::uint8_t *bytes,
                    unsigned count, bool source_import = false);
// Persisted monotonically increasing IDs. floor is the largest existing ID.
bool reserve_session_id(Store store, std::uint32_t floor, std::uint32_t &id);
// The same real microcode core is used on host and Pico. During service()
// the user's live calculator is restored, never the scratch program.
Result execute(const Program &program, const Example &example,
               std::uint32_t task_revision, bool (*service)(void *) = nullptr,
               void *context = nullptr, Trace *trace = nullptr,
               unsigned *trace_count = nullptr);
bool capture_program(Program &p);
bool apply_program(const Program &p); // Stopped classic calculator, bank zero.
bool load_example_inputs(const Example &example);
} // namespace mk61ai
#endif
