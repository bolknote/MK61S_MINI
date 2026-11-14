#ifndef MK61_EXPLORER_HOME_HPP
#define MK61_EXPLORER_HOME_HPP

#include "mk8_literal.hpp"

namespace explorer_home {

enum class Page : u8 { DISK, HOME, GAMES, PROGRAMS, DOCUMENTS, GAME_FILES };
constexpr unsigned COUNT = 4;
constexpr Page ITEMS[COUNT] = {Page::GAMES, Page::PROGRAMS, Page::DOCUMENTS, Page::DISK};

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

inline const char* folder(Page page) {
  switch(page) {
    case Page::GAMES: return "Games";
    case Page::PROGRAMS: return "Programs";
    case Page::DOCUMENTS: return "Documents";
    default: return "";
  }
}

} // namespace explorer_home
#endif
