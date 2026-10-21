#include "shared_memory.hpp"
#include "workspace_swap.hpp"
#include "language_vm_abi.hpp"
#include <assert.h>
#include <stdio.h>
#include <string.h>

using namespace shared_memory;
using namespace workspace_swap;
namespace {
u8 expected[language_vm::VALUES_SIZE];
void whole(Lease& lease) {
  assert(acquire(Owner::LANGUAGE_VM, WORKSPACE_SIZE, AcquireMode::REQUIRED, lease));
}
}
int main() {
  // Establish a valid full VM resident. Nonzero tail markers compress well
  // and let the test observe both source-owner wipes and snapshot restores.
  {
    Lease lease; whole(lease);
    memset(lease.data(), 0, lease.size());
    memset(expected, 0x5A, sizeof(expected)); expected[8] = 123;
    memcpy(lease.data()+language_vm::COMPILER_WORKSPACE_SIZE, expected, sizeof(expected));
  }
  const auto old = resident_token(Arena::WORKSPACE);
  WorkspacePartition partition;
  assert(!partition.open(Owner::FOCAL, sizeof(expected)));
  assert(!partition.open(Owner::LANGUAGE_VM, sizeof(expected)-1));
  assert(partition.open(Owner::LANGUAGE_VM, sizeof(expected)));
  assert(!commit_resident_handoff(old)); // Beginning the partition revokes the old epoch.
  assert(capacity(Arena::WORKSPACE) == language_vm::COMPILER_WORKSPACE_SIZE);
  WorkspacePartition nested; assert(!nested.open(Owner::LANGUAGE_VM,sizeof(expected)));
  {
    Lease foreign, oversized;
    assert(!acquire(Owner::SETUP, 32, AcquireMode::REQUIRED, foreign));
    assert(!acquire(Owner::FOCAL, WORKSPACE_SIZE, AcquireMode::REQUIRED, oversized));
    Lease prefix;
    assert(acquire(Owner::TINYBASIC, language_vm::COMPILER_WORKSPACE_SIZE,
                   AcquireMode::REQUIRED, prefix));
    memset(prefix.data(),0xA5,prefix.size());
    assert(!partition.close()); // Cannot expand while an APP prefix is live.
    assert(!memcmp(partition.tail(),expected,sizeof(expected)) && validate_invariants());
  }
  {
    Lease prefix;
    assert(acquire(Owner::FOCAL, language_vm::COMPILER_WORKSPACE_SIZE,
                   AcquireMode::REQUIRED,prefix));
    assert(prefix.fresh()); memset(prefix.data(),0xCC,prefix.size());
    assert(!memcmp(partition.tail(),expected,sizeof(expected)) && validate_invariants());
  }
  assert(partition.close() && !workspace_partitioned() && validate_invariants());
  assert(resident_owner(Arena::WORKSPACE) == Owner::LANGUAGE_VM);
  assert(owner_snapshot_schema(Owner::LANGUAGE_VM) == 9);
  {
    Lease lease; whole(lease);
    assert(!lease.fresh());
    assert(!memcmp(lease.data()+language_vm::COMPILER_WORKSPACE_SIZE,expected,sizeof(expected)));
    for(unsigned i=0;i<language_vm::COMPILER_WORKSPACE_SIZE;++i)assert(!lease.data()[i]);
  }
  // Full-width clients work again, and ordinary swap must capture/restore the
  // complete (prefix + values tail) schema, not a former compiler prefix.
  {
    Lease other;
    assert(acquire(Owner::FOCAL, 4096, AcquireMode::REQUIRED, other));
    memset(other.data(),0x11,other.size());
  }
  assert(statistics().valid && statistics().owner == Owner::LANGUAGE_VM);
  {
    Lease lease; whole(lease);
    assert(!lease.fresh());
    assert(!memcmp(lease.data()+language_vm::COMPILER_WORKSPACE_SIZE,expected,sizeof(expected)));
  }
  const auto before = statistics().restores;
  {
    WorkspacePartition next; assert(next.open(Owner::LANGUAGE_VM,sizeof(expected)));
    Lease compiler;
    assert(acquire(Owner::FOCAL, 4096, AcquireMode::REQUIRED, compiler));
    assert(compiler.fresh()); // An old FOCAL snapshot exists, but must not be decoded here.
    assert(statistics().restores == before);
    assert(!memcmp(next.tail(),expected,sizeof(expected)));
  }
  assert(!workspace_partitioned() && validate_invariants());
  {
    Lease lease;whole(lease);memset(lease.data(),0xD3,language_vm::COMPILER_WORKSPACE_SIZE);
  }
  WorkspacePartition reused;assert(!reused.reuse_prefix());
  assert(reused.open(Owner::LANGUAGE_VM,sizeof(expected)) && reused.reuse_prefix());
  assert(!reused.reuse_prefix());
  {
    Lease prefix;assert(acquire(Owner::LANGUAGE_VM,language_vm::COMPILER_WORKSPACE_SIZE,AcquireMode::REQUIRED,prefix));
    assert(!prefix.fresh());
    for(unsigned i=0;i<prefix.size();++i)assert(prefix.data()[i]==0xD3);
    assert(!reused.reuse_prefix() && !reused.close());
    assert(!memcmp(reused.tail(),expected,sizeof(expected)));
  }
  assert(reused.close());
  {
    Lease lease;whole(lease);
    for(unsigned i=0;i<language_vm::COMPILER_WORKSPACE_SIZE;++i)assert(lease.data()[i]==0);
    assert(!memcmp(lease.data()+language_vm::COMPILER_WORKSPACE_SIZE,expected,sizeof(expected)));
  }
  assert(reused.open(Owner::LANGUAGE_VM,sizeof(expected)) && reused.reuse_prefix());
  {
    Lease compiler;assert(acquire(Owner::FOCAL,4096,AcquireMode::REQUIRED,compiler) && compiler.fresh());
    for(unsigned i=0;i<compiler.size();++i)assert(compiler.data()[i]==0);
    memset(compiler.data(),0xCC,compiler.size());
  }
  assert(!reused.reuse_prefix());
  {
    Lease prefix;assert(acquire(Owner::LANGUAGE_VM,language_vm::COMPILER_WORKSPACE_SIZE,AcquireMode::REQUIRED,prefix) && prefix.fresh());
    for(unsigned i=0;i<prefix.size();++i)assert(prefix.data()[i]==0);
  }
  assert(reused.close() && validate_invariants());
  discard();
  puts("workspace partition: protected tail, owners/epochs, full snapshots, no partial restore PASS");
}
