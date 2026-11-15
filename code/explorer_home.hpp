#ifndef MK61_EXPLORER_HOME_HPP
#define MK61_EXPLORER_HOME_HPP

#include "mk8_literal.hpp"

namespace explorer_home {

enum class Page : u8 { DISK, HOME, GAMES, PROGRAMS, DOCUMENTS, GAME_FILES, FOLDER };

inline Page session_page(u8 flags) { return (Page)(flags >> 1); }
inline u8 session_flags(Page page, u8 previous = 0) {
  return (u8)((previous & 1U) | ((u8)page << 1));
}

inline const char* label(Page page, bool russian) {
  switch(page) {
    case Page::GAMES: return russian ? M8("Игры") : "Games";
    case Page::PROGRAMS: return russian ? M8("Программы") : "Programs";
    case Page::DOCUMENTS: return russian ? M8("Мои файлы") : "My files";
    case Page::DISK: return russian ? M8("Весь диск") : "All files";
    default: return russian ? M8("Проводник") : "Explorer";
  }
}

// The reserved folder names are ASCII letters in both UTF-8 and M8.
inline bool named(const char* name, const char* lower) {
  while(*lower)
    if(((u8)*name++ | 0x20U) != (u8)*lower++) return false;
  return *name == 0;
}

inline bool user_folder(const char* name) {
  return name[0] != '.' && !named(name, "system") && !named(name, "fonts");
}

inline Page folder_page(const char* name) {
  if(named(name, "games")) return Page::GAMES;
  if(named(name, "programs")) return Page::PROGRAMS;
  if(named(name, "documents")) return Page::DOCUMENTS;
  return Page::FOLDER;
}

inline const char* folder_label(const char* name, bool russian) {
  const auto page = folder_page(name);
  if(page != Page::FOLDER) return label(page, russian);
  return russian && named(name, "music") ? M8("Музыка") : nullptr;
}

} // namespace explorer_home
#endif
