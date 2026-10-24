#ifndef MK61_LANGUAGE_VM_REPEAT_HPP
#define MK61_LANGUAGE_VM_REPEAT_HPP
#include "language_flash_cache.hpp"
#include "language_vm_cached_execution.hpp"

// Test-only raw-image adapter. Production repeated calls use the same Store
// and preparation helper as all other certified file/RAM-cache launches.

namespace language_vm { namespace flash {
// A synchronous prepared-call loan, not another cache. Both its descriptor
// and bytes come from the existing epoch/fingerprint-checked page pool.
// Never retains an APP entry, workspace pointer or native continuation.
class RepeatImage {
  ReadCache& cache_;
  const uint8_t* bytes_=nullptr;
  ReadCache::Image image_{};
public:
  RepeatImage(ReadCache& cache,uint32_t revision,uint16_t source,
              uint32_t fingerprint,Language language):cache_(cache) {
    if(cache.image(revision,source,fingerprint,image_) && image_.validated.wide && image_.validated.language==language)
      (void)cache.borrow(revision,image_.directory,image_.validated.size,{},bytes_,true);
  }
  ~RepeatImage(){cache_.release(bytes_);}
  RepeatImage(const RepeatImage&)=delete;
  RepeatImage& operator=(const RepeatImage&)=delete;
  explicit operator bool() const {return bytes_!=nullptr;}
  const uint8_t* bytes() const {return bytes_;}
  const ValidatedImage& validated() const {return image_.validated;}
  uint32_t source_stamp() const {return image_.stamp;}
  uint16_t source() const {return image_.source;}
  IO io() const {
    IO io{};io.context=const_cast<RepeatImage*>(this);
    io.lookup=[](void* raw,uint32_t key,bool number,uint32_t* result) {
      const auto& image=*static_cast<RepeatImage*>(raw);
      if(!image.bytes_ || !result)return false;
      unsigned low=0,high=image.validated().lines;
      while(low<high) {
        const unsigned mid=low+(high-low)/2;
        const uint32_t found=dword(image.bytes_+HEADER_SIZE+mid*8+(number?0:4));
        if(number && found==key){*result=dword(image.bytes_+HEADER_SIZE+mid*8+4);return true;}
        if(number?found<key:found<=key)low=mid+1;else high=mid;
      }
      *result=number?UINT32_MAX:low?dword(image.bytes_+HEADER_SIZE+(low-1)*8):0;
      return true;
    };
    return io;
  }
};
}
// Fresh invocation state, persistent numeric banks. No stale I/O flags,
// stack cursors, input expressions or APP pointers cross a RUN boundary.
inline bool prepare_repeat_call(CompilerContext& context,const flash::RepeatImage& image,
                                PersistentValues& values,ExecutionState& state,
                                loadable_module::Command command,uint32_t mode,flash::IO& lookup) {
  const auto language=image.validated().language;
  auto& r=context.execution;r={};
  r.size=sizeof(r);r.version=REQUEST_VERSION;r.image=image.bytes();r.image_size=image.validated().size;
  r.variables=values.variables[language==Language::BASIC?0:1];
  r.array=language==Language::BASIC?values.array:values.focal_array;
  r.array_count=language==Language::BASIC?385:64;
  r.mode=command==loadable_module::Command::TINYBASIC_RUN_ID_STATUS?uint8_t(mode):0;
  r.storage=&lookup;
  context.language=language;
  values.selected[language==Language::BASIC?0:1]=image.source();
  // Keep the resident's existing certificate check and CORRUPT_MODULE
  // contract, including a malformed descriptor cached by an earlier load.
  // The executor still performs its independent request/view checks.
  if(!prepare_cached_execution(context,image.validated(),state,command))return false;
  context.source_id=image.source();context.prepared=true;context.cache_target=false;
  context.storage=nullptr;context.cache_driver=0xFFFF;context.clear_requested=0;context.language=language;
  return true;
}
}
#endif
