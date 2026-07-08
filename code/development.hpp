#ifndef DEVELOPMENT_HPP
#define DEVELOPMENT_HPP

#include "program_store.hpp"

bool development_select(void);
bool program_store_explorer_select(void);
bool program_store_view_entry(program_store::ProgramType type, const char* name);

#endif
