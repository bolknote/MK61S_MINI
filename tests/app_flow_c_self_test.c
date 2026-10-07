#include "app_flow.h"
#include <assert.h>
int main(void) {
  mk61_app_flow step = {0};
  step.size = sizeof(step); step.version = MK61_APP_FLOW_VERSION;
  assert(mk61_app_flow_compatible(&step));
  mk61_app_flow_call(&step, mk61_app_flow_to(2, 0xFFFF, 1), 7);
  assert(step.action == MK61_FLOW_CALL && step.next.kind == 2 && step.resume_phase == 7);
  mk61_app_flow_return(&step, 42, MK61_FLOW_OK);
  assert(step.action == MK61_FLOW_RETURN && step.result == 42);
  return 0;
}
