#ifndef DEVELOPMENT_HPP
#define DEVELOPMENT_HPP

#include "program_store.hpp"

bool development_select(void);
bool program_store_explorer_select(void);

enum class ProgramStoreFileDialogResult : u8 {
  CANCELLED = 0,
  EXISTING,
  NEW_FILE
};

// Общие файловые диалоги на устройстве. Редакторы языков используют тот же
// обход дерева, управление и проверку имён, что и Проводник, вместо собственных
// независимых плоских списков программ.
ProgramStoreFileDialogResult program_store_choose_file(
    program_store::ProgramType type, u16 start_directory, bool allow_new,
    program_store::Entry& out_entry, u16& out_directory);
bool program_store_choose_directory(u16 start_directory, u16 forbidden_tree,
                                    u16& out_directory);
bool program_store_choose_save_target(program_store::ProgramType type,
                                      u16 start_directory, char* name,
                                      usize name_capacity,
                                      u16& out_directory);

bool program_store_view_entry(const program_store::Entry& entry);
bool program_store_view_entry(program_store::ProgramType type, const char* name);
bool program_store_apply_font(const program_store::Entry& entry);
bool program_store_apply_font(const char* name);
bool program_store_suspend_font_for_usb(void);
void program_store_restore_font_after_usb(void);

#endif
