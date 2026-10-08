#include "../examples/portable-apps/SHEET/phone_input.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>

using namespace phone_input;
int main() {
  char text[96]={}; uint16_t length=0, cursor=0; State state={};
  const uint8_t counts[]={4,5,4,4,4,4,4,4};
  for(uint8_t digit=2;digit<=9;++digit) for(uint8_t index=0;index<counts[digit-2];++index) {
    finish(state);
    for(uint8_t press=0;press<=index;++press) assert(tap(state,text,length,cursor,sizeof(text),digit,100));
  }
  assert(length==33 && strcmp(text,M8("АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"))==0);
  state={}; state.lowercase=true; length=cursor=0; text[0]=0;
  for(uint8_t digit=2;digit<=9;++digit) for(uint8_t index=0;index<counts[digit-2];++index) {
    finish(state);
    for(uint8_t press=0;press<=index;++press) assert(tap(state,text,length,cursor,sizeof(text),digit,100));
  }
  assert(strcmp(text,M8("абвгдеёжзийклмнопрстуфхцчшщъыьэюя"))==0);

  // Repeated taps wrap within one glyph; confirmation starts the next glyph.
  state={}; length=cursor=0; text[0]=0;
  for(int i=0;i<5;++i) assert(tap(state,text,length,cursor,sizeof(text),2,100));
  assert(length==1 && strcmp(text,M8("А"))==0);
  finish(state); assert(tap(state,text,length,cursor,sizeof(text),2,100));
  assert(strcmp(text,M8("АА"))==0);
  assert(!expire(state,1299)); assert(expire(state,1300));
  assert(tap(state,text,length,cursor,sizeof(text),2,1300));
  assert(strcmp(text,M8("ААА"))==0);
  assert(tap(state,text,length,cursor,sizeof(text),0,1301));
  assert(!state.key && strcmp(text,M8("ААА "))==0);

  // The deadline stays correct when the millisecond counter wraps.
  state={}; length=cursor=0; text[0]=0;
  assert(tap(state,text,length,cursor,sizeof(text),3,UINT32_MAX-20));
  assert(!expire(state,1178)); assert(expire(state,1179));
  assert(tap(state,text,length,cursor,sizeof(text),3,1179));
  assert(strcmp(text,M8("ДД"))==0);

  state={}; state.layout=LATIN; length=cursor=0; text[0]=0;
  assert(tap(state,text,length,cursor,sizeof(text),2,0));
  assert(tap(state,text,length,cursor,sizeof(text),2,1));
  assert(strcmp(text,"B")==0);
  finish(state); state.lowercase=true;
  for(int i=0;i<4;++i) assert(tap(state,text,length,cursor,sizeof(text),7,10));
  assert(strcmp(text,"Bs")==0);
  finish(state); state.layout=DIGITS;
  for(uint8_t digit=0;digit<=9;++digit) assert(tap(state,text,length,cursor,sizeof(text),digit,20));
  assert(strcmp(text,"Bs0123456789")==0);

  // Editing in the middle moves the existing tail and cycles only the insertion.
  state={}; strcpy(text,"XY"); length=2; cursor=1;
  assert(tap(state,text,length,cursor,sizeof(text),3,0));
  assert(tap(state,text,length,cursor,sizeof(text),3,1));
  assert(strcmp(text,M8("XЕY"))==0 && length==3 && cursor==2);

  // Full buffers can cycle their pending glyph, but cannot append or corrupt it.
  state={}; char small[3]={}; length=cursor=0;
  assert(tap(state,small,length,cursor,sizeof(small),2,0));
  finish(state); assert(tap(state,small,length,cursor,sizeof(small),2,0));
  assert(tap(state,small,length,cursor,sizeof(small),2,1));
  assert(strcmp(small,M8("АБ"))==0);
  finish(state); assert(!tap(state,small,length,cursor,sizeof(small),9,2));
  assert(strcmp(small,M8("АБ"))==0 && length==2 && cursor==2);
  assert(!tap(state,small,length,cursor,sizeof(small),10,2));
  std::puts("SHEET phone input: Cyrillic with Ё/ё, cycling, confirmation, timeout/wrap, Latin, digits, insertion and limits PASS");
}
