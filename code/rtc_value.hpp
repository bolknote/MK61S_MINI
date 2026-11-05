#ifndef MK61_RTC_VALUE_HPP
#define MK61_RTC_VALUE_HPP
#include "loadable_app_services.h"
namespace rtc_value {
// Local civil RTC values. The day number has the Unix epoch, without adding
// a timezone conversion to a clock that deliberately stores local time.
constexpr uint32_t get(const mk61_setup_datetime& value,bool days) {
  if(!days) return value.hour*3600U+value.minute*60U+value.second;
  int year=int(value.year),month=int(value.month);year-=month<=2;
  const int era=(year>=0?year:year-399)/400,yy=year-era*400;
  const unsigned doy=(153U*unsigned(month+(month>2?-3:9))+2)/5+value.day-1;
  return uint32_t(era*146097+yy*365+yy/4-yy/100+int(doy)-719468);
}
static_assert(get({1970,1,1,0,0,0},true)==0 && get({2000,1,1,0,0,0},true)==10957,"RTC epoch");
static_assert(get({2000,3,1,0,0,0},true)-get({2000,2,1,0,0,0},true)==29,"RTC leap day");
}
#endif
