#include "keyboard_core.hpp"
#include "keyboard_layout.hpp"

#include <cassert>
#include <cstdio>
#include <vector>

static constexpr i32 KEY_OK = keyboard_layout::ACTIVE.ok;
static constexpr i32 KEY_ESC = keyboard_layout::ACTIVE.esc;
static constexpr i32 KEY_DEGREE = keyboard_layout::ACTIVE.degree;
static constexpr i32 KEY_GRADE = keyboard_layout::ACTIVE.grade;
static constexpr i32 KEY_RADIAN = keyboard_layout::ACTIVE.radian;
static constexpr i32 KEY_ESC_PRESS = KEY_ESC;
enum class key_state { RELEASED = keyboard_core::RELEASE_MASK };
enum class sw { RUN };
static constexpr usize KEY_IN_ROW = keyboard_core::ROW_COUNT;
static constexpr u8 LAST_SCAN_ROW = KEY_IN_ROW - 1;
static constexpr int INPUT = 0;
static const u8 scan_pins[] = {0, 1, 2, 3, 4};
static int cancellations, redraws, ok_calls, timer_stops;
static u32 now, row_started;
static u8 scan_line;
static std::vector<u8> scanned_rows;

void pinMode(u8, int) {}
void activate_scan_line(void) { row_started = now; }
void check_hold_key(void) {}
void lcd_std_display_redraw(void) { ++redraws; }
bool select_m61_angle_unit(i32) { return true; }
void mk61_baseloop_hook(i32) {}
void mk61_menu_hook(i32) {}
static auto input_focus = &mk61_baseloop_hook;
namespace classic_timer {
void synchronize(bool active) { assert(!active); ++timer_stops; }
}
namespace core_61 {
static bool edit_program, running;
bool is_RUN(void) { return running; }
}
void hidden_press_key(sw) { core_61::running = false; }
namespace m61_text {
static bool enabled, suspended, bound;
bool active(void) { return enabled; }
bool calculator_suspended(void) { return suspended; }
void cancel(void) { ++cancellations; enabled = suspended = false; }
bool handle_ok_key(void) {
  ++ok_calls;
  if(!bound) return false;
  suspended = true;
  return true;
}
}
namespace kbd {
using Event = keyboard_core::Event;
static keyboard_core::DeliveryQueue key_fifo;
static keyboard_core::PressEdgeLatch immediate_presses;
static keyboard_core::ExternalKeyState external_keys;
static bool down[keyboard_core::KEY_COUNT];
static struct Row {
  u8 candidate_mask(void) const { return 0; }
} RowArray[KEY_IN_ROW];
static i32 holded_scan_code = -1, hold_quant_counter = -1;
bool is_key_pressed(i32 key) { return down[key]; }
bool take_immediate_press(i32 key) {
  return immediate_presses.take(key) && !key_fifo.suppressed(key);
}
void clear_immediate_presses(void) { immediate_presses.reset(); }
i32 last_key(void) { return key_fifo.peek(); }
i32 get_key(void) { return key_fifo.pop(); }
Event poll_event(void) { return Event(get_key()); }
isize scan(void) {
  if(now == row_started) return -1; // production caller must keep settle time
  scanned_rows.push_back(scan_line);
  scan_line = (scan_line + 1U) % KEY_IN_ROW;
  activate_scan_line();
  return 1;
}
#include "m61_keyboard_surface.inc"
static void press(i32 key) {
  down[key] = true;
  immediate_presses.note(key);
  assert(key_fifo.push(key));
}
static void release(i32 key) {
  down[key] = false;
  assert(key_fifo.push(key | keyboard_core::RELEASE_MASK));
}
}
#include "m61_controls_surface.inc"
namespace viewer {
static constexpr i32 VIEWER_KEY_NONE = -1;
#include "m61_viewer_surface.inc"
}

static void reset(void) {
  m61_text::enabled = false;
  service_m61_controls(); // reset the production function's was_active latch
  kbd::key_fifo.reset();
  for(bool& key : kbd::down) key = false;
  cancellations = redraws = ok_calls = timer_stops = 0;
  m61_text::enabled = m61_text::bound = true;
  m61_text::suspended = core_61::edit_program = false;
  core_61::running = true;
  input_focus = &mk61_baseloop_hook;
  service_m61_controls();
}

int main(void) {
  // Calculator -> manual -> ESC -> calculator: use the real dispatcher,
  // Markdown input consumer, handoff and immediate-edge latch together.
  reset();
  kbd::press(KEY_OK);
  service_m61_controls();
  assert(ok_calls == 1 && timer_stops == 1 && m61_text::suspended);
  assert(viewer::scan_key() < 0); // opening OK must not close the manual
  kbd::release(KEY_OK);
  kbd::press(KEY_ESC);
  assert(viewer::scan_key() == KEY_ESC);
  service_m61_controls();
  assert(cancellations == 0 && m61_text::enabled && core_61::running);
  kbd::release(KEY_ESC);
  m61_text::suspended = false;
  service_m61_controls();
  assert(cancellations == 0);
  kbd::press(KEY_ESC); // a NEW press on the calculator still cancels normally
  service_m61_controls();
  assert(cancellations == 1 && !core_61::running);

  // No capture in menus, PRG, or when the script has not bound OK.
  for(int mode = 0; mode < 3; ++mode) {
    reset();
    if(mode == 0) input_focus = &mk61_menu_hook;
    if(mode == 1) core_61::edit_program = true;
    if(mode == 2) m61_text::bound = false;
    kbd::press(KEY_OK);
    service_m61_controls();
    assert(kbd::last_key() == KEY_OK && timer_stops == 0);
    assert(ok_calls == (mode == 2 ? 1 : 0));
  }
  reset();
  m61_text::suspended = true; // timed trap still accepts OK before FIFO drain
  kbd::press(KEY_OK);
  service_m61_controls();
  assert(ok_calls == 1 && kbd::last_key() < 0);

  // Poll both physical control rows, including Classic's separate OK row.
  scanned_rows.clear();
  scan_line = 0;
  now = row_started = 0;
  assert(kbd::scan_m61_controls() == -1);
  assert(kbd::scan_m61_controls() == -1);
  for(now = 1; now <= 20; ++now) {
    assert(kbd::scan_m61_controls() == 1);
    assert(kbd::scan_m61_controls() == -1);
  }
  bool saw_ok_row = false, saw_escape_row = false;
  for(u8 row : scanned_rows) {
    assert(row == LAST_SCAN_ROW || row == KEY_OK % KEY_IN_ROW);
    saw_ok_row |= row == KEY_OK % KEY_IN_ROW;
    saw_escape_row |= row == KEY_ESC % KEY_IN_ROW;
  }
  assert(saw_ok_row && saw_escape_row);
  std::puts("m61 controls: OK focus, viewer ESC handoff, physical rows: ok");
}
