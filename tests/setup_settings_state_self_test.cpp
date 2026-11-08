#include "loadable_app_services.h"
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
using u8=uint8_t;
using u32=uint32_t;
enum class ProgramMemoryMode:u8 {CLASSIC_105,EXPANDED_112,AUTO};
enum class SpeedMode:u8 {CLASSIC,MAXIMUM};
enum class RandomMode:u8 {MK61,MK61S};
constexpr unsigned PIN_BUZZER=1;
unsigned resets,enabled,saved,refreshed,beeps,muted,random_changes;
bool random_extended;
struct Display {bool graphics=false;bool graphicsMode()const{return graphics;}} display;
Display& main_lcd(){return display;}
void reset_ext_program_state(){++resets;}
void sound_stop(){++muted;}
void sound(unsigned,unsigned,unsigned,unsigned){++beeps;}
namespace core_61 {void enable(){++enabled;}}
namespace entropy_pool {void configure_calculator(bool next){random_extended=next;++random_changes;}}
namespace library_mk61 {
u8 sound_volume_state=10;
bool idle_signal_state=true,russian_language=false,expanded_program=false;
SpeedMode speed_mode_state=SpeedMode::CLASSIC;
ProgramMemoryMode memory_mode=ProgramMemoryMode::AUTO;
RandomMode random_mode_state=RandomMode::MK61;
#if defined(MK61_OLED1602_WS0010)
u8 oled_timeout_state=0;
void set_oled_timeout(u8 next){oled_timeout_state=next;}
#endif
void set_sound_volume(u8 next){sound_volume_state=next;}
void set_idle_signal_state(bool next){idle_signal_state=next;}
void set_speed_mode_state(SpeedMode next){speed_mode_state=next;}
void set_language_state(bool next){russian_language=next;}
void set_random_mode_state(RandomMode next){random_mode_state=next;}
void set_program_memory_state(bool next){expanded_program=next;}
void mark_settings_dirty(){++saved;}
void refresh_menu_text(){++refreshed;}
// Production setters/readers, extracted at test time; only device effects above
// are modeled. Keep menu migration's reset/save behavior under regression.
#include "setup_settings_state.inc"
}
int main() {
  using namespace library_mk61;
  mk61_setup_settings before{},after{};read_settings_snapshot(before);
  assert(!(before.features&MK61_SETTINGS_FONTS));
  display.graphics=true;read_settings_snapshot(after);
  assert(bool(after.features&MK61_SETTINGS_FONTS)==bool(MK61_ENABLE_SETUP));
  assert(bool(after.features&MK61_SETTINGS_RTC)==bool(MK61_ENABLE_SETUP));
  assert(bool(after.features&MK61_SETTINGS_COMPUTE)==bool(MK61_ENABLE_SETUP));
  const u8 limits[]={10,1,1,2,1,1,3};
  for(unsigned setting=0;setting<MK61_SETTING_COUNT;++setting) {
    assert(!apply_setting(setting,limits[setting]+1U));
    assert(!apply_setting(setting,256));
  }
  assert(!apply_setting(MK61_SETTING_COUNT,0) && !apply_setting(UINT32_MAX,0));
  assert(saved==0 && refreshed==0 && beeps==0);
  assert(apply_setting(MK61_SETTING_VOLUME,10) && saved==0 && beeps==0);
  assert(apply_setting(MK61_SETTING_VOLUME,5) && sound_volume_state==5 && beeps==1 && muted==1);
  assert(apply_setting(MK61_SETTING_IDLE_SIGNAL,0) && !idle_signal_state);
  assert(apply_setting(MK61_SETTING_SPEED,1) && unsigned(speed_mode_state)==1);
  assert(apply_setting(MK61_SETTING_LANGUAGE,1) && russian_language);
  assert(apply_setting(MK61_SETTING_RANDOM,1) && random_extended && random_changes==1);
  assert(apply_setting(MK61_SETTING_MEMORY,1) && expanded_program && resets==1 && enabled==1);
  assert(apply_setting(MK61_SETTING_MEMORY,2) && expanded_program && resets==1);
  assert(apply_setting(MK61_SETTING_MEMORY,0) && !expanded_program && resets==2 && enabled==2);
  const unsigned writes=saved;assert(apply_setting(MK61_SETTING_MEMORY,0) && writes==saved);
#if defined(MK61_OLED1602_WS0010)
  assert(apply_setting(MK61_SETTING_OLED,3) && oled_timeout_state==3);
#else
  assert(!apply_setting(MK61_SETTING_OLED,3));
#endif
  assert(saved==refreshed);
  read_settings_snapshot(after);
  assert(after.value[MK61_SETTING_VOLUME]==5 && after.value[MK61_SETTING_LANGUAGE]==1);
  std::puts("SETUP resident state: bounds, no-op saves, audio, RAM mode/reset, entropy, language and optional controls PASS");
}
