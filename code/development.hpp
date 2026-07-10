#ifndef DEVELOPMENT_HPP
#define DEVELOPMENT_HPP

#include "program_store.hpp"

bool development_select(void);
bool program_store_explorer_select(void);
bool program_store_view_entry(program_store::ProgramType type, const char* name);
bool program_store_apply_font(const char* name);
bool program_store_suspend_font_for_usb(void);
void program_store_restore_font_after_usb(void);

#endif
