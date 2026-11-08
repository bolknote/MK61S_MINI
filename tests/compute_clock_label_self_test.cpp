#include "rust_types.h"
#include "compute_clock_plan.hpp"
#include "settings_menu_model.hpp"
#include "mk8_literal.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <initializer_list>
struct Display {
 bool graphics; unsigned advance;
 bool uiTextActive()const{return graphics;}
 unsigned measureUiText(const char* s)const{return std::strlen(s)*advance;}
 unsigned uiTextWidth()const{return 192;}
} display;
Display& main_lcd(){return display;}
u8 selected;
u32 service(u32 op){assert(op==MK61_SETUP_COMPUTE_CLOCK);return selected|(1U<<16)|(5U<<24);}
#include "compute_clock_label.inc"
int main(){
 for(bool ru:{false,true})for(bool graphics:{false,true})for(unsigned advance:{6U,8U})
  for(selected=0;selected<5;++selected){
   display={graphics,advance};mk61_setup_settings state{};state.value[MK61_SETTING_LANGUAGE]=ru;
   char text[32]{};label(settings_menu::COMPUTE,state,text,sizeof(text));
   const bool offline=selected>=3;
   assert((std::strstr(text,"USB")!=nullptr)==offline);
   if(graphics)assert(display.measureUiText(text)+12U<=display.uiTextWidth());
   else assert(std::strlen(text)<=15); // 16-column LCD includes its cursor.
   char frequency[8];std::snprintf(frequency,sizeof(frequency),"%u",unsigned(compute_clock::high_mhz(compute_clock::Platform::F411,selected)));
   assert(std::strstr(text,frequency));
  }
 std::puts("CPU labels: five frequencies, RU/EN, narrow LCD and large UI font retain offline USB marker PASS");
}
