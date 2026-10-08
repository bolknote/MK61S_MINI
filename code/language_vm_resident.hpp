#ifndef MK61_LANGUAGE_VM_RESIDENT_HPP
#define MK61_LANGUAGE_VM_RESIDENT_HPP
#include "language_vm_abi.hpp"
#include "loadable_module_runtime.hpp"

namespace language_vm {
bool execute_resident(ExecuteRequest&);
struct CacheDiagnostics {
  uint32_t budget,payload,used,lookups,hits,misses,reservations,reservation_failures,
           publications,evictions,invalidations;
};
// Read-only bounded counters; false means this build has no persistent cache.
bool cache_diagnostics(CacheDiagnostics&);
// Routes one existing frontend command, transfers pointer-free values around
// its workspace, and executes a requested image. F411 retains verified M61
// BASIC images without retaining compiler/executor pointers or mutable values.
// Placement is resident Flash or external hot/cold APPs, selected at build.
loadable_module::RuntimeStatus invoke_resident(Language, loadable_module::Command,
                                               uint32_t, uint32_t, uint32_t&);
}  // namespace language_vm
#endif
