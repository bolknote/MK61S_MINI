#ifndef FL_NATIVE_HEALTH_H
#define FL_NATIVE_HEALTH_H
/* Diagnostic observation only. Addresses and offsets come from the exact
 * resident ELF/DWARF; no resident state, counters or timing is modified. */
enum {
 FL_NATIVE_BEFORE_LOGICAL=1,FL_NATIVE_LOGICAL_SERVICE,FL_NATIVE_AFTER_LOGICAL,
 FL_NATIVE_AFTER_PHYSICAL,FL_NATIVE_AFTER_RESTORE,FL_NATIVE_POST_SERVICE,
 FL_NATIVE_POST_KEYPOLL,FL_NATIVE_LOAD_SERVICE,FL_NATIVE_CLEANUP
};
typedef struct {
 uint32_t at,timeouts,resets,aborts,errors,stage,result,pending,phase,online;
} fl_native_snapshot;
static fl_native_snapshot fl_native_baseline,fl_native_previous;
static fl_native_snapshot fl_native_fault_before,fl_native_fault_after;
static uint32_t fl_native_fault,fl_native_previous_edge;
static uint32_t fl_native_fault_previous_edge;
static __attribute__((noinline,noclone,noipa)) void fl_native_read(fl_native_snapshot *s) {
 s->at=R(0x40054028u);
 s->timeouts=R(FL_NATIVE_I2C_TIMEOUTS);s->resets=R(FL_NATIVE_I2C_RESETS);
 s->aborts=R(FL_NATIVE_I2C_ABORTS);s->errors=R(FL_NATIVE_KBD_ERRORS);
 s->stage=R(FL_NATIVE_I2C_STAGE);s->result=R(FL_NATIVE_I2C_RESULT);
 s->pending=*(volatile const uint8_t *)(uintptr_t)FL_NATIVE_KBD_PENDING;
 s->phase=*(volatile const uint8_t *)(uintptr_t)FL_NATIVE_KBD_PHASE;
 s->online=*(volatile const uint8_t *)(uintptr_t)FL_NATIVE_KBD_ONLINE;
}
static __attribute__((noinline,noclone,noipa)) void fl_native_start(void) {
 fl_native_read(&fl_native_baseline);fl_native_previous=fl_native_baseline;
 fl_native_fault=fl_native_previous_edge=fl_native_fault_previous_edge=0;
}
static __attribute__((noinline,noclone,noipa)) int fl_native_edge(unsigned edge) {
 fl_native_snapshot s;fl_native_read(&s);
 if(!fl_native_fault && (s.timeouts!=fl_native_baseline.timeouts ||
    s.resets!=fl_native_baseline.resets || s.aborts!=fl_native_baseline.aborts ||
    s.errors!=fl_native_baseline.errors)) {
  fl_native_fault=edge;fl_native_fault_previous_edge=fl_native_previous_edge;
  fl_native_fault_before=fl_native_previous;fl_native_fault_after=s;
 }
 fl_native_previous=s;fl_native_previous_edge=edge;
 return !fl_native_fault;
}
#endif
