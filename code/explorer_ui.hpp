#ifndef MK61_EXPLORER_UI_HPP
#define MK61_EXPLORER_UI_HPP

#include "loadable_module_abi.hpp"
#include "app_flow.h"

// One foreground state machine, compiled into resident OR EXPLORER.APP.
// It returns an action; operations run only after this call has unwound.
namespace explorer_ui {

bool select(loadable_module::ExplorerSession& session);
uint32_t flow_step(mk61_app_flow* flow);

} // namespace explorer_ui

#endif
