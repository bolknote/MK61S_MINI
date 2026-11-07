#include "hd_gate.hpp"
#include <new>
#include <cstddef>
#include <cstdint>

extern "C" {
unsigned hd_gate_bytes() { return sizeof(Mk61DebugGate); }
int hd_gate_init(void* state, unsigned count, int program) {
    if (!state || reinterpret_cast<std::uintptr_t>(state) % alignof(Mk61DebugGate)) return -1;
    auto* gate = new(state) Mk61DebugGate();
    return gate->configure(count, program != 0) ? 0 : -1;
}
void hd_gate_edit(void* state) { static_cast<Mk61DebugGate*>(state)->edited(); }
int hd_gate_run(void* state, unsigned index, int stopped) {
    return static_cast<Mk61DebugGate*>(state)->ran(index, stopped != 0);
}
int hd_gate_can(void* state) { return static_cast<Mk61DebugGate*>(state)->can_done(); }
unsigned hd_gate_revision(void* state) { return static_cast<Mk61DebugGate*>(state)->revision; }
}
