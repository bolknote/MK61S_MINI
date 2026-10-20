#ifndef MK61_LANGUAGE_LINKED_PROGRAM_HPP
#define MK61_LANGUAGE_LINKED_PROGRAM_HPP
#include "language_vm_abi.hpp"

namespace language_vm { namespace linked {
// Experimental LVP1 container. Member LBV1/LBV2 images retain local addresses;
// neither native pointers nor VM/APP layouts are written to disk. Validation
// and all storage belong to the caller, not a new static cache or allocation.
// Header: magic[4], version:u8, flags:u8, count:u16, size:u32, entry:u32,
// directory_bytes:u32, reserved:u32, payload_crc32:u32, header_crc32:u32.
// Directory record: symbol:u32, offset:u32, size:u32, source_identity:u32.
// All words are little-endian. Exact earlier records may share an image.
constexpr uint16_t HEADER_BYTES=32, ENTRY_BYTES=16, MAX_MEMBERS=64;
constexpr uint8_t VERSION=1;
struct Input {
  const uint8_t* bytes=nullptr;
  flash::Input paged={};
  uint32_t size=0;
  void* epoch_context=nullptr;
  uint32_t (*epoch)(void*)=nullptr;
};
// Without an epoch callback the backing image must be immutable and alive for
// the entire session. Catalog, numeric banks and context must remain alive
// until execute returns even if a callback invalidates/releases the image.
struct Member {
  uint32_t symbol,offset;
  // Bundle-local debug identity, NOT an installed C9 inode. An editor host
  // must explicitly map it through the source manifest before opening files.
  uint16_t source_id;
  ValidatedImage validated;
};
struct Program {
  Input input;
  const Member* members=nullptr;
  uint16_t count=0;
  uint32_t entry=0,epoch=0,identity=0;
};
// Scratch BOUNDARIES I/O is needed only to validate LBV2 members. LBV1 is a
// raw host-compatibility path; shipping wide-only executors reject it.
// GRAPH expressions are deliberately left to the ordinary VM for now: its
// graph cleanup is not resumable at arbitrary step/INPUT boundaries. Regular
// graphics operations are unchanged. No unsupported image publishes a Program.
// A successful Program pins no source/APP.
Error inspect(Input,Member*,uint16_t capacity,Program&,flash::IO scratch={});
bool current(const Program&);

// One pointer-free continuation is reused for every member. It may survive
// INPUT/APP eviction; fresh services, catalog and numeric banks are rebound
// on each call. No native call frame is retained between members.
enum class Phase : uint8_t { EMPTY, ENTER, RUN, AWAIT_INPUT, DONE, FAILED };
struct Session {
  Continuation control;
  uint32_t identity=0,epoch=0,symbol=0,steps=0,members=0;
  uint16_t index=0;
  Phase phase=Phase::EMPTY;
};
struct Host {
  void* context=nullptr;
  bool (*bind)(void*,Language,Bindings&)=nullptr;
  // Optional per-member UI/source identity hook; not called again on resume.
  bool (*enter)(void*,uint32_t symbol,uint16_t source_id,Language)=nullptr;
  // Return the next symbol, or zero to finish. This replaces the outer
  // script dispatcher, not the language's own GOSUB/CALL stack.
  bool (*next)(void*,uint32_t completed_symbol,uint32_t& next_symbol)=nullptr;
  // Optional synchronous immutable member loan (for example existing cache
  // frames). A null result selects paged input. release runs on every exit.
  bool (*borrow)(void*,const Member&,const uint8_t*& image)=nullptr;
  void (*release)(void*,const uint8_t* image)=nullptr;
};
using Kernel=RunResult (*)(const View&,Continuation&,const Bindings&,
                          const Services&,uint32_t,bool);
enum class Status : uint8_t { DONE, AWAIT_INPUT, BUDGET, UNRESOLVED, INVALIDATED, ERROR };
struct Result {
  Status status;
  RunResult run;
  uint32_t symbol,steps,members;
  uint16_t source_id;
};
bool start(const Program&,Session&,uint32_t entry=0);
// A nonzero budget is global to this call, including member transitions.
// LIMIT and INPUT preserve the exact current continuation. INPUT resumes
// only after a value has explicitly been supplied; it never restarts RUN.
Result execute_with(const Program&,Session&,const Host&,const Services&,Kernel,
                    uint32_t budget=0,const Value* input=nullptr);
// Unlimited, fresh whole-member LBV2 calls: raw container bytes or a mandatory
// non-null immutable loan. Never constructs a paged Reader. INPUT/LIMIT still
// publish their continuation, but only execute_with may resume it; this entry
// rejects an already suspended session instead of silently restarting it.
Result execute_whole_with(const Program&,Session&,const Host&,const Services&,Kernel);
inline Result execute(const Program& p,Session& s,const Host& h,const Services& v,
                      uint32_t budget=0,const Value* input=nullptr) {
  return execute_with(p,s,h,v,run,budget,input);
}
#if defined(MK61_LINKED_VM_POC) && MK61_LINKED_VM_POC
// Experimental in-process export for unlimited whole-member calls only.
// Only usable while LANGVM is pinned; clear its active request before
// unpinning. No native pointer is ever persisted. Not a public APP service.
constexpr uint32_t KERNEL_EXPORT_COMMAND=0x70F,KERNEL_EXPORT_MAGIC=0x3150564C;
struct KernelExport {uint32_t magic;Kernel kernel;const Services* services;};
// Cold VMSTORE handoff. All pointers/callbacks belong to the resident caller;
// no APP code, Reader object or native continuation survives the return.
constexpr uint32_t LOAD_PHASE=0x4C56,LOAD_MAGIC=0x324C564C;
constexpr unsigned FRAGMENT_BYTES=4096,MAX_FRAGMENTS=64;
struct Storage {
  uint16_t files[MAX_FRAGMENTS];
  uint32_t size=0,revision=0;
};
struct LoadRequest {
  uint32_t size,magic;
  uint16_t directory,capacity;
  Storage* storage;
  Member* members;
  Program* program;
  Input input;
  bool (*poll)(void*);
  Error error=Error::NONE;
};
struct Fragment {uint16_t id;uint32_t size;};
using LocateFragment=bool (*)(void*,uint16_t,const char*,Fragment&);
// Synchronous cold APP implementation; shared inspect_flash/verify is reused.
uint32_t load(LoadRequest*,void* context,LocateFragment);
#if UINTPTR_MAX == UINT32_MAX
static_assert(sizeof(Input)==28 && sizeof(Storage)==136 && sizeof(LoadRequest)==60,
    "resident/cold-loader handoff ABI");
#endif
#endif
static_assert(std::is_trivially_copyable<Session>::value,"linked session must survive APP eviction");
}}
#endif
