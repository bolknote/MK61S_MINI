#ifndef DEVELOPMENT_HPP
#define DEVELOPMENT_HPP

#include "config.h"
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
#if MK61_PROPORTIONAL_UI_FONTS
struct ProgramStoreUiFont {
  u32 key;
  u8 height;
  char name[program_store::NAME_SIZE];
};

// Every valid Fonts/*.FMK file is one selectable face. The filename (without
// .FMK, as stored by C5) is its UI name; the raster height comes from FMK.
// The stable filename key survives catalog reordering and C5 reformatting.
u16 program_store_ui_font_count(void);
bool program_store_ui_font_at(u16 index, ProgramStoreUiFont& out);
bool program_store_describe_ui_font(u32 key, ProgramStoreUiFont& out);
// key=0 selects the first/last face. Otherwise returns the alphabetical
// neighbour of that exact (collision-checked) face in one bounded scan.
bool program_store_step_ui_font(u32 key, i8 delta, ProgramStoreUiFont& out);
bool program_store_apply_ui_font(u32 key, u8& out_height);
// Migration path for the former root-level UI12/UI14/UI16 convention.
bool program_store_apply_legacy_ui_font(u8 size);
void program_store_clear_ui_font(void);
#endif
bool program_store_suspend_font_for_usb(void);
void program_store_restore_font_after_usb(void);

#endif
