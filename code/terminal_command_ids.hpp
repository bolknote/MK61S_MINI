#ifndef TERMINAL_COMMAND_IDS_HPP
#define TERMINAL_COMMAND_IDS_HPP

#include "rust_types.h"

enum : u8 {
  CMD_UNKNOWN = 0,
  CMD_VERSION, CMD_LIST, CMD_ISA, CMD_ASM, CMD_LASM, CMD_RESET, CMD_REG_DUMP,
  CMD_REG_SET, CMD_SAVE, CMD_LOAD, CMD_1302, CMD_DISASM, CMD_HIN, CMD_HOUT,
  CMD_SET_CODE, CMD_POKE, CMD_DFU, CMD_DUMP, CMD_PUB, CMD_SMAP, CMD_STACK,
  CMD_KBD, CMD_CMD, CMD_CLEAR, CMD_RING, CMD_RENAME, CMD_DIR, CMD_DEL_SLOT,
  CMD_RUN, CMD_OPEN, CMD_ERASE_STORAGE, CMD_INS, CMD_HELP, CMD_HISTORY,
  CMD_LED, CMD_BEEP, CMD_IF, CMD_VFAT_LOG, CMD_FS_LIST, CMD_FS_REMOVE,
  CMD_FS_CLEAN, CMD_FS_PWD, CMD_FS_CD, CMD_FS_MKDIR, CMD_FS_MOVE,
  CMD_FS_RMDIR, CMD_FS_STAT, CMD_RTC
};

// M61 files are data, not a privileged terminal session. Keep this list
// deliberately explicit so adding a terminal command does not grant scripts
// access by accident.
constexpr bool terminal_command_allowed_in_script(u8 id) {
  switch(id) {
    case CMD_VERSION:
    case CMD_LIST:
    case CMD_ISA:
    case CMD_ASM:
    case CMD_LASM:
    case CMD_REG_DUMP:
    case CMD_REG_SET:
    case CMD_LOAD:
    case CMD_1302:
    case CMD_HIN:
    case CMD_HOUT:
    case CMD_SET_CODE:
    case CMD_POKE:
    case CMD_DUMP:
    case CMD_PUB:
    case CMD_STACK:
    case CMD_KBD:
    case CMD_CMD:
    case CMD_RING:
    case CMD_RUN:
    case CMD_OPEN:
    case CMD_INS:
    case CMD_LED:
    case CMD_BEEP:
    case CMD_IF:
      return true;
    default:
      return false;
  }
}

#endif
