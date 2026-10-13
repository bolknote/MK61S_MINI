#include "compact_format.hpp"
#include <cstdint>
#include <cstring>
#include <climits>
namespace compact_format {
namespace {
struct Sink {
  char* output;
  std::size_t capacity;
  uint64_t length = 0;
  void repeat(char value, uint32_t count) {
    if(output && capacity && length < capacity-1) {
      const std::size_t free = capacity-1-static_cast<std::size_t>(length);
      std::memset(output+length,value,count < free ? count : free);
    }
    length += count;
  }
  void bytes(const char* value, uint32_t count) {
    if(output && capacity && length < capacity-1) {
      const std::size_t free = capacity-1-static_cast<std::size_t>(length);
      std::memcpy(output+length,value,count < free ? count : free);
    }
    length += count;
  }
  int finish() {
    if(output && capacity) output[length < capacity ? static_cast<std::size_t>(length) : capacity-1] = 0;
    return length > INT_MAX ? -1 : static_cast<int>(length);
  }
};
static uint32_t number(const char*& at) {
  uint32_t value=0;
  while(*at>='0' && *at<='9') {
    const uint32_t digit=static_cast<uint32_t>(*at++-'0');
    if(value>(UINT32_MAX-digit)/10U) value=UINT32_MAX;
    else value=value*10U+digit;
  }
  return value;
}
} // namespace
int vsnprintf(char* output, std::size_t capacity, const char* format, va_list incoming) {
  Sink sink{output,capacity};
  if(!format) return sink.finish();
  va_list args; va_copy(args,incoming);
  while(*format) {
    if(*format!='%') { sink.bytes(format++,1); continue; }
    ++format;
    bool left=false,zero=false,plus=false,space=false,alternate=false;
    bool scanning=true;
    while(scanning) switch(*format) {
      case '-':left=true;++format;break;
      case '0':zero=true;++format;break;
      case '+':plus=true;++format;break;
      case ' ':space=true;++format;break;
      case '#':alternate=true;++format;break;
      default:scanning=false;break;
    }
    uint32_t width=0;
    if(*format=='*') {
      ++format;const int value=va_arg(args,int);
      if(value<0) { left=true;width=0U-static_cast<uint32_t>(value); }
      else width=static_cast<uint32_t>(value);
    } else width=number(format);
    int precision=-1;
    if(*format=='.') {
      ++format;
      if(*format=='*') { ++format;precision=va_arg(args,int); }
      else { const uint32_t parsed=number(format);precision=parsed>INT_MAX ? INT_MAX : static_cast<int>(parsed); }
    }
    char length=0;
    if(*format=='h' || *format=='l' || *format=='L') length=*format++;
    const char conversion=*format;
    if(!conversion) break;
    ++format;
    const char* text=nullptr;
    uint32_t count=0,padded_zeros=0;
    char digits[32], character=0, prefix[3];
    uint32_t prefix_count=0;
    switch(conversion) {
      case 'd':case 'i':case 'u':case 'o':case 'x':case 'X':case 'p': {
        uint32_t value=0;
        if(conversion=='p') { value=static_cast<uint32_t>(reinterpret_cast<uintptr_t>(va_arg(args,void*)));alternate=true; }
        else if(conversion=='d' || conversion=='i') {
          const int32_t signed_value=length=='l' ? static_cast<int32_t>(va_arg(args,long)) :
              (length=='h' ? static_cast<int16_t>(va_arg(args,int)) : va_arg(args,int));
          value=static_cast<uint32_t>(signed_value);
          if(signed_value<0) { prefix[prefix_count++]='-';value=0U-value; }
          else if(plus) prefix[prefix_count++]='+';
          else if(space) prefix[prefix_count++]=' ';
        } else value=length=='l' ? static_cast<uint32_t>(va_arg(args,unsigned long)) :
            (length=='h' ? static_cast<uint16_t>(va_arg(args,unsigned int)) : va_arg(args,unsigned int));
        const unsigned base=conversion=='o' ? 8 : ((conversion=='x' || conversion=='X' || conversion=='p') ? 16 : 10);
        if(alternate && base==16 && value) { prefix[prefix_count++]='0';prefix[prefix_count++]=conversion=='X' ? 'X' : 'x'; }

        char* end=digits+sizeof(digits);char* begin=end;
        if(value || precision!=0) do { const unsigned digit=value%base;*--begin=static_cast<char>(digit<10 ? '0'+digit : (conversion=='X' ? 'A' : 'a')+digit-10);value/=base; } while(value);
        // Preserve nano's historical %#o zero spelling without precision.
        // With explicit precision use deterministic octal semantics; nano's
        // old implementation tests its uninitialized previous digit count.
        const uint32_t raw_count=static_cast<uint32_t>(end-begin);
        if(alternate && base==8 && (precision<0 || begin==end ||
            (*begin!='0' && precision<=static_cast<int>(raw_count)))) *--begin='0';
        text=begin;count=static_cast<uint32_t>(end-begin);
        if(precision>static_cast<int>(count)) padded_zeros=static_cast<uint32_t>(precision)-count;
        if(precision>=0) zero=false;
        break;
      }
      case 'c': character=static_cast<char>(va_arg(args,int));text=&character;count=1;break;
      case 's': {
        text=va_arg(args,const char*);if(!text) text="(null)";
        while(text[count] && (precision<0 || count<static_cast<uint32_t>(precision))) ++count;
        break;
      }
      case 'n':
        if(length=='l') *va_arg(args,long*)=static_cast<long>(sink.length);
        else if(length=='h') *va_arg(args,short*)=static_cast<short>(sink.length);
        else *va_arg(args,int*)=static_cast<int>(sink.length);
        continue;
      case 'e':case 'E':case 'f':case 'F':case 'g':case 'G':
        // Same integer-only nano printf ABI: consume the floating argument.
        // Floating formatting is not part of MK61_SERVICE_CAP_FORMAT.
        if(length=='L') (void)va_arg(args,long double);else (void)va_arg(args,double);
        continue;
      default:character=conversion;text=&character;count=1;break;
    }
    const uint64_t content=static_cast<uint64_t>(count)+prefix_count+padded_zeros;
    const uint32_t pad=content<width ? width-static_cast<uint32_t>(content) : 0;
    if(!left && !zero) sink.repeat(' ',pad);
    sink.bytes(prefix,prefix_count);
    if(!left && zero) sink.repeat('0',pad);
    sink.repeat('0',padded_zeros);sink.bytes(text,count);
    if(left) sink.repeat(' ',pad);
  }
  va_end(args);return sink.finish();
}
int snprintf(char* output, std::size_t capacity, const char* format, ...) {
  va_list args;va_start(args,format);const int result=vsnprintf(output,capacity,format,args);va_end(args);return result;
}
} // namespace compact_format

#if defined(ARDUINO_ARCH_STM32) && (defined(STM32F401xC) || defined(STM32F401xE) || defined(STM32F411xE))
// Preserve the C ABI used by project/SDK callers without touching core headers.
extern "C" int snprintf(char* output, std::size_t capacity, const char* format, ...) {
  va_list args; va_start(args,format);
  const int result=compact_format::vsnprintf(output,capacity,format,args);
  va_end(args);return result;
}
extern "C" int vsnprintf(char* output, std::size_t capacity, const char* format, va_list args) {
  return compact_format::vsnprintf(output,capacity,format,args);
}
#endif
