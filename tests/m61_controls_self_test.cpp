#include "keyboard_core.hpp"
#include "keyboard_layout.hpp"
#include "m61_keys.hpp"
#include <cassert>
#include <cstdio>
#include <vector>
static constexpr i32 KEY_OK=keyboard_layout::ACTIVE.ok, KEY_ESC=keyboard_layout::ACTIVE.esc,
    KEY_DEGREE=keyboard_layout::ACTIVE.degree, KEY_GRADE=keyboard_layout::ACTIVE.grade,
    KEY_RADIAN=keyboard_layout::ACTIVE.radian, KEY_ESC_PRESS=KEY_ESC,
    KEY_CX=keyboard_layout::ACTIVE.cx, KEY_USER_PRESS=keyboard_layout::ACTIVE.user;
enum class key_state { RELEASED=keyboard_core::RELEASE_MASK };
enum class sw { RUN };
static constexpr usize KEY_IN_ROW=keyboard_core::ROW_COUNT;
static constexpr u8 LAST_SCAN_ROW=KEY_IN_ROW-1;
static constexpr int INPUT=0;
static const u8 scan_pins[]={0,1,2,3,4};
static int cancellations,redraws,timer_stops,angle_calls,handler_clears,display_restores;
static bool lcd_hooked;
static u32 now,row_started;
static u8 scan_line;
static std::vector<u8> scanned_rows;
static std::vector<unsigned> captured;
namespace stm32f4_gpio { void configure(u8,int) {} }
void activate_scan_line() { row_started=now; }
void check_hold_key() {}
void lcd_std_display_redraw() { ++redraws; }
void lcd_stack_output() {}
template<class... T> void debug_sink(const T&...) {}
#define dbgln(module, ...) debug_sink(__VA_ARGS__)
bool select_m61_angle_unit(i32) { ++angle_calls;return true; }
void mk61_baseloop_hook(i32) {}
void mk61_menu_hook(i32) {}
static auto input_focus=&mk61_baseloop_hook;
namespace classic_timer { void synchronize(bool active) { assert(!active);++timer_stops; } }
namespace core_61 {
static bool edit_program,running;
bool is_RUN() { return running; }
bool restore_standard_display() { ++display_restores; return true; }
}
void hidden_press_key(sw) { core_61::running=false; }
namespace m61_text {
static bool enabled,suspended,modal,bound[m61_keys::COUNT],timer_bound,opcode_bound,trap_bound;
bool active() { return enabled; }
bool calculator_suspended() { return suspended; }
bool keyboard_available() { return enabled && !modal; }
void cancel() { ++cancellations;enabled=suspended=false; }
bool key_bindings_active() { for(bool v:bound)if(v)return true;return false; }
bool clear_bindings_and_traps() {
  ++handler_clears;
  const bool any=key_bindings_active() || timer_bound || opcode_bound || trap_bound;
  for(bool& v:bound)v=false;
  timer_bound=opcode_bound=trap_bound=false;
  return any;
}
bool captures_key(u8 key) { return enabled && !modal && m61_keys::valid(key) && bound[key]; }
bool handle_key_event(u8 key,bool down) {
  if(!captures_key(key))return false;
  captured.push_back(key | (down?0:0x40));suspended=true;return true;
}
}
namespace kbd {
using Event=keyboard_core::Event;
static keyboard_core::DeliveryQueue key_fifo;
static keyboard_core::PressEdgeLatch immediate_presses;
static keyboard_core::ExternalKeyState external_keys;
static bool down[keyboard_core::KEY_COUNT];
static struct Row { u8 candidate_mask()const{return 0;} } RowArray[KEY_IN_ROW];
static i32 holded_scan_code=-1,hold_quant_counter=-1;
bool is_key_pressed(i32 key) { return down[key]; }
bool take_immediate_press(i32 key) { return immediate_presses.take(key)&&!key_fifo.suppressed(key); }
void clear_immediate_presses() { immediate_presses.reset(); }
i32 last_key() { return key_fifo.peek(); }
i32 get_key() { return key_fifo.pop(); }
Event poll_event() { return Event(get_key()); }
void clear_hold_key() { holded_scan_code=hold_quant_counter=-1; }
isize scan() {
  if(now==row_started)return -1;
  scanned_rows.push_back(scan_line);scan_line=(scan_line+1U)%KEY_IN_ROW;
  activate_scan_line();return 1;
}
#include "m61_keyboard_surface.inc"
static void press(i32 key) { down[key]=true;immediate_presses.note(key);assert(key_fifo.push(key)); }
static void release(i32 key) { down[key]=false;assert(key_fifo.push(key|keyboard_core::RELEASE_MASK)); }
}
#include "m61_controls_surface.inc"
#include "m61_hold_surface.inc"
namespace viewer {
static constexpr i32 VIEWER_KEY_NONE=-1;
#include "m61_viewer_surface.inc"
}
static void reset() {
  m61_text::enabled=false;service_m61_controls();kbd::key_fifo.reset();
  for(bool& v:kbd::down)v=false;
  for(bool& v:m61_text::bound)v=false;
  cancellations=redraws=timer_stops=angle_calls=handler_clears=display_restores=0;captured.clear();
  m61_text::timer_bound=m61_text::opcode_bound=m61_text::trap_bound=false;
  m61_text::enabled=true;m61_text::suspended=m61_text::modal=false;
  core_61::edit_program=false;core_61::running=true;
  input_focus=&mk61_baseloop_hook;service_m61_controls();
}
int main() {
  bool seen[m61_keys::COUNT]={};
  for(i32 raw=0;raw<40;++raw) {
    reset();const i32 key=m61_keys::logical_key(keyboard_layout::ACTIVE,raw);
    assert(key>=0 && !seen[key]);seen[key]=true;
    assert(m61_keys::scan_code(keyboard_layout::ACTIVE,key)==raw);
    m61_text::bound[key]=true;kbd::press(raw);service_m61_controls();
    kbd::release(raw);service_m61_controls();
    assert((captured==std::vector<unsigned>{(unsigned)key,(unsigned)key|0x40}));
    assert(kbd::last_key()<0 && !cancellations && !angle_calls && core_61::running);
  }
  reset();kbd::press(KEY_ESC);service_m61_controls();
  assert(cancellations==1 && !core_61::running);
  for(i32 angle:{KEY_DEGREE,KEY_GRADE,KEY_RADIAN}) {
    reset();kbd::press(angle);service_m61_controls();assert(angle_calls>0 && !cancellations);
  }
  reset();kbd::press(keyboard_layout::ACTIVE.digit[4]);service_m61_controls();
  assert(captured.empty() && kbd::last_key()==keyboard_layout::ACTIVE.digit[4]);
  for(int mode=0;mode<2;++mode) {
    reset();m61_text::bound[m61_keys::OK]=true;
    if(mode==0)input_focus=&mk61_menu_hook;else core_61::edit_program=true;
    kbd::press(KEY_OK);service_m61_controls();assert(captured.empty() && kbd::last_key()==KEY_OK);
  }
  reset();m61_text::bound[m61_keys::OK]=true;
  kbd::press(KEY_OK);service_m61_controls();m61_text::modal=true;
  assert(viewer::scan_key()<0);
  kbd::release(KEY_OK);kbd::press(KEY_ESC);
  assert(viewer::scan_key()<0);service_m61_controls();assert(!cancellations);
  assert(viewer::scan_key()==KEY_ESC);service_m61_controls();assert(!cancellations);
  kbd::release(KEY_ESC);m61_text::modal=m61_text::suspended=false;
  service_m61_controls();kbd::press(KEY_ESC);service_m61_controls();assert(cancellations==1);
  scanned_rows.clear();scan_line=0;now=row_started=0;
  assert(kbd::scan_m61_controls()==-1);
  for(now=1;now<=20;++now)assert(kbd::scan_m61_controls()==1);
  bool ok_row=false,escape_row=false,cx_row=false;
  for(u8 row:scanned_rows) {
    assert(row==LAST_SCAN_ROW || row==KEY_OK%KEY_IN_ROW || row==KEY_CX%KEY_IN_ROW);
    ok_row|=row==KEY_OK%KEY_IN_ROW;escape_row|=row==LAST_SCAN_ROW;
    cx_row|=row==KEY_CX%KEY_IN_ROW;
  }
  assert(ok_row && escape_row && cx_row);
  for(bool keys : {false,true}) {
    reset();m61_text::timer_bound=m61_text::opcode_bound=m61_text::trap_bound=true;
    m61_text::bound[m61_keys::logical_key(keyboard_layout::ACTIVE,KEY_CX)]=keys;
    event_hold_key(KEY_CX,0);
    assert(handler_clears==1 && display_restores==1 && redraws==1);
    assert(!m61_text::timer_bound && !m61_text::opcode_bound && !m61_text::trap_bound);
    assert(!m61_text::key_bindings_active() && cancellations==int(keys));
    assert(core_61::running==!keys && kbd::holded_scan_code==-1);
    event_hold_key(KEY_CX,1);assert(handler_clears==1);
  }
  std::puts("m61 controls: 40 keys, DOWN/UP, focus, viewer and long Cx clearing all bind kinds: ok");
}
