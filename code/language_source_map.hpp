#ifndef MK61_LANGUAGE_SOURCE_MAP_HPP
#define MK61_LANGUAGE_SOURCE_MAP_HPP
#include <stdint.h>

namespace language_vm { namespace source_map {
// Sparse provenance is emitted into the image tail. Keep one pending entry
// so two source annotations at the same instruction need only one record.
// The sizing and emission passes use the same bounded encoder.
struct Positions {
  uint32_t previous=0,pending=0,bytes=0;
  uint16_t column=0,count=0,previous_column=0;
  void reset(uint32_t code) {previous=code;pending=bytes=0;column=count=previous_column=0;}
  __attribute__((noinline)) static unsigned encode(uint32_t value,uint8_t* output) {
    unsigned n=0;
    do {output[n++]=uint8_t((value&127)|(value>127?128:0));value>>=7;} while(value);
    return n;
  }
  template<class Write> __attribute__((noinline)) bool flush(Write write) {
    if(!column)return true;
    if(count==UINT16_MAX || pending<previous)return false;
    // Repeating the same column changes no lookup result, including across
    // line boundaries. LINE/HALT already have their own zero-column rule.
    if(count && column==previous_column) {column=0;return true;}
    uint8_t record[8];unsigned n=encode(pending-previous,record);
    n+=encode(column,record+n);
    if(!write(bytes,record,uint16_t(n)))return false;
    bytes+=n;++count;previous=pending;previous_column=column;column=0;return true;
  }
  template<class Write> bool note(uint32_t pc,uint16_t value,Write write) {
    if(!value || pc<previous || pc<pending)return false;
    if(column && pc!=pending && !flush(write))return false;
    pending=pc;column=value;return true;
  }
};
}}
#endif
