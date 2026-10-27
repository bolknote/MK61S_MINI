#ifndef MK61_LANGUAGE_VM_RESIDENT_HPP
#define MK61_LANGUAGE_VM_RESIDENT_HPP
#include "language_vm_abi.hpp"
#include "loadable_module_runtime.hpp"

namespace language_vm {
bool execute_resident(ExecuteRequest&);
struct CacheDiagnostics {
  uint32_t budget,payload,used,lookups,hits,misses,reservations,reservation_failures,
           publications,evictions,invalidations;
#if MK61_FLASH_LANGUAGE_VM
  uint32_t loan_hits=0,loan_misses=0;
#endif
#if MK61_LANGUAGE_VM_CACHE_MIXED
  uint32_t packs=0,thaws=0,packed=0;
#endif
};
// Read-only bounded counters; false means this build has no persistent cache.
bool cache_diagnostics(CacheDiagnostics&);
// Allocate an empty configured cache before a long-lived OVERLAY pins _sbrk.
// No source compilation or language-state initialization; OOM keeps the usual
// uncached execution fallback available.
bool prepare_image_cache();
#if MK61_FLASH_LANGUAGE_VM && (MK61_RESIDENT_LANGUAGE_VM || MK61_OVERLAY_LANGUAGE_VM)
// Input-only NOR progress is scoped to a language invocation. Ordinary
// imports and filesystem maintenance outside it keep their existing path.
bool storage_input_active();
#else
inline bool storage_input_active() {return false;}
#endif
#if defined(MK61_LINKED_VM_POC) && MK61_LINKED_VM_POC
namespace flash {class ReadCache;}
flash::ReadCache* linked_page_cache();
bool run_linked_program(uint16_t directory);
#endif
// Routes one existing frontend command, transfers pointer-free values around
// its workspace, and executes a requested image. F411 retains verified M61
// BASIC images without retaining compiler/executor pointers or mutable values.
// Placement is resident Flash or external hot/cold APPs, selected at build.
loadable_module::RuntimeStatus invoke_resident(Language, loadable_module::Command,
                                               uint32_t, uint32_t, uint32_t&);
}  // namespace language_vm
#endif
