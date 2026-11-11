#ifndef FL_LOGICAL_FENCE_H
#define FL_LOGICAL_FENCE_H
typedef struct {
 uint32_t waited,calls,initial_pending,initial_phase,pending,phase;
} fl_logical_snapshot;
/* Read-only, build-pinned Keyboard::transaction_pending(). Register selection
 * and its delayed response are one transaction even while the wires are idle.
 * Normal service finishes it before any lease; native state is never patched. */
static __attribute__((noinline,noclone,noipa)) int fl_finish_keyboard(void (*service)(void),fl_logical_snapshot *s) {
 const uint32_t start=R(0x40054028u);
 s->calls=s->waited=0;
 s->initial_pending=*(volatile const uint8_t *)(uintptr_t)FL_NATIVE_KBD_PENDING;
 s->initial_phase=*(volatile const uint8_t *)(uintptr_t)FL_NATIVE_KBD_PHASE;
 for(;;) {
  s->pending=*(volatile const uint8_t *)(uintptr_t)FL_NATIVE_KBD_PENDING;
  s->phase=*(volatile const uint8_t *)(uintptr_t)FL_NATIVE_KBD_PHASE;
  s->waited=R(0x40054028u)-start;
  if(s->pending>1||s->phase>8)return 0;
  if(s->waited>=100000u)return 0;
  if(!s->pending&&!s->phase)return 1;
  ++s->calls;service();
  if(!fl_native_edge(FL_NATIVE_LOGICAL_SERVICE))return 0;
 }
}
#endif
