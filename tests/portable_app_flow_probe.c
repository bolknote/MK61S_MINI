#include "mk61_app.h"
typedef struct state { uint32_t value; uint16_t caller, child; } state;
uint32_t mk61_app_flow_step(mk61_app_flow* flow) {
  if(!mk61_app_flow_compatible(flow) || flow->context_size < sizeof(state)) return 0;
  state* context = (state*)flow->context;
  if(flow->current.phase == 0) {
    context->caller = flow->current.file_id;
    context->value = 7;
    mk61_app_flow_call(flow,
        mk61_app_flow_to(MK61_APP_KIND_APPLICATION, 43, 2), 1);
  } else if(flow->current.phase == 2) {
    context->child = flow->current.file_id;
    context->value += 35;
    mk61_app_flow_return(flow, context->value, MK61_FLOW_OK);
  } else if(flow->current.phase == 1) {
    if(flow->status != MK61_FLOW_OK || flow->result != 42 || context->caller != 42 ||
       context->child != 43 || context->value != 42) return 0;
    mk61_app_flow_exit(flow, 42, MK61_FLOW_OK);
  } else return 0;
  return 1;
}
