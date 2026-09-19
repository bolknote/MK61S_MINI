#include "../code/rust_types.h"

#include <assert.h>
#include <stdio.h>

#define PRESS 1
#define MINI 0
#define EXT_RUN 0
#define dbgln(...) do {} while(false)

static constexpr int PIN_BUZZER = 1;
static u32 fake_millis = 1000;
static int sound_count;
static int delivered_key = -1;
static int delivered_key_count;
static int full_scan_count;
static int control_scan_count;
static int queued_key = -1;
static int key_on_full_scan = -1;
static bool cancel_during_service;
static int service_count;
t_time_ms runtime_ms;

u32 millis(void) { return fake_millis; }
void sound(int, usize, usize, u8) { sound_count++; }

struct FakeLabel {
  void enable(void) {}
  void disable(void) {}
} MnemoLabel;

struct FakeDisassembler {
  void disable(const char* = nullptr) {}
} disassembler;

struct FakeConfig {
  bool disassm;
} config = {false};

namespace library_mk61 {
static bool maximum;
bool speed_is_max(void) { return maximum; }
bool speed_is_classic(void) { return false; }
u8 sound_volume(void) { return 10; }
}

namespace cfg {
static constexpr usize MAXIMUM_MK61_BATCH_STEPS = 4;
}

namespace classic_timer {
void synchronize(bool) {}
u32 configured_period_us(void) { return 0; }
}

namespace runtime_safety {
bool valid_extended_command(u8, i32) { return false; }
}

namespace core_61 {
enum class StepAction { KEEP_RUNNING, STOP };
static bool running;
static bool boundary_yielded;
static bool displayed;
static StepAction step_action;
static int step_count;

bool is_RUN(void) { return running; }
bool is_CALC(void) { return !running; }
bool is_displayed(void) { return displayed; }
void step(void) {
  step_count++;
  if(step_action == StepAction::STOP) running = false;
}
i32 get_IP(void) { return 0; }
i32 program_steps(void) { return 105; }
i32 get_code(i32) { return 0; }
i32 get_ring_address(i32 address) { return address; }
bool program_boundary_yielded(void) { return boundary_yielded; }
}

namespace m61_text {
static bool script_active;
static bool suspended;
bool active(void) { return script_active; }
bool calculator_suspended(void) { return suspended; }
}

namespace kbd {
bool scan_m61_controls(void) {
  control_scan_count++;
  return false;
}
void scan(void) {
  full_scan_count++;
  if(key_on_full_scan >= 0) queued_key = key_on_full_scan;
}
i32 get_key(i32) {
  const i32 result = queued_key;
  queued_key = -1;
  return result;
}
}

void key_press_handler(i32 keycode) {
  delivered_key = keycode;
  delivered_key_count++;
}

void service_m61_controls(void) {
  service_count++;
  if(cancel_during_service) m61_text::script_active = false;
}

static u8 ext61_program[105];
static constexpr i32 COUNT_EXT_COMMAND = 7;
static struct {
  u8 code;
  t_time_ms time;
} ext_command;

#include "../code/automate.hpp"

static void reset_fakes(void) {
  fake_millis = 1000;
  sound_count = 0;
  delivered_key = -1;
  delivered_key_count = 0;
  full_scan_count = 0;
  control_scan_count = 0;
  queued_key = -1;
  key_on_full_scan = -1;
  cancel_during_service = false;
  service_count = 0;
  runtime_ms = 0;
  library_mk61::maximum = false;
  core_61::running = true;
  core_61::boundary_yielded = false;
  core_61::displayed = true;
  core_61::step_action = core_61::StepAction::KEEP_RUNNING;
  core_61::step_count = 0;
  m61_text::script_active = true;
  m61_text::suspended = false;
  mk61_sending_keycode = MK61_REQUEST_BASE_LOOP;
}

static void test_m61_normal_stop_keeps_stop_signal(void) {
  reset_fakes();
  core_61::step_action = core_61::StepAction::STOP;

  run_program_steps();

  assert(core_61::step_count == 1);
  assert(full_scan_count == 1);
  assert(control_scan_count == 0);
  assert(service_count == 1);
  assert(sound_count == 1);
}

static void test_m61_run_delivers_regular_calculator_key(void) {
  reset_fakes();
  key_on_full_scan = 42;

  run_program_steps();

  assert(full_scan_count == 1);
  assert(control_scan_count == 0);
  assert(delivered_key_count == 1);
  assert(delivered_key == 42);
  assert(sound_count == 0);
}

static void test_suspended_trap_only_scans_controls(void) {
  reset_fakes();
  m61_text::suspended = true;
  queued_key = 43;

  scan_m61_runtime_keyboard();
  service_run_keypress();

  assert(full_scan_count == 0);
  assert(control_scan_count == 1);
  assert(delivered_key_count == 0);
  assert(queued_key == 43);
}

static void test_m61_cancel_stays_silent(void) {
  reset_fakes();
  cancel_during_service = true;

  run_program_steps();

  assert(!m61_text::script_active);
  assert(sound_count == 0);
  assert(delivered_key_count == 0);
}

static void test_maximum_mode_runs_the_fast_batch(void) {
  reset_fakes();
  library_mk61::maximum = true;
  m61_text::script_active = false;

  run_program_steps();

  assert(core_61::step_count == (int) cfg::MAXIMUM_MK61_BATCH_STEPS);
}

static void test_every_run_updates_last_runtime(void) {
  reset_fakes();
  event_start_prg_mk61();
  assert(runtime_ms == 1000U);

  fake_millis = 1423;
  core_61::step_action = core_61::StepAction::STOP;
  run_program_steps();
  assert(runtime_ms == 423U);

  core_61::running = true;
  core_61::step_action = core_61::StepAction::STOP;
  fake_millis = 2000;
  event_start_prg_mk61();
  fake_millis = 2017;
  run_program_steps();
  assert(runtime_ms == 17U);
}

static void test_runtime_elapsed_time_wraps_safely(void) {
  reset_fakes();
  fake_millis = 0xFFFFFFF0U;
  event_start_prg_mk61();
  fake_millis = 0x00000010U;
  event_stop_in_prg_mk61();
  assert(runtime_ms == 32U);
}

int main(void) {
  test_m61_normal_stop_keeps_stop_signal();
  test_m61_run_delivers_regular_calculator_key();
  test_suspended_trap_only_scans_controls();
  test_m61_cancel_stays_silent();
  test_maximum_mode_runs_the_fast_batch();
  test_every_run_updates_last_runtime();
  test_runtime_elapsed_time_wraps_safely();
  printf("automate_self_test: ok\n");
  return 0;
}
