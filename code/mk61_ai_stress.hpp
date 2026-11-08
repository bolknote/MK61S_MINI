#ifndef MK61_AI_STRESS_HPP
#define MK61_AI_STRESS_HPP
#include "crc32.hpp"
#include <cstdint>
#include <cstring>
namespace mk61ai::diagnostic {
enum class StressFailure : unsigned {
  NONE, EXECUTION, CONTROL, LOCAL_MATH, REMOTE_MATH, MATH_BYTES,
  WRITE, READ, MEMORY_BYTES, CANCEL, MEMORY_CRC
};
inline const char *stress_failure_name(StressFailure f) {
  switch(f) {
    case StressFailure::NONE:return "none";
    case StressFailure::EXECUTION:return "execution_busy";
    case StressFailure::CONTROL:return "core1_control";
    case StressFailure::LOCAL_MATH:return "local_math_status";
    case StressFailure::REMOTE_MATH:return "remote_math_status";
    case StressFailure::MATH_BYTES:return "math_bytes";
    case StressFailure::WRITE:return "write";
    case StressFailure::READ:return "read";
    case StressFailure::MEMORY_BYTES:return "memory_bytes";
    case StressFailure::CANCEL:return "cancel";
    case StressFailure::MEMORY_CRC:return "memory_crc";
  }
  return "invalid";
}
struct StressDiagnostics {
  StressFailure failure=StressFailure::NONE;
  unsigned iteration=0,address=~0U,first_bad=~0U,expected=0,actual=0;
  unsigned write=0,read=0,local_status=0,remote_status=0;
  unsigned math_byte=~0U,math_expected=0,math_actual=0;
  std::uint32_t expected_crc=0,actual_crc=0;
  bool crc_match=false,busy_entered=false,busy_exited=false;
  bool stable_read=false,stable_match=false;
  std::uint32_t stable_crc=0;
  static std::uint32_t crc(const unsigned char *p,unsigned n) {
    return mk61_crc32::finish(mk61_crc32::extend(mk61_crc32::INITIAL_STATE,p,n));
  }
  bool math(unsigned local,unsigned remote,bool submitted,const void *want,const void *got,unsigned bytes) {
    local_status=local;remote_status=remote;address=first_bad=math_byte=~0U;
    write=read=0;expected_crc=actual_crc=0;crc_match=false;
    if(local) {failure=StressFailure::LOCAL_MATH;return false;}
    if(submitted&&remote) {failure=StressFailure::REMOTE_MATH;return false;}
    const auto *a=static_cast<const unsigned char*>(want),*b=static_cast<const unsigned char*>(got);
    for(unsigned i=0;i<bytes;++i) if(a[i]!=b[i]) {
      math_byte=i;math_expected=a[i];math_actual=b[i];failure=StressFailure::MATH_BYTES;return false;
    }
    return true;
  }
  template<class Buffer> bool memory(Buffer &buffer,unsigned index,unsigned char (&want)[256],unsigned char (&got)[256]) {
    iteration=index;address=(index*4093U)&(65536-256);first_bad=~0U;
    write=read=0;crc_match=false;actual_crc=0;
    for(unsigned j=0;j<256;++j) want[j]=static_cast<unsigned char>((j*37U)^(index*13U)^(j>>3));
    expected_crc=crc(want,256);
    const bool wrote=buffer.write(address,want,256);write=wrote?1U:2U;
    if(!wrote) {failure=StressFailure::WRITE;return false;}
    const bool received=buffer.read(address,got,256);read=received?1U:2U;
    if(!received) {failure=StressFailure::READ;return false;}
    actual_crc=crc(got,256);crc_match=actual_crc==expected_crc;
    for(unsigned j=0;j<256;++j) if(want[j]!=got[j]) {
      first_bad=j;expected=want[j];actual=got[j];failure=StressFailure::MEMORY_BYTES;return false;
    }
    if(!crc_match)failure=StressFailure::MEMORY_CRC;
    return crc_match;
  }
};
}
#endif
