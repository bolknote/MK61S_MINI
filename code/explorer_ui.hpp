#ifndef MK61_EXPLORER_UI_HPP
#define MK61_EXPLORER_UI_HPP

#include "loadable_module_abi.hpp"

// One foreground state machine, compiled into resident OR EXPLORER.APP.
// It returns an action; operations run only after this call has unwound.
namespace explorer_ui {

bool select(loadable_module::ExplorerSession& session);

} // namespace explorer_ui

#endif
