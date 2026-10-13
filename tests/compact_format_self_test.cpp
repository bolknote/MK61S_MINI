#include "compact_format.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <cstdint>
#include <climits>
#include <iostream>
static unsigned cases;
template<typename... Args> void check(const char* format,Args... args) {
  for(unsigned cap: {0U,1U,2U,7U,16U,64U,128U}) {
    char actual[160],expected[160];std::memset(actual,0x5A,sizeof(actual));std::memset(expected,0x5A,sizeof(expected));
    const int a=compact_format::snprintf(actual+8,cap,format,args...);
    const int b=std::snprintf(expected+8,cap,format,args...);
    if(a!=b || std::memcmp(actual,expected,sizeof(actual))) { std::cerr<<format<<" cap="<<cap<<" got "<<a<<" expected "<<b<<"\n";std::abort(); }
    ++cases;
  }
}
int main() {
  for(const char* flags: {"","-","+"," ","0","#","-0","+0","#0"})
    for(unsigned width: {0U,1U,8U,32U}) for(int precision: {-1,0,1,6,12}) {
      char format[32];
      if(precision<0)std::snprintf(format,sizeof(format),"%%%s%ud",flags,width);
      else std::snprintf(format,sizeof(format),"%%%s%u.%dd",flags,width,precision);
      for(int value:{INT_MIN,-1000,-1,0,1,1000,INT_MAX})check(format,value);
      if(precision<0)std::snprintf(format,sizeof(format),"%%%s%uX",flags,width);
      else std::snprintf(format,sizeof(format),"%%%s%u.%dX",flags,width,precision);
      for(unsigned value:{0U,1U,0x87654321U,UINT_MAX})check(format,value);
    }
  for(int w:{-32,-1,0,1,32})for(int p:{-1,0,1,5,32}) {check("[%*.*s]",w,p,"abcdefghijklmnopqrstuvwxyz");check("[%0*.*u]",w,p,123U);}
  check("%ld:%u %.12s %c %%",-2147483647L,42U,"abcdefghijklmno",'x');
  check("%hd %hu",int(-32768),unsigned(65535));
  for(unsigned value:{0U,1U,31U,4015209614U,UINT_MAX})
    for(int precision:{0,1,4,12})check("[%#07.*o]",precision,value);
  char out[20];assert(compact_format::snprintf(out,sizeof(out),"%#o",0U)==2 && !std::strcmp(out,"00"));
  assert(compact_format::snprintf(nullptr,0,"[%p]",nullptr)==3);
  int n=0;assert(compact_format::snprintf(out,sizeof(out),"abc%nXYZ",&n)==6 && n==3);
  assert(compact_format::snprintf(out,sizeof(out),"%2147483648u",1U)==-1);
  std::cout<<"Compact formatter: "<<cases<<" differential bounded-output cases PASS\n";
}
