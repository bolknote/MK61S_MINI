#include "settings_menu_model.hpp"
#include <cassert>
#include <cstdio>
#include <set>
using namespace settings_menu;
int main() {
  for(unsigned features=0;features<16;++features) {
    std::set<Item> seen;
    for(unsigned i=0;i<count(features);++i)assert(seen.insert(at(i,features)).second);
    assert(at(count(features),features)==END);
    for(Item item:{VOLUME,IDLE,SPEED,MEMORY,RANDOM,LANGUAGE})assert(seen.count(item));
    assert(bool(seen.count(COMPUTE))==bool(features&MK61_SETTINGS_COMPUTE));
    assert(bool(seen.count(FONTS))==bool(features&MK61_SETTINGS_FONTS));
    assert(bool(seen.count(OLED))==bool(features&MK61_SETTINGS_OLED));
    assert(bool(seen.count(DATE_TIME))==bool(features&MK61_SETTINGS_RTC));
    assert(bool(seen.count(RTC_CORRECTION))==bool(features&MK61_SETTINGS_RTC));
    assert(at(0,features)==VOLUME && at(1,features)==IDLE && at(2,features)==SPEED);
  }
  assert(count(0)==6 && count(15)==11);
  assert(adjusted(VOLUME,0,-1,false)==0 && adjusted(VOLUME,10,1,false)==10);
  assert(adjusted(VOLUME,10,1,true)==0 && adjusted(VOLUME,0,1,true)==1);
  for(unsigned value=0;value<3;++value)
    assert(adjusted(MEMORY,adjusted(MEMORY,value,1,false),-1,false)==value);
  assert(adjusted(OLED,3,1,false)==0 && adjusted(OLED,0,-1,false)==3);
  for(Item item:{IDLE,SPEED,RANDOM,LANGUAGE}) {
    assert(adjusted(item,0,1,true)==1 && adjusted(item,1,-1,false)==0);
  }
  std::puts("SETUP menu: six core controls, optional RTC/OLED/fonts/compute, stable order, volume limits and cyclic choices PASS");
}
