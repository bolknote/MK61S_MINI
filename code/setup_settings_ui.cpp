#include "config.h"
#if !MK61_SETUP_IS_LOADABLE || defined(MK61_BUILD_SETUP_MODULE)
#include "setup_ui.hpp"
#include "setup_service.hpp"
#include "settings_menu_model.hpp"
#include "compute_clock_plan.hpp"
#include "menu.hpp"
#include "cross_hal.h"
#include "lcd_ru.hpp"
#if defined(MK61_BUILD_PORTABLE_SYSTEM)
#include "setup_compat.hpp"
#endif
#include <stdio.h>
extern void idle_main_process();
namespace setup_ui {
namespace {
void label(settings_menu::Item item,const mk61_setup_settings& s,char* out,usize capacity) {
  using namespace settings_menu;
  const bool ru=s.value[MK61_SETTING_LANGUAGE];
  const u8 value=unsigned(item)<MK61_SETTING_COUNT?s.value[item]:0;
  const char* text="";
  switch(item) {
    case VOLUME:snprintf(out,capacity,ru?M8("Громкость %u"):"Volume %u",value);return;
    case IDLE:text=ru?(value?M8("5 мин звук вкл"):M8("5 мин звук выкл")):(value?"5 min beep ON":"5 min beep OFF");break;
    case SPEED:text=ru?(value?M8("Скорость макс"):M8("Скорость норма")):(value?"Speed MAXIMUM":"Speed CLASSIC");break;
    case COMPUTE: {
      const u32 clock=service(MK61_SETUP_COMPUTE_CLOCK);
      const auto platform=(compute_clock::Platform)((clock>>16)&0xFF);
      const unsigned mhz=compute_clock::high_mhz(platform,(u8)clock);
      const bool offline=!compute_clock::usb_available(platform,(u8)clock);
      const char* format=ru ? (main_lcd().uiTextActive()
          ? M8("Частота CPU %u МГц%s") : (offline?M8("CPU%u МГц%s"):M8("CPU %u МГц%s"))) :
          (main_lcd().uiTextActive()?"CPU frequency %u MHz%s":offline?"CPU%u MHz%s":"CPU %u MHz%s");
      const char* suffix=!offline?"":main_lcd().uiTextActive()?
          (ru?M8(" без USB"):" no USB"):" USB-";
      snprintf(out,capacity,format,mhz,suffix);
      if(main_lcd().uiTextActive() && main_lcd().measureUiText(out)+12U>main_lcd().uiTextWidth())
        snprintf(out,capacity,ru?M8("CPU %u МГц%s"):"CPU %u MHz%s",mhz,suffix);
      return;
    }
    case MEMORY:text=ru?(value==2?M8("Память АВТО"):value?M8("Память 112ШГ+ПF"):M8("Память 105ШГ")):
        (value==2?"Memory Auto":value?"Memory 112+F":"Memory 105");break;
    case RANDOM:text=ru?(value?M8("К СЧ MK61s"):M8("К СЧ MK61")):(value?"Random MK61s":"Random MK61");break;
    case LANGUAGE:text=ru?M8("Язык рус"):"Language EN";break;
    case DATE_TIME:text=ru?M8("Дата и время"):"Date & time";break;
    case RTC_CORRECTION:text=ru?M8("Поправка RTC"):"RTC correction";break;
    case FONTS:text=ru?M8("Шрифты..."):"Fonts...";break;
    case OLED: {
      const unsigned minutes=value==1?5:value==2?15:value==3?30:0;
      if(minutes){snprintf(out,capacity,ru?M8("OLED сон %uмин"):"OLED sleep %um",minutes);return;}
      text=ru?M8("OLED сон выкл"):"OLED sleep OFF";break;
    }
    default:break;
  }
  snprintf(out,capacity,"%s",text);
}
void draw(const mk61_setup_settings& s,unsigned selected,unsigned count) {
  MK61DisplayUpdate update(main_lcd());
  main_lcd().beginUiText();
  const unsigned rows=main_lcd().rows();
  const unsigned top=menu_model::firstVisible(selected,count,rows);
  if(main_lcd().uiTextActive()) {
    for(unsigned row=0;row<rows;++row) {
      char text[32]{};
      if(top+row<count)label(settings_menu::at(top+row,s.features),s,text,sizeof(text));
      main_lcd().printUiLine(row,text,top+row==selected?'>':' ');
    }
  } else {
    char text[lcd_display::RUNTIME_MAX_ROWS][32]{};
    const char* lines[lcd_display::RUNTIME_MAX_ROWS];
    for(unsigned row=0;row<rows;++row) {
      text[row][0]=top+row==selected?'>':' ';
      if(top+row<count)label(settings_menu::at(top+row,s.features),s,text[row]+1,sizeof(text[row])-1);
      lines[row]=text[row];
    }
    // One CGRAM font for the complete character-display window.
    lcd_ru::print_window(lines,rows);
  }
}
}
static bool settings_action(settings_menu::Item item,const mk61_setup_settings& state,i32 key) {
  if(key!=KEY_OK_PRESS && key!=KEY_SHG_LEFT_PRESS && key!=KEY_SHG_RIGHT_PRESS)return false;
  if(unsigned(item)<MK61_SETTING_COUNT) {
    return service(MK61_SETUP_SETTING_WRITE,item,
        settings_menu::adjusted(item,state.value[item],key==KEY_SHG_LEFT_PRESS?-1:1,key==KEY_OK_PRESS))!=0;
  }
  if(item==settings_menu::COMPUTE) {
    const u32 clock=service(MK61_SETUP_COMPUTE_CLOCK);
    const auto platform=(compute_clock::Platform)((clock>>16)&0xFF);
    return service(MK61_SETUP_COMPUTE_CLOCK,1,compute_clock::step(
        platform,(u8)clock,key==KEY_SHG_LEFT_PRESS?-1:1))!=0;
  }
  if(key==KEY_OK_PRESS) {
    switch(item) {
      case settings_menu::DATE_TIME:setup_ui::date_time();return true;
      case settings_menu::RTC_CORRECTION:setup_ui::calibration();return true;
      case settings_menu::FONTS:setup_ui::font();return true;
      default:return false;
    }
  }
  if(item==settings_menu::FONTS && !(service(MK61_SETUP_FEATURES)&MK61_SETUP_FEATURE_UI_FONT)) {
    setup_ui::step_font(key==KEY_SHG_LEFT_PRESS?-1:1);return true;
  }
  return false;
}
bool settings() {
#if defined(MK61_BUILD_PORTABLE_SYSTEM)
  struct TextScope {
    bool was_ui=main_lcd().uiTextActive();
    ~TextScope(){if(!was_ui)main_lcd().endUiText();}
  } text_scope;
#else
  MK61DisplayTextScope text_scope(main_lcd());
#endif
  main_lcd().clear();
  unsigned selected=0;
  for(;;) {
    mk61_setup_settings state{};
    if(!service(MK61_SETUP_SETTINGS_READ,0,0,&state))return action::MENU_BACK;
    const unsigned count=settings_menu::count(state.features);
    if(selected>=count)selected=count-1;
    draw(state,selected,count);
    const u32 revision=main_lcd().displayModeRevision();
    i32 key;
    do {idle_main_process();key=kbd::poll_event().code();}
      while((key<0 || key>=(i32)key_state::RELEASED) && revision==main_lcd().displayModeRevision());
    if(revision!=main_lcd().displayModeRevision())continue;
    if(key==KEY_ESC_PRESS){kbd::handoff(kbd::Event(key));lcd_ru::restore_default_font();return action::MENU_BACK;}
    if(key==KEY_LEFT_PRESS || key==KEY_RIGHT_PRESS) {
      selected=menu_model::step(selected,count,key==KEY_LEFT_PRESS?-1:1);continue;
    }
    if(key!=KEY_OK_PRESS && key!=KEY_SHG_LEFT_PRESS && key!=KEY_SHG_RIGHT_PRESS)continue;
    const auto item=settings_menu::at(selected,state.features);
    const bool dialog=unsigned(item)>=MK61_SETTING_COUNT && key==KEY_OK_PRESS;
    if(dialog)kbd::handoff(kbd::Event(key));
    if(settings_action(item,state,key) && dialog)main_lcd().clear();
  }
}
}
#endif
