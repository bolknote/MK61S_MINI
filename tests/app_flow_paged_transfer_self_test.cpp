#include "app_flow_transfer.hpp"
#include "workspace_swap.hpp"
#include "language_vm_abi.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
using namespace shared_memory;
using loadable_module::RuntimeStatus;
namespace {
Lease cached_app;
unsigned evictions;
bool cache_pinned;
}
namespace loadable_module {
RuntimeStatus evict_cached() {
  ++evictions;
  if(cache_pinned)return RuntimeStatus::BUSY;
  cached_app.reset();return RuntimeStatus::OK;
}
}
int main() {
  {
    Lease values;
    assert(workspace_swap::acquire(Owner::LANGUAGE_VM,WORKSPACE_SIZE,
        workspace_swap::AcquireMode::REQUIRED,values));
    memset(values.data()+language_vm::COMPILER_WORKSPACE_SIZE,0xA5,language_vm::VALUES_SIZE);
  }
  WorkspacePartition partition;
  assert(partition.open(Owner::LANGUAGE_VM,language_vm::VALUES_SIZE));
  static_assert(sizeof(language_vm::ExecutionState)<=language_vm::FLASH_COMPILER_WORKSPACE_SIZE,
      "paged execution must leave its resident page intact");
  assert(cached_app.acquire_cache(Arena::APP,Owner::LOADABLE_MODULE,20452));
  auto* const app=cached_app.data();
  memset(app,0xB7,cached_app.size());
  for(unsigned run=0;run<20;++run) {
    app_flow::Transfer transfer(Owner::LANGUAGE_VM);
    // The file can exceed 64 KiB: only its fixed execution prefix lives in RAM.
    app_flow::ImageTransfer plan={};plan.size=200000;plan.prefix=sizeof(language_vm::ExecutionState);
    assert(transfer.commit_paged(plan,false)==RuntimeStatus::OK);
    assert(evictions==0 && cached_app.ok() && cached_app.data()==app);
    assert(!plan.image && plan.workspace==transfer.workspace_lease().data());
    assert(plan.workspace_size==capacity(Arena::WORKSPACE));
    memset(plan.workspace,0x51,plan.prefix);
    for(unsigned i=0;i<cached_app.size();++i)assert(app[i]==0xB7);
    for(unsigned i=0;i<language_vm::VALUES_SIZE;++i)assert(partition.tail()[i]==0xA5);
  }
  // Cold compilation retains the prior eviction/error contract.
  app_flow::Transfer cold(Owner::LANGUAGE_VM);
  app_flow::ImageTransfer plan={};plan.size=200000;plan.prefix=sizeof(language_vm::ExecutionState);
  cache_pinned=true;
  assert(cold.commit_paged(plan)==RuntimeStatus::BUSY && cached_app.ok());
  assert(!plan.workspace && !cold.workspace_lease().ok());
  cache_pinned=false;
  assert(cold.commit_paged(plan)==RuntimeStatus::OK && !cached_app.ok());
  assert(evictions==2);
  app_flow::ImageTransfer bad=plan;bad.image=app;
  assert(cold.commit_paged(bad,false)==RuntimeStatus::CORRUPT_MODULE);
  assert(evictions==2 && validate_invariants());
  puts("Paged RUN: 20 warm transfers preserve the VM APP; cold eviction, pin refusal and bounded RAM PASS");
}
