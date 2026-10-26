#ifndef MK61_APP_FLOW_HPP
#define MK61_APP_FLOW_HPP
#include "app_flow.h"

namespace app_flow {
using Status = mk61_app_flow_status;
using Target = mk61_app_flow_target;
using Step = mk61_app_flow;
using Invoke = Status (*)(void* backend, const Target&, Step&);

// Invoker must finish its native call before returning. Host targets are
// optional resident actions, authorized by this invocation's backend only.
Status run(Target first, void* context, uint32_t context_size,
           uint32_t& result, Invoke invoke, void* backend = nullptr);
}
#endif
