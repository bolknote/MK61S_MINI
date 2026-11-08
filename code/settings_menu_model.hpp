#ifndef MK61_SETTINGS_MENU_MODEL_HPP
#define MK61_SETTINGS_MENU_MODEL_HPP
#include "loadable_app_services.h"
#include "menu_model.hpp"
namespace settings_menu {
enum Item : uint8_t {
  VOLUME=MK61_SETTING_VOLUME, IDLE=MK61_SETTING_IDLE_SIGNAL,
  SPEED=MK61_SETTING_SPEED, MEMORY=MK61_SETTING_MEMORY,
  RANDOM=MK61_SETTING_RANDOM, LANGUAGE=MK61_SETTING_LANGUAGE,
  OLED=MK61_SETTING_OLED, COMPUTE=MK61_SETTING_COUNT, DATE_TIME, RTC_CORRECTION, FONTS, END
};
constexpr Item ORDER[]={VOLUME,IDLE,SPEED,COMPUTE,MEMORY,RANDOM,DATE_TIME,RTC_CORRECTION,LANGUAGE,OLED,FONTS};
inline bool visible(Item item,uint8_t features) {
  return item==COMPUTE ? features&MK61_SETTINGS_COMPUTE :
      item==DATE_TIME || item==RTC_CORRECTION ? features&MK61_SETTINGS_RTC :
      item==OLED ? features&MK61_SETTINGS_OLED :
      item==FONTS ? features&MK61_SETTINGS_FONTS : true;
}
inline Item at(unsigned index,uint8_t features) {
  for(auto item:ORDER)if(visible(item,features)){if(!index--)return item;}
  return END;
}
inline unsigned count(uint8_t features) {
  unsigned n=0;for(auto item:ORDER)if(visible(item,features))++n;return n;
}
// OK cycles volume; shifted arrows clamp it. Other scalar choices cycle.
inline uint8_t adjusted(Item item,uint8_t value,int direction,bool cycle) {
  if(item==VOLUME) return cycle ? (value>=10?0:value+1) :
      direction>0 ? (value<10?value+1:10) : (value?value-1:0);
  const unsigned count=item==MEMORY?3:item==OLED?4:2;
  return uint8_t((value+(direction<0?count-1:1))%count);
}
}
#endif
