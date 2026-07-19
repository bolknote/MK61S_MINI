#ifndef TERMINAL_CLASS
#define TERMINAL_CLASS
/*
 terminal - модуль работы из терминала с ядром МК61s и калькулятором.
  Terminal command transport and execution for the MK61 core.
*/
#include "Arduino.h"
#include "config.h"
#include "rust_types.h"
#include "cross_hal.h"
#include "mk61emu_core.h"
#include "disasm.hpp"
#include "tools.hpp"
#include "library_pmk.hpp"
#include "ledcontrol.h"
#include "mk_math.hpp"
#include "mk61_ref.hpp"
#include "virtual_fat.hpp"
#include "program_store.hpp"
#include "storage_path.hpp"
#include "terminal_command_ids.hpp"
#include "terminal_core.hpp"
#include "terminal_protocol.hpp"
#include "utf8_view.hpp"

extern  const char terminal_symbols[16];

static  constexpr u32 seqNOP = seq(sw::K,sw::_0);
static  const u32 key_sequence_on_cmd[15*16] = {
  seq(sw::_0),  seq(sw::_1),  seq(sw::_2),  seq(sw::_3),  seq(sw::_4), seq(sw::_5), seq(sw::_6), seq(sw::_7), seq(sw::_8), seq(sw::_9), seq(sw::DOT), seq(sw::NEG), seq(sw::POW), seq(sw::CX), seq(sw::Bx), seq(sw::F,sw::Bx),
  seq(sw::ADD), seq(sw::SUB), seq(sw::MUL), seq(sw::DIV), seq(sw::XY), seq(sw::F,sw::DOT), seq(sw::F,sw::_5), seq(sw::F,sw::_1), seq(sw::F,sw::_2), seq(sw::F,sw::_4), seq(sw::F,sw::_5), seq(sw::F,sw::_6), seq(sw::F,sw::_7), seq(sw::F,sw::_8), seq(sw::F,sw::_9), seqNOP,
  seq(sw::F,sw::ADD),seq(sw::F,sw::SUB),seq(sw::F,sw::MUL),seq(sw::F,sw::DIV),seq(sw::F,sw::XY),seq(sw::F,sw::DOT),seq(sw::K,sw::ADD),seq(sw::K,sw::SUB),seq(sw::K,sw::MUL),seq(sw::K,sw::DIV),seq(sw::K,sw::XY),seqNOP,seqNOP,seqNOP,seqNOP,seqNOP,
  seq(sw::K,sw::_3),seq(sw::K,sw::_4),seq(sw::K,sw::_5),seq(sw::K,sw::_6),seq(sw::K,sw::_7),seq(sw::K,sw::_8),seq(sw::K,sw::_9),seq(sw::K,sw::DOT),seq(sw::K,sw::NEG),seq(sw::K,sw::POW),seq(sw::K,sw::CX),seq(sw::K,sw::Bx),seqNOP,seqNOP,seqNOP,seqNOP,
  seq(sw::xP,sw::_0),seq(sw::xP,sw::_1),seq(sw::xP,sw::_2),seq(sw::xP,sw::_3),seq(sw::xP,sw::_4),seq(sw::xP,sw::_5),seq(sw::xP,sw::_6),seq(sw::xP,sw::_7),seq(sw::xP,sw::_8),seq(sw::xP,sw::_9),seq(sw::xP,sw::DOT),seq(sw::xP,sw::NEG),seq(sw::xP,sw::POW),seq(sw::xP,sw::CX),seq(sw::xP,sw::Bx),seqNOP,
  seq(sw::RUN),seq(sw::JP),seq(sw::RET),seq(sw::JSR),seqNOP,seq(sw::K,sw::_1),seq(sw::K,sw::_2),seq(sw::F,sw::RUN),seq(sw::F,sw::JP),seq(sw::F,sw::RET),seq(sw::F,sw::JSR),seq(sw::F,sw::xP),seq(sw::F,sw::BK),seq(sw::F,sw::Px),seq(sw::F,sw::FW),seqNOP,
  seq(sw::Px,sw::_0),seq(sw::Px,sw::_1),seq(sw::Px,sw::_2),seq(sw::Px,sw::_3),seq(sw::Px,sw::_4),seq(sw::Px,sw::_5),seq(sw::Px,sw::_6),seq(sw::Px,sw::_7),seq(sw::Px,sw::_8),seq(sw::Px,sw::_9),seq(sw::Px,sw::DOT),seq(sw::Px,sw::NEG),seq(sw::Px,sw::POW),seq(sw::Px,sw::CX),seq(sw::Px,sw::Bx),seqNOP,
  seq(sw::K,sw::RUN,sw::_0),seq(sw::K,sw::RUN,sw::_1),seq(sw::K,sw::RUN,sw::_2),seq(sw::K,sw::RUN,sw::_3),seq(sw::K,sw::RUN,sw::_4),seq(sw::K,sw::RUN,sw::_5),seq(sw::K,sw::RUN,sw::_6),seq(sw::K,sw::RUN,sw::_7),
    seq(sw::K,sw::RUN,sw::_8),seq(sw::K,sw::RUN,sw::_9),seq(sw::K,sw::RUN,sw::DOT),seq(sw::K,sw::RUN,sw::NEG),seq(sw::K,sw::RUN,sw::POW),seq(sw::K,sw::RUN,sw::CX),seq(sw::K,sw::RUN,sw::Bx),seqNOP,
  seq(sw::K,sw::JP,sw::_0),seq(sw::K,sw::JP,sw::_1),seq(sw::K,sw::JP,sw::_2),seq(sw::K,sw::JP,sw::_3),seq(sw::K,sw::JP,sw::_4),seq(sw::K,sw::JP,sw::_5),seq(sw::K,sw::JP,sw::_6),seq(sw::K,sw::JP,sw::_7),
    seq(sw::K,sw::JP,sw::_8),seq(sw::K,sw::JP,sw::_9),seq(sw::K,sw::JP,sw::DOT),seq(sw::K,sw::JP,sw::NEG),seq(sw::K,sw::JP,sw::POW),seq(sw::K,sw::JP,sw::CX),seq(sw::K,sw::JP,sw::Bx),seqNOP,
  seq(sw::K,sw::RET,sw::_0),seq(sw::K,sw::RET,sw::_1),seq(sw::K,sw::RET,sw::_2),seq(sw::K,sw::RET,sw::_3),seq(sw::K,sw::RET,sw::_4),seq(sw::K,sw::RET,sw::_5),seq(sw::K,sw::RET,sw::_6),seq(sw::K,sw::RET,sw::_7),
    seq(sw::K,sw::RET,sw::_8),seq(sw::K,sw::RET,sw::_9),seq(sw::K,sw::RET,sw::DOT),seq(sw::K,sw::RET,sw::NEG),seq(sw::K,sw::RET,sw::POW),seq(sw::K,sw::RET,sw::CX),seq(sw::K,sw::RET,sw::Bx),seqNOP,
  seq(sw::K,sw::JSR,sw::_0),seq(sw::K,sw::JSR,sw::_1),seq(sw::K,sw::JSR,sw::_2),seq(sw::K,sw::JSR,sw::_3),seq(sw::K,sw::JSR,sw::_4),seq(sw::K,sw::JSR,sw::_5),seq(sw::K,sw::JSR,sw::_6),seq(sw::K,sw::JSR,sw::_7),
    seq(sw::K,sw::JSR,sw::_8),seq(sw::K,sw::JSR,sw::_9),seq(sw::K,sw::JSR,sw::DOT),seq(sw::K,sw::JSR,sw::NEG),seq(sw::K,sw::JSR,sw::POW),seq(sw::K,sw::JSR,sw::CX),seq(sw::K,sw::JSR,sw::Bx),seqNOP,
  seq(sw::K,sw::xP,sw::_0),seq(sw::K,sw::xP,sw::_1),seq(sw::K,sw::xP,sw::_2),seq(sw::K,sw::xP,sw::_3),seq(sw::K,sw::xP,sw::_4),seq(sw::K,sw::xP,sw::_5),seq(sw::K,sw::xP,sw::_6),seq(sw::K,sw::xP,sw::_7),
    seq(sw::K,sw::xP,sw::_8),seq(sw::K,sw::xP,sw::_9),seq(sw::K,sw::xP,sw::DOT),seq(sw::K,sw::xP,sw::NEG),seq(sw::K,sw::xP,sw::POW),seq(sw::K,sw::xP,sw::CX),seq(sw::K,sw::xP,sw::Bx),seqNOP,
  seq(sw::K,sw::BK,sw::_0),seq(sw::K,sw::BK,sw::_1),seq(sw::K,sw::BK,sw::_2),seq(sw::K,sw::BK,sw::_3),seq(sw::K,sw::BK,sw::_4),seq(sw::K,sw::BK,sw::_5),seq(sw::K,sw::BK,sw::_6),seq(sw::K,sw::BK,sw::_7),
    seq(sw::K,sw::BK,sw::_8),seq(sw::K,sw::BK,sw::_9),seq(sw::K,sw::BK,sw::DOT),seq(sw::K,sw::BK,sw::NEG),seq(sw::K,sw::BK,sw::POW),seq(sw::K,sw::BK,sw::CX),seq(sw::K,sw::BK,sw::Bx),seqNOP,
  seq(sw::K,sw::Px,sw::_0),seq(sw::K,sw::Px,sw::_1),seq(sw::K,sw::Px,sw::_2),seq(sw::K,sw::Px,sw::_3),seq(sw::K,sw::Px,sw::_4),seq(sw::K,sw::Px,sw::_5),seq(sw::K,sw::Px,sw::_6),seq(sw::K,sw::Px,sw::_7),
    seq(sw::K,sw::Px,sw::_8),seq(sw::K,sw::Px,sw::_9),seq(sw::K,sw::Px,sw::DOT),seq(sw::K,sw::Px,sw::NEG),seq(sw::K,sw::Px,sw::POW),seq(sw::K,sw::Px,sw::CX),seq(sw::K,sw::Px,sw::Bx),seqNOP,
  seq(sw::K,sw::FW,sw::_0),seq(sw::K,sw::FW,sw::_1),seq(sw::K,sw::FW,sw::_2),seq(sw::K,sw::FW,sw::_3),seq(sw::K,sw::FW,sw::_4),seq(sw::K,sw::FW,sw::_5),seq(sw::K,sw::FW,sw::_6),seq(sw::K,sw::FW,sw::_7),
    seq(sw::K,sw::FW,sw::_8),seq(sw::K,sw::FW,sw::_9),seq(sw::K,sw::FW,sw::DOT),seq(sw::K,sw::FW,sw::NEG),seq(sw::K,sw::FW,sw::POW),seq(sw::K,sw::FW,sw::CX),seq(sw::K,sw::FW,sw::Bx),seqNOP
};

const   u8                  CR = 0x0D;
const   u8                  NL = 0x0A;
static  constexpr usize     MAX_INPUT_CHAR = terminal_core::INPUT_CAPACITY;

extern  class_disassm_mk61  disassembler;
extern  MK61Display         lcd;
extern  void DFU_enable(void);



// ====== Диспетчер команд: имя -> id через CRC-8 индекс ======
// Первое слово строки хешируется CRC-8 (полином 0x31) и служит входом в
// 256-байтный индекс, построенный на этапе компиляции. Совпадение хеша
// обязательно подтверждается сравнением полного имени: иначе опечатка с тем же
// CRC молча выполнила бы чужую команду (среди команд есть dfu и sera).
// Коллизии хешей разрешаются линейным пробированием при построении индекса,
// поэтому переименовывать команды при совпадении CRC не требуется.

struct TerminalCommand {
  const char* name;
  u8          id;
  const char* desc;
};

// Единственный источник истины: имя <-> id <-> описание для help.
// Добавление команды: строка здесь + case в execute().
static constexpr TerminalCommand terminal_commands[] = {
  { "ver",     CMD_VERSION,       "firmware version" },
  { "help",    CMD_HELP,          "this list" },
  { "history", CMD_HISTORY,       "recent command lines" },
  { "list",    CMD_LIST,          "program memory in hex, vertical" },
  { "dump",    CMD_DUMP,          "program memory in hex, horizontal" },
  { "pub",     CMD_PUB,           "program listing in publication format" },
  { "lasm",    CMD_LASM,          "disassemble program memory" },
  { "isa",     CMD_ISA,           "list of assembler mnemonics" },
  { "asm",     CMD_ASM,           "asm [TA] <mnemonics> - assemble line" },
  { "ins",     CMD_INS,           "ins <step> <opcode> - insert into program" },
  { "hin",     CMD_HIN,           "hin <addr> <hex> - write program memory" },
  { "hout",    CMD_HOUT,          "program memory as hin lines" },
  { "reg",     CMD_REG_DUMP,      "dump R0..RE registers" },
  { "stk",     CMD_STACK,         "dump stack X,Y,Z,T,X1" },
  { "poke",    CMD_POKE,          "poke <X|Y|Z|T> <1.25e02> - write stack" },
  { "1302",    CMD_1302,          "dump K145IK1302 R register" },
  { "ring",    CMD_RING,          "dump ring M memory" },
  { "kbd",     CMD_KBD,           "kbd <hex scancode> - press key" },
  { "led",     CMD_LED,           "led <0|1>[,ms,0|1,...] - LED pattern" },
  { "beep",    CMD_BEEP,          "beep <Hz>,<ms>[,...] - sound pattern" },
  { "if",      CMD_IF,            "if <reg><op><val> <cmd> - conditional" },
  { "cmd",     CMD_CMD,           "cmd <hex opcode> - press keys of opcode" },
  { "run",     CMD_RUN,           "run [name] - run program / stored file" },
  { "open",    CMD_OPEN,          "open <name> - run stored file" },
  { "save",    CMD_SAVE,          "save <slot|path.m61> - store program (Y/y)" },
  { "load",    CMD_LOAD,          "load <slot|path.m61> - load program" },
  { "pwd",     CMD_FS_PWD,        "print current storage directory" },
  { "cd",      CMD_FS_CD,         "cd [path] - change storage directory" },
  { "ls",      CMD_FS_LIST,       "ls [path] - list one storage directory" },
  { "dir",     CMD_FS_LIST,       "alias for ls" },
  { "mkdir",   CMD_FS_MKDIR,      "mkdir [-p] <path> - create directories" },
  { "mv",      CMD_FS_MOVE,       "mv <source> <destination>" },
  { "rm",      CMD_FS_REMOVE,     "rm [-r] <path> - remove file or tree" },
  { "del",     CMD_FS_REMOVE,     "alias for rm" },
  { "rmdir",   CMD_FS_RMDIR,      "rmdir <path> - remove empty directory" },
  { "df",      CMD_FS_STAT,       "show C5 capacity and node quota" },
  { "smap",    CMD_SMAP,          "numeric M1 slot occupancy map" },
  { "sdir",    CMD_DIR,           "list numeric M1 slots" },
  { "snm",     CMD_RENAME,        "snm <slot> <name> - rename slot" },
  { "sdel",    CMD_DEL_SLOT,      "sdel <slot> - delete numeric M1 slot (Y/y)" },
  { "sera",    CMD_ERASE_STORAGE, "erase all slots (Y/y)" },
  { "clr",     CMD_CLEAR,         "clear program memory (Y/y)" },
  { "vlog",    CMD_VFAT_LOG,      "dump virtual FAT trace log" },
  { "fsls",    CMD_FS_LIST,       "alias for ls" },
  { "fsrm",    CMD_FS_REMOVE,     "alias for rm" },
  { "fsstat",  CMD_FS_STAT,       "alias for df" },
  { "fsclean", CMD_FS_CLEAN,      "remove all zero-length store entries" },
  { "disa",    CMD_DISASM,        "toggle disassembler on display" },
  { "rst",     CMD_RESET,         "reboot MCU (confirm on device)" },
  { "dfu",     CMD_DFU,           "enter DFU bootloader" },
};
static constexpr usize TERMINAL_COMMAND_COUNT = sizeof(terminal_commands) / sizeof(terminal_commands[0]);

constexpr u8 terminal_crc8(const char* str, usize len) {
  u8 crc = 0;
  for(usize i = 0; i < len; i++) {
    crc ^= (u8) str[i];
    for(u8 bit = 0; bit < 8; bit++) crc = (crc & 0x80) ? (u8) ((crc << 1) ^ 0x31) : (u8) (crc << 1);
  }
  return crc;
}

constexpr usize terminal_name_len(const char* s) {
  usize len = 0;
  while(s[len] != 0) len++;
  return len;
}

struct TerminalCommandIndex {
  u8 slot[256];  // 1 + номер в terminal_commands; 0 - пусто
};

constexpr TerminalCommandIndex make_terminal_command_index(void) {
  TerminalCommandIndex index = {};
  for(usize n = 0; n < TERMINAL_COMMAND_COUNT; n++) {
    const char* name = terminal_commands[n].name;
    usize probe = terminal_crc8(name, terminal_name_len(name));
    while(index.slot[probe] != 0) probe = (probe + 1) & 0xFF;
    index.slot[probe] = (u8) (n + 1);
  }
  return index;
}
static constexpr TerminalCommandIndex terminal_command_index = make_terminal_command_index();

// Доказательство на этапе компиляции: каждая команда таблицы достижима через
// индекс и разрешается именно в свой id. Ловит и переполнение кластера
// пробирования, и случайный дубль имени - прошивка с недостижимой командой
// просто не соберётся.
constexpr bool terminal_index_resolves_all(void) {
  for(usize n = 0; n < TERMINAL_COMMAND_COUNT; n++) {
    const char* name = terminal_commands[n].name;
    const usize len = terminal_name_len(name);
    usize probe = terminal_crc8(name, len);
    bool resolved = false;
    while(true) {
      const u8 slot = terminal_command_index.slot[probe];
      if(slot == 0) break; // пустая ячейка - имя в индексе не найдено
      const TerminalCommand& cmd = terminal_commands[slot - 1];
      bool equal = true;
      for(usize i = 0; i <= len; i++) {
        if(cmd.name[i] != name[i]) { equal = false; break; }
      }
      if(equal) {
        resolved = (cmd.id == terminal_commands[n].id);
        break;
      }
      probe = (probe + 1) & 0xFF;
    }
    if(!resolved) return false;
  }
  return true;
}
static_assert(terminal_index_resolves_all(), "terminal command index: a command is unreachable (CRC cluster or duplicate name)");

static const char* terminal_skip_spaces(const char* p) {
  while(p != NULL && (*p == ' ' || *p == '\t')) p++;
  return p;
}

static bool terminal_arg_end(const char* p) {
  p = terminal_skip_spaces(p);
  return p == NULL || *p == 0 || *p == '\r' || *p == '\n';
}

static bool terminal_parse_slot_arg(const char* args, usize& slot_out) {
  args = terminal_skip_spaces(args);
  if(args == NULL || *args < '0' || *args > '9') return false;

  usize slot = 0;
  const char* p = args;
  while(*p >= '0' && *p <= '9') {
    slot = slot * 10 + (usize) (*p - '0');
    if(slot > MAX_SLOT_FOR_PROGRAM) return false;
    p++;
  }
  if(!terminal_arg_end(p)) return false;
  slot_out = slot;
  return true;
}

static bool terminal_copy_arg(char* out, usize capacity, const char* args) {
  args = terminal_skip_spaces(args);
  if(out == NULL || capacity == 0 || args == NULL) return false;
  usize len = 0;
  while(args[len] != 0 && args[len] != '\r' && args[len] != '\n') len++;
  while(len > 0 && (args[len - 1] == ' ' || args[len - 1] == '\t')) len--;
  if(len == 0 || len >= capacity) return false;
  memcpy(out, args, len);
  out[len] = 0;
  return true;
}

static bool terminal_single_token(const char* args, char* out,
                                  usize capacity) {
  const char* cursor = args;
  return terminal_core::parse_token(cursor, out, capacity) &&
         terminal_core::at_end(cursor);
}

static void terminal_path_error(const char* operation,
                                storage_path::Status status) {
  Serial.print(operation);
  Serial.print(": ");
  Serial.println(storage_path::status_text(status));
}

static void terminal_print_fs_entry(const program_store::Entry& entry) {
  char name[storage_path::VISIBLE_NAME_SIZE];
  if(!storage_path::visible_name(entry, name, sizeof(name))) {
    Serial.println("?\t<invalid entry>");
    return;
  }
  if(entry.kind == program_store::NodeKind::DIRECTORY) {
    Serial.print("d\t");
    Serial.print(name);
    Serial.println('/');
  } else {
    Serial.print("f\t");
    Serial.print(entry.data_len);
    Serial.print(" B\t");
    Serial.println(name);
  }
}

// Команда по первому слову строки: CMD_xxx или CMD_UNKNOWN.
static u8 terminal_command_lookup(const u8* line) {
  usize len = 0;
  while(line[len] != 0 && !terminal_core::is_space((char) line[len])) len++;
  if(len == 0) return CMD_UNKNOWN;

  // Спец-формы, не разбираемые по первому слову (длина ограждает от чтения
  // остатков предыдущей команды за нулём-терминатором):
  if(len == 3 && line[0] == 'R' && line[2] == '=' && terminal_core::is_space((char) line[3])) return CMD_REG_SET; // R0= <значение>
  if(len >= 4 && line[0] == 's' && line[1] == 'e' && line[2] == 't' && line[3] == '$') return CMD_SET_CODE;  // set$<hex>

  usize probe = terminal_crc8((const char*) line, len);
  while(true) {
    const u8 slot = terminal_command_index.slot[probe];
    if(slot == 0) return CMD_UNKNOWN;
    const TerminalCommand& cmd = terminal_commands[slot - 1];
    if(strncmp((const char*) line, cmd.name, len) == 0 && cmd.name[len] == 0) return cmd.id;
    probe = (probe + 1) & 0xFF;
  }
}

const char ISA_61[] = 
"0,1,2,3,4,5,6,7,8,9,dot,neg,pow10,clr,push,preX,\
add,sub,mul,div,swap,e10,exp,lg,ln,asin,acos,atg,sin,cos,tg,?,\
pi,sqrt,sqr,rec,pow,rot,toM,?,?,?,toMS,?,?,?,?,?,\
inMS,mod,sgn,inM,int,frc,max,and,or,xor,not,rnd,?,?,?,?,\
sto0,sto1,sto2,sto3,sto4,sto5,sto6,sto7,sto8,sto9,stoA,stoB,stoC,stoD,stoE,?,\
hlt,jmp,ret,call,nop,?,?,jz,rpt2,jl,rpt3,rpt1,jme,rpt0,jnz,?,\
ld0,ld1,ld2,ld3,ld4,ld5,ld6,ld7,ld8,ld9,ldA,ldB,ldC,ldD,ldE,?,\
jz[0],jz[1],jz[2],jz[3],jz[4],jz[5],jz[6],jz[7],jz[8],jz[9],jz[A],jz[B],jz[C],jz[D],jz[E],?,\
jmp[0],jmp[1],jmp[2],jmp[3],jmp[4],jmp[5],jmp[6],jmp[7],jmp[8],jmp[9],jmp[A],jmp[B],jmp[C],jmp[D],jmp[E],?,\
jlz[0],jlz[1],jlz[2],jlz[3],jlz[4],jlz[5],jlz[6],jlz[7],jlz[8],jlz[9],jlz[A],jlz[B],jlz[C],jlz[D],jlz[E],?,\
call[0],call[1],call[2],call[3],call[4],call[5],call[6],call[7],call[8],call[9],call[A],call[B],call[C],call[D],call[E],?,\
sto[0],sto[1],sto[2],sto[3],sto[4],sto[5],sto[6],sto[7],sto[8],sto[9],sto[A],sto[B],sto[C],sto[D],sto[E],?,\
jme[0],jme[1],jme[2],jme[3],jme[4],jme[5],jme[6],jme[7],jme[8],jme[9],jme[A],jme[B],jme[C],jme[D],jme[E],?,\
ld[0],ld[1],ld[2],ld[3],ld[4],ld[5],ld[6],ld[7],ld[8],ld[9],ld[A],ld[B],ld[C],ld[D],ld[E],?,\
jnz[0],jnz[1],jnz[2],jnz[3],jnz[R4],jnz[5],jnz[6],jnz[7],jnz[8],jnz[9],jnz[A],jnz[B],jnz[C],jnz[D],jnz[E]";

class class_terminal {
  private:
    enum class mnemo_type {ISA_61, ISA_CLASSIC};
    static constexpr usize MAX_LEN_CLASSIC_MNEMO = 8; // максимальная длинна классической инструкции

    const char* const ISA_CLASSIC_61 =
"0,1,2,3,4,5,6,7,8,9,.,/-/,В\317,CX,B^,Bx,+,-,*,:,XY,F10^x,Fe^x,Flg,Fln,Fasin,Facos,Fatg,Fsin,Fcos,Ftg,?,\
\317\xE8,V\"\"\",Fx^2,F1/x,Fx^y,(),Ko->',?,?,?,Ko->'\",?,?,?,?,?,Ko<-'\",|x|,3H,Ko<-',K[x],K{x},Kmax,K^,Kv,K(+),\310HB,C\327,?,Ko->'\",?,?,\
X->\3170,X->\3171,X->\3172,X->\3173,X->\3174,X->\3175,X->\3176,X->\3177,X->\3178,X->\3179,X->\317A,X->\317B,X->\317C,X->\317\304,X->\317E,?,\
C/\317,\301/\317,B/O,\317/\317,HO\317,?,?,Fx\2070,FL2,Fx>=0,FL3,FL1,Fx<0,FL0,Fx=0,?,\
\317->X0,\317->X1,\317->X2,\317->X3,\317->X4,\317->X5,\317->X6,\317->X7,\317->X8,\317->X9,\317->XA,\317->XB,\317->XC,\317->X\xC4,\317->XE,?,\
Kx\2070 0,Kx\2070 1,Kx\2070 2,Kx\2070 3,Kx\2070 4,Kx\2070 5,Kx\2070 6,Kx\2070 7,Kx\2070 8,Kx\2070 9,Kx\2070 A,Kx\2070 B,Kx\2070 C,Kx\2070 \304,Kx\2070 E,?,\
K\301\3170,K\301\3171,K\301\3172,K\301\3173,K\301\3174,K\301\3175,K\301\3176,K\301\3177,K\301\3178,K\301\3179,K\301\317A,K\301\317B,K\301\317C,K\301\317\304,K\301\317E,?,\
Kx>=0 0,Kx>=0 1,Kx>=0 2,Kx>=0 3,Kx>=0 4,Kx>=0 5,Kx>=0 6,Kx>=0 7,Kx>=0 8,Kx>=0 9,Kx>=0 A,Kx>=0 B,Kx>=0 C,Kx>=0 \304,Kx>=0 E,?,\
К\317\3170,К\317\3171,К\317\3172,К\317\3173,К\317\3174,К\317\3175,К\317\3176,К\317\3177,К\317\3178,К\317\3179,К\317\317A,К\317\317B,К\317\317C,К\317\317\304,К\317\317E,?,\
KX->\3170,KX->\3171,KX->\3172,KX->\3173,KX->\3174,KX->\3175,KX->\3176,KX->\3177,KX->\3178,KX->\3179,KX->\317A,KX->\317B,KX->\317C,KX->\317\304,KX->\317E,?,\
Kx<0 0,Kx<0 1,Kx<0 2,Kx<0 3,Kx<0 4,Kx<0 5,Kx<0 6,Kx<0 7,Kx<0 8,Kx<0 9,Kx<0 A,Kx<0 B,Kx<0 C,Kx<0 \304,Kx<0 E,?,\
K\317->X0,K\317->X1,K\317->X2,K\317->X3,K\317->X4,K\317->X5,K\317->X6,K\317->X7,K\317->X8,K\317->XA,K\317->XB,K\317->XC,K\317->X\304,K\317->XE,?,\
Kx=0 0,Kx=0 1,Kx=0 2,Kx=0 3,Kx=0 4,Kx=0 5,Kx=0 6,Kx=0 7,Kx=0 8,Kx=0 9,Kx=0 A,Kx=0 B,Kx=0 C,Kx=0 \304,Kx=0 E,?";

    isize   AT;
    u8      pending_confirmation_cmd;
    isize   nSlot;
    bool    input_overflow;
    char    pending_save_name[program_store::NAME_SIZE];
    u16     pending_save_parent_id;
    u16     current_directory;

    // Аргументы скриптового действия переживают восстановление input_buffer:
    // script_args_ptr указывает внутрь буфера строки, поэтому перед возвратом
    // из execute_script_line() они переносятся сюда. Скрипт один в момент
    // времени - хранилище общее (static).
    static inline char script_args_storage[MAX_INPUT_CHAR];

    // Буфер строки один на прошивку (C++17 inline): экземпляров терминала два
    // (интерактивный и скриптовый m61), но раньше из-за слияния weak-методов
    // линкером реально использовалась одна копия, вторая была мёртвым грузом.
    static inline u8 input_buffer[MAX_INPUT_CHAR];

    // ====== История команд: байтовое кольцо + каталог записей ======
    // Каталог хранит позицию и длину каждой записи, поэтому доступ по номеру
    // (стрелки вверх/вниз) O(1) и нет сдвигов памяти при вытеснении старых.
    static constexpr u16 HISTORY_TEXT_SIZE = 256;
    static constexpr u8  HISTORY_DEPTH     = 8;

    // static inline: серийный ввод ведёт только интерактивный экземпляр,
    // держать копию истории в каждом экземпляре (script_terminal) - потеря ОЗУ.
    static inline char  hist_text[HISTORY_TEXT_SIZE];
    static inline u16   hist_start[HISTORY_DEPTH];
    static inline u8    hist_length[HISTORY_DEPTH];
    static inline u8    hist_head;                    // номер самой старой записи в каталоге
    static inline u8    hist_count;
    static inline u16   hist_used;                    // занято байт в текстовом кольце
    static inline u16   hist_write;                   // позиция записи в текстовом кольце
    static inline i8    hist_nav;                     // -1 - не в истории, 0 - самая новая
    static inline u8    esc_state;                    // разбор escape-последовательностей
    static inline u8    prev_terminator;              // съедание второго символа пары CRLF
    static inline u8    saved_line[MAX_INPUT_CHAR];   // строка, редактируемая до входа в историю
    static inline usize saved_len;

    void history_drop_oldest(void) {
      hist_used -= hist_length[hist_head];
      hist_head = (u8) ((hist_head + 1) % HISTORY_DEPTH);
      hist_count--;
    }

    void history_entry_read(u8 slot, u8* out) {
      const u16 start = hist_start[slot];
      for(u8 i = 0; i < hist_length[slot]; i++) out[i] = (u8) hist_text[(u16) ((start + i) % HISTORY_TEXT_SIZE)];
    }

    bool history_entry_equals(u8 slot, const u8* line, usize len) {
      if(hist_length[slot] != len) return false;
      const u16 start = hist_start[slot];
      for(usize i = 0; i < len; i++) {
        if((u8) hist_text[(u16) ((start + i) % HISTORY_TEXT_SIZE)] != line[i]) return false;
      }
      return true;
    }

    void history_add(const u8* line, usize len) {
      if(len == 0 || len >= HISTORY_TEXT_SIZE) return;
      // подряд идущие одинаковые команды не дублируем
      if(hist_count > 0 && history_entry_equals((u8) ((hist_head + hist_count - 1) % HISTORY_DEPTH), line, len)) return;

      while(hist_count > 0 && (hist_used + len > HISTORY_TEXT_SIZE || hist_count >= HISTORY_DEPTH)) history_drop_oldest();

      const u8 slot = (u8) ((hist_head + hist_count) % HISTORY_DEPTH);
      hist_start[slot] = hist_write;
      hist_length[slot] = (u8) len;
      for(usize i = 0; i < len; i++) {
        hist_text[hist_write] = (char) line[i];
        hist_write = (u16) ((hist_write + 1) % HISTORY_TEXT_SIZE);
      }
      hist_used += len;
      hist_count++;
    }

    void history_print(void) {
      if(hist_count == 0) {
        Serial.println("History is empty.");
        return;
      }
      u8 line[MAX_INPUT_CHAR];
      for(u8 i = 0; i < hist_count; i++) {
        const u8 slot = (u8) ((hist_head + i) % HISTORY_DEPTH);
        history_entry_read(slot, line);
        Serial.print("  ");
        Serial.print(i + 1);
        Serial.print(": ");
        Serial.write(line, hist_length[slot]);
        Serial.println();
      }
    }

    void print_prompt(void) {
      char path[64];
      if(storage_path::format_directory(current_directory, path,
                                        sizeof(path)) ==
         storage_path::Status::OK) Serial.print(path);
      else Serial.print("...");
      Serial.print("> ");
    }

    void redraw_input_line(usize old_columns) {
      Serial.write('\r');
      print_prompt();
      Serial.write(input_buffer, recive_pos);
      const usize columns = utf8_view::codepoint_count(
          (const char*) input_buffer, (u16) recive_pos);
      for(usize i = columns; i < old_columns; i++) Serial.write(' ');
      for(usize i = columns; i < old_columns; i++) Serial.write('\b');
    }

    void history_recall(i8 nav) {
      const usize old_columns = utf8_view::codepoint_count(
          (const char*) input_buffer, (u16) recive_pos);
      if(nav < 0) {  // выход из истории: вернуть редактируемую строку
        memcpy(input_buffer, saved_line, saved_len);
        recive_pos = saved_len;
      } else {
        const u8 slot = (u8) ((hist_head + hist_count - 1 - nav) % HISTORY_DEPTH);
        history_entry_read(slot, input_buffer);
        recive_pos = hist_length[slot];
      }
      hist_nav = nav;
      redraw_input_line(old_columns);
    }

    void history_key_up(void) {
      if(hist_nav + 1 >= (i8) hist_count) return;
      if(hist_nav < 0) {  // запомнить строку, набранную до входа в историю
        memcpy(saved_line, input_buffer, recive_pos);
        saved_len = recive_pos;
      }
      history_recall((i8) (hist_nav + 1));
    }

    void history_key_down(void) {
      if(hist_nav < 0) return;
      history_recall((i8) (hist_nav - 1));
    }

    void print_help(void) {
      Serial.println("Available commands:");
      for(usize i = 0; i < TERMINAL_COMMAND_COUNT; i++) {
        if(terminal_commands[i].desc == NULL) continue;
        Serial.print("  ");
        Serial.print(terminal_commands[i].name);
        for(usize pad = strlen(terminal_commands[i].name); pad < 8; pad++) Serial.write(' ');
        Serial.println(terminal_commands[i].desc);
      }
      Serial.println("  R<r>=   R<r>= <value> - write register, e.g. R0= 3.14");
      Serial.println("  set$    set$<addr> <hex> - write program memory");
    }

    // args обычно указывает внутрь input_buffer, который execute_script_line()
    // восстановит перед возвратом, поэтому результат ссылается на отдельное
    // хранилище.
    terminal_protocol::Result script_action(terminal_protocol::ResultKind action, const char* args) {
      usize len = 0;
      while(args[len] != 0 && len < sizeof(script_args_storage) - 1) {
        script_args_storage[len] = args[len];
        len++;
      }
      script_args_storage[len] = 0;
      recive_pos = 0;
      return terminal_protocol::Result::action(action, script_args_storage);
    }

    bool input_can_append(void) const {
      return terminal_core::input_can_append(recive_pos);
    }

    void list_mk61_code_page(void) {
      u8 code_page[core_61::CODE_PAGE_BUFFER_SIZE] = {};
      core_61::get_code_page(&code_page[0]);
      const usize program_steps = core_61::program_steps();

      for(int j = 0; j < 16; j++) {
        for(usize i = j; i < program_steps; i += 16) {
          if(i > 99) {
            Serial.write('A');
            Serial.print(i-100);
          } else {
            if(i < 10) Serial.write('0');
            Serial.print(i);
          }
          Serial.print(". ");
          if(code_page[i] < 16) Serial.write('0');
          Serial.print(code_page[i], HEX); 
          Serial.print("  ");
        }
        Serial.println();
      }
    }

    void dump_mk61_code_page(void) {
      u8 code_page[core_61::CODE_PAGE_BUFFER_SIZE] = {};
      core_61::get_code_page(&code_page[0]);
      const isize program_steps = (isize) core_61::program_steps();
      isize j = 0;
      do {
        for(isize i = 0; i < 16; i++) {
          Serial_write_hex(code_page[j]);
          Serial.print("  ");
          j++;
          if ( j >= program_steps ) break;
        }
        Serial.println();
      } while (j < program_steps);
    }

    char* ISA_61_code(u8 opcode, char* text) {
      isize comma_count = opcode;
      isize i = 0;

      for(u8 symbol : ISA_61) {
        if(symbol == 0) break;
        if(symbol == ',') {
          comma_count--;
        } else if(comma_count == 0)
          text[i++] = symbol;
      }
      text[i] = 0;
      return text;
    }

    char* ISA_CLASSIC_61_code(u8 opcode, char* text) {
      isize comma_count = opcode;
      isize i = 0;

      for(const char* p = ISA_CLASSIC_61; *p != 0; p++) {
        const u8 symbol = (u8) *p;
        if(symbol == 0) break;
        if(symbol == ',') {
          comma_count--;
        } else if(comma_count == 0)
          text[i++] = symbol;
      }
      text[i] = 0;
      return text;
    }

    void /* __attribute__((optimize("O0"))) */ output_version(void) {
      Serial.print("sizeof Serial "); Serial.println(sizeof(HardwareSerial));
      Serial.print(MODEL);
      Serial.print(" ver. ");
      Serial.print(__DATE__);
      Serial.write('(');
      Serial.print(__TIME__);
      Serial.println(')');
    }

    void DumpRegisters(void) {
     // -0.12345678 -9A (14)
      char buffer[15];

      for(int i=0; i < 15; i++) {
        Serial.write('R');
        Serial.print(i, HEX);
        Serial.print(" = ");
        MK61Emu_ReadRegister(i, buffer, terminal_symbols);
        //Serial.write((char*) &buffer[0], 3); //Serial.write(buffer[1]); Serial.write('.'); 
        Serial.println((char*) &buffer);
      }

      Serial.print("IP: "); Serial.println(core_61::get_IP());
    }

    void Dump1302(void) {
      char buff[43];
      MK61Emu_get_1302_R(&buff[0]);
      Serial.println(buff);
    }

    void  print_address_as_MK61(usize addr) {
      if(addr > 99) {
        Serial.write('A');
        Serial.print(addr-100);
      } else {
        if(addr < 10) Serial.write('0');
        Serial.print(addr);
      }
    }

  public:
    usize recive_pos;

    class_terminal(void)
      : AT(0), pending_confirmation_cmd(CMD_UNKNOWN), nSlot(-1),
        input_overflow(false), pending_save_parent_id(program_store::ROOT_ID),
        current_directory(program_store::ROOT_ID), recive_pos(0) {
      pending_save_name[0] = 0;
    }

    void reset_command_state(void) {
      AT                    = 0;
      recive_pos            = 0;
      pending_confirmation_cmd = CMD_UNKNOWN;
      nSlot                 = -1;
      input_overflow        = false;
      pending_save_name[0]  = 0;
      pending_save_parent_id = program_store::ROOT_ID;
    }

    // История и редактор строки общие (static): сбрасываются только при
    // старте интерактивного терминала, скриптовый init их не трогает.
    void reset_line_editor(void) {
      esc_state             = 0;
      prev_terminator       = 0;
      hist_nav              = -1;
      saved_len             = 0;
      hist_head             = 0;
      hist_count            = 0;
      hist_used             = 0;
      hist_write            = 0;
    }

    void  init(void) {
      current_directory = program_store::ROOT_ID;
      reset_command_state();
      reset_line_editor();
      Serial.begin(115200);
      delay(1800);
      output_version();
      print_prompt();
    }

    void init_script(void) {
      current_directory = program_store::ROOT_ID;
      reset_command_state();
    }

    terminal_protocol::Result execute_script_line(const char* line);

    void  echo_mk61_stack(void) {
      char cvalue[15];
      cvalue[14] = 0;

      Serial.print("X1 = "); Serial.println(read_stack_register(stack::X1, cvalue, terminal_symbols)); 
      Serial.print("T  = "); Serial.println(read_stack_register(stack::T, cvalue, terminal_symbols)); 
      Serial.print("Z  = "); Serial.println(read_stack_register(stack::Z, cvalue, terminal_symbols)); 
      Serial.print("Y  = "); Serial.println(read_stack_register(stack::Y, cvalue, terminal_symbols)); 
      Serial.print("X  = "); Serial.println(read_stack_register(stack::X, cvalue, terminal_symbols));
      Serial.print("IP =  "); Serial.println(core_61::get_IP());
    }

    void  echo_ISA_61(void) {
      static constexpr isize COLUMN_COUNT = 4;
      static constexpr usize COLUMN_SIZE  = 10;

      u8 opcode = 0;
      usize begin = 0;
      isize column = COLUMN_COUNT;
      // Вывод в 4 колонки, в формате opcode - инструкция 
      for(usize i=0; i < sizeof(ISA_61); i++) {
        if(ISA_61[i] == ',' || ISA_61[i] == 0) { // обнаружен разделитель команд или окончание массива 
          const isize len = i - begin;
          Serial_write_hex(opcode); Serial.write(' '); Serial.write(&ISA_61[begin], len);
          if(column-- <= 0) { // завершим вывод строки, все 4 колонки выведены
            Serial.println();
            column = COLUMN_COUNT;
          } else { // завершим вывод колонки и дополним ее выводом пробелов
            for(usize space_counter = len; space_counter <= COLUMN_SIZE; space_counter++) Serial.write(' ');
          }
          begin = i + 1;
          opcode++;
        }
      }
    }

    void pub_mk61_code_page(void) {
      char op[MAX_LEN_CLASSIC_MNEMO+1];
      u8 code_page[core_61::CODE_PAGE_BUFFER_SIZE] = {};
      core_61::get_code_page(&code_page[0]);
      isize last_cmd_addr = seek_program_END(&code_page[0]);
      const isize program_steps = (isize) core_61::program_steps();
      isize address = 0;
      for (int i=0; i<30; i++) {
        if(i > last_cmd_addr) break;
        for (int ii=0; ii<4; ii++) {
          address = ii*30 + i;
          if(address > last_cmd_addr) break;
          if (address < program_steps) {
            print_address_as_MK61(address); Serial.print(". ");

            const u8 code = code_page[address];
            if(address > 0 && core_61::len_code_command(code_page[address-1]) == 2) {
              Serial_write_hex(code);
              for(usize cnt_space=2; cnt_space < MAX_LEN_CLASSIC_MNEMO + 2; cnt_space++) Serial.print(' ');
            } else {
              Serial.print(ISA_CLASSIC_61_code(code, &op[0])); 
              for(usize ln=strlen(op); ln < MAX_LEN_CLASSIC_MNEMO; ln++) Serial.write(' ');
              Serial.print("  ");
            }
          }
        }
        Serial.println(); 
      }
    }

    void  lasm_mk61_code_page(mnemo_type type) {
      char op[7+1];
      u8 code_page[core_61::CODE_PAGE_BUFFER_SIZE] = {};

      core_61::get_code_page(&code_page[0]);
      isize lastCommand = seek_program_END(&code_page[0]);
      isize j = 0;     
      for (isize i=0; i<30; i++) {
        for (isize ii=0; ii<4; ii++) {
          j = ii*30 + i;
          if (lastCommand > j) {
            Serial.print("00");
            print_address_as_MK61(j);
            const u8 code = code_page[j];
            const u8 code2 = code_page[j+1];
            Serial.write(' '); Serial_write_hex(code); Serial.write(' ');
            if (j > 0){
              if (core_61::len_code_command(code_page[j-1]) == 2) {
                Serial.print("      ");
              } else {
                const char* mnemo = (type == mnemo_type::ISA_CLASSIC)? ISA_CLASSIC_61_code(code, &op[0]) : ISA_61_code(code, &op[0]);
                Serial.print(mnemo); 
                for(usize ln=strlen(op); ln < 6; ln++) Serial.write(' '); 
              }
            } else {
              const char* mnemo = (type == mnemo_type::ISA_CLASSIC)? ISA_CLASSIC_61_code(code, &op[0]) : ISA_61_code(code, &op[0]);
              Serial.print(mnemo); 
              for(usize ln=strlen(op); ln < 6; ln++) Serial.write(' '); 
            }            
            if ( core_61::len_code_command(code) == 2 ) {
              Serial_write_hex(code2); 
              Serial.print("  ");
            } else {
              Serial.print("    ");
            }
            Serial.print("  ");
          }
         }
         if (i > lastCommand) { break; }
         Serial.println();
      }
    }

    bool GetHexString(const char* args) {
      args = terminal_core::skip_spaces(args);
      if(args == NULL) return false;

      usize address = 0;
      for(usize i = 0; i < 4; i++) {
        if(args[i] < '0' || args[i] > '9') {
          Serial.println("Address must contain exactly four decimal digits.");
          return false;
        }
        address = address * 10 + (usize) (args[i] - '0');
      }
      if(!terminal_core::is_space(args[4]) || address >= core_61::MAX_PROGRAM_STEP) {
        Serial.println("BAD address!");
        return false;
      }

      const char* hex = terminal_core::skip_spaces(args + 4);
      if(hex == NULL || terminal_core::is_end(*hex)) {
        Serial.println("Hex byte string is empty.");
        return false;
      }

      u8 code_page[core_61::CODE_PAGE_BUFFER_SIZE] = {};
      core_61::get_code_page(&code_page[0]);
      usize write_at = address;
      while(!terminal_core::is_end(*hex) && !terminal_core::is_space(*hex)) {
        const int high = terminal_core::digit_value(hex[0], 16);
        const int low = terminal_core::digit_value(hex[1], 16);
        if(high < 0 || low < 0) {
          Serial.println("Hex byte string must contain complete byte pairs.");
          return false;
        }
        if(write_at >= core_61::MAX_PROGRAM_STEP) {
          Serial.println("Program memory overflow!");
          return false;
        }
        code_page[write_at++] = (u8) ((high << 4) | low);
        hex += 2;
      }
      if(!terminal_core::at_end(hex)) {
        Serial.println("Unexpected text after hex byte string.");
        return false;
      }

      const bool force_expanded = write_at > core_61::CLASSIC_PROGRAM_STEP;
      apply_program_memory_auto(&code_page[0], core_61::MAX_PROGRAM_STEP, false, force_expanded);
      core_61::set_code_page(&code_page[0]);
      return true;
    }

    void  PutHexString(void) {
      u8 code_page[core_61::CODE_PAGE_BUFFER_SIZE] = {};
      core_61::get_code_page(&code_page[0]);
      isize last_cmd_addr = seek_program_END(&code_page[0]);
      dbgln(MINI, "Last step in programm: ", last_cmd_addr);
      isize j = 0;
      while (j < last_cmd_addr) {
        Serial.print("00"); print_address_as_MK61(j); Serial.write(' ');
        isize jk = 0;
        while (jk < 24) {
          Serial_write_hex(code_page[j]);
          j++; jk++;
          if (j >= last_cmd_addr) break;
        }
        Serial.println();
      }
    }

    bool Assembler(void) {
      const terminal_core::Assembly assembly = terminal_core::parse_assembly(
        command_args(), AT, ISA_61, core_61::MAX_PROGRAM_STEP);
      if(assembly.error != terminal_core::AssemblyError::NONE) {
        ErrorReaction();
        switch(assembly.error) {
          case terminal_core::AssemblyError::EMPTY: Serial.println("Usage: asm [addr] <mnemonics>"); break;
          case terminal_core::AssemblyError::BAD_ADDRESS: Serial.println("BAD address!"); break;
          case terminal_core::AssemblyError::TOO_LONG: Serial.println("Program memory overflow!"); break;
          case terminal_core::AssemblyError::UNKNOWN_MNEMONIC:
            Serial.print("Unexpected token: ");
            Serial.println(assembly.error_at == NULL ? "" : assembly.error_at);
            break;
          case terminal_core::AssemblyError::NONE: break;
        }
        return false;
      }

      // Parse first and commit once: a bad token must leave the program intact.
      u8 code_page[core_61::CODE_PAGE_BUFFER_SIZE] = {};
      core_61::get_code_page(&code_page[0]);
      for(usize i = 0; i < assembly.count; i++) code_page[assembly.address + i] = assembly.opcodes[i];
      apply_program_memory_auto(&code_page[0], core_61::MAX_PROGRAM_STEP, false);
      core_61::set_code_page(&code_page[0]);
      AT = (isize) (assembly.address + assembly.count);

      Serial.print("Assembled ");
      Serial.print(assembly.count);
      Serial.print(" opcode(s) at ");
      Serial.println(assembly.address);
      return true;
    }

    void  flash_map_list(void) {
      Serial.print("     0  1  2  3  4  5  6  7  8  9\r\n0 - ");
      usize slot = 0;
      do { // пробежим все слоты от 0 до 99
        if(IsOccupied(slot))
          Serial.print("[X]");
        else
          Serial.print("[ ]");

        if(++slot == 100) break;

        if((slot % 10) == 0) {
          Serial.println();
          Serial.print(slot / 10);
          Serial.print(" - ");
        }
      } while(true);
      Serial.println();
    }

    terminal_protocol::Result command_to_kbd(bool script_mode) {
      usize code_61 = 0;
      const usize command_count = sizeof(key_sequence_on_cmd) / sizeof(key_sequence_on_cmd[0]);
      if(!terminal_core::parse_single_unsigned(command_args(), 16, command_count - 1, code_61)) {
        Serial.println("Usage: cmd <00..EF>");
        return terminal_protocol::Result::error();
      }

      u32 sequence = key_sequence_on_cmd[code_61];
      dbgln(MK61E, "mk61 <- ", (u8) code_61);
      dbghexln(MK61E, "mk61 <- $", (i32) sequence);

      for(isize i=0; i<4; i++) {
        const i8 scan_code = sequence & 0xFF;
        if(scan_code < 0) break;

        // В скрипте — прямо на ядро: буфер клавиатуры чистится при выходе из меню.
        if(script_mode) hidden_press_key((sw) scan_code);
        else kbd::push(scan_code);
        sequence >>= 8;
      }
      return terminal_protocol::Result::ok();
    }

    bool scancode_to_kbd(i32& out) {
      usize key_code = 0;
      if(!terminal_core::parse_single_unsigned(command_args(), 16, 0x27, key_code)) {
        Serial.println("Usage: kbd <00..27>");
        return false;
      }
      dbghexln(MK61E, "mk61 <- ", key_code, "H");
      out = (i32) key_code;
      return true;
    }

    static bool value_fits_mk61(double value) {
      char sign = ' ';
      char mantissa[8];
      isize pow10 = 0;
      return mk61_ref::double_to_parts(value, sign, mantissa, pow10);
    }

    bool write_register_value(u8 reg, const char* args) {
      double value = 0.0;
      if(!terminal_core::parse_single_decimal(args, value) || !value_fits_mk61(value)) return false;
      const mk61_ref::Ref ref = {mk61_ref::Kind::R, reg};
      return mk61_ref::write(ref, value);
    }

    bool write_stack_value(const char* args) {
      args = terminal_core::skip_spaces(args);
      if(args == NULL || args[0] == 0 || !terminal_core::is_space(args[1])) return false;

      char name[2] = {args[0], 0};
      mk61_ref::Ref ref;
      if(!mk61_ref::parse_name(name, ref) || ref.kind == mk61_ref::Kind::R) return false;

      double value = 0.0;
      if(!terminal_core::parse_single_decimal(args + 1, value) || !value_fits_mk61(value)) return false;
      return mk61_ref::write(ref, value);
    }

    // Аргументы команды: всё после первого слова строки ввода.
    const char* command_args(void) {
      const char* p = (const char*) input_buffer;
      while(!terminal_core::is_end(*p) && !terminal_core::is_space(*p)) p++;
      return terminal_core::skip_spaces(p);
    }

    // Список неотрицательных чисел через запятую и/или пробелы.
    isize parse_u32_list(const char* p, u32* out, usize max_count) {
      usize count = 0;
      while(true) {
        while(*p == ' ' || *p == ',') p++;
        if(*p == 0) break;
        if(*p < '0' || *p > '9') return -1;
        u32 value = 0;
        while(*p >= '0' && *p <= '9') {
          const u32 digit = (u32) (*p++ - '0');
          if(value > (0xFFFFFFFFUL - digit) / 10) return -1;
          value = value * 10 + digit;
        }
        if(count >= max_count) return -1;
        out[count++] = value;
      }
      return (isize) count;
    }

    // led 1 | led 0 | led 1,500,0,500,1 - состояния и паузы (ms), асинхронно.
    bool exec_led(void) {
      u32 values[2 * led::PATTERN_MAX - 1];
      const isize n = parse_u32_list(command_args(), values, 2 * led::PATTERN_MAX - 1);
      if(n <= 0 || (n % 2) == 0) return false; // нечётный список: state,ms,...,state

      led::PatternStep steps[led::PATTERN_MAX];
      usize count = 0;
      for(isize i = 0; i < n; i += 2) {
        if(values[i] > 1) return false;
        if(i + 1 < n && values[i + 1] > 65535) return false; // пауза хранится в u16
        steps[count].on = (u8) values[i];
        steps[count].hold_ms = (u16) ((i + 1 < n) ? values[i + 1] : 0);
        count++;
      }
      return led::pattern_start(steps, count);
    }

    // beep 4000,100 | beep 4000,100,0,50,2000,200 - пары частота(Hz),длительность(ms);
    // частота 0 - пауза. Воспроизведение асинхронное.
    bool exec_beep(void) {
      u32 values[2 * SOUND_PATTERN_MAX];
      const isize n = parse_u32_list(command_args(), values, 2 * SOUND_PATTERN_MAX);
      if(n <= 0 || (n % 2) != 0) return false;

      SoundNote notes[SOUND_PATTERN_MAX];
      const usize count = (usize) n / 2;
      for(usize i = 0; i < count; i++) {
        if(values[2 * i] > 65535 || values[2 * i + 1] > 65535) return false; // u16 в SoundNote
        notes[i].frequency_Hz = (u16) values[2 * i];
        notes[i].duration_ms = (u16) values[2 * i + 1];
        notes[i].gap_ms = 0;
        notes[i].volume_percent = 100;
      }
      return sound_pattern_start(notes, count);
    }

    // Значение индикаторного формата "-1.2345678 -99" -> double.
    // Нечисловые сегменты (ERROR, L/C/E на индикаторе) - отказ.
    static bool parse_mk_display_value(const char* v, double& out) {
      char buffer[20];
      char* w = buffer;
      if(v[0] == '-') *w++ = '-';
      for(int i = 1; i <= 9; i++) {
        const char c = v[i];
        if(c == '.') { *w++ = c; continue; }
        if(c == ' ') continue;
        if(c < '0' || c > '9') return false;
        *w++ = c;
      }
      if(v[12] < '0' || v[12] > '9' || v[13] < '0' || v[13] > '9') return false;
      *w++ = 'e';
      *w++ = (v[11] == '-') ? '-' : '+';
      *w++ = v[12];
      *w++ = v[13];
      *w = 0;
      out = mk_math::atof(buffer);
      return true;
    }

    static bool operand_delimiter(char c) {
      return terminal_core::is_end(c) || terminal_core::is_space(c) || c == '<' || c == '>' || c == '=' || c == '!';
    }

    // Операнд условия if: x,y,z,t,x1 (стек), r0..re (rf в расширенном режиме)
    // или числовой литерал (1.25e-2, -5, ...).
    static bool parse_if_operand(const char*& p, double& out) {
      p = terminal_core::skip_spaces(p);
      const char c = (*p >= 'A' && *p <= 'Z') ? (char) (*p - 'A' + 'a') : *p;

      if(c == 'r') {
        const isize reg = HexdecimalDigit(p[1]);
        if(reg >= 0 && operand_delimiter(p[2])) {
          if(reg == 15 && !core_61::expanded_program_is_on()) return false;
          char value[15];
          value[14] = 0;
          MK61Emu_ReadRegister((int) reg, value, terminal_symbols);
          p += 2;
          return parse_mk_display_value(value, out);
        }
        return false;
      }

      if(c == 'x' || c == 'y' || c == 'z' || c == 't') {
        stack reg = stack::X;
        usize advance = 1;
        if(c == 'x' && p[1] == '1') { reg = stack::X1; advance = 2; }
        else if(c == 'x') reg = stack::X;
        else if(c == 'y') reg = stack::Y;
        else if(c == 'z') reg = stack::Z;
        else reg = stack::T;
        if(!operand_delimiter(p[advance])) return false;

        char value[15];
        value[14] = 0;
        read_stack_register(reg, value, terminal_symbols);
        p += advance;
        return parse_mk_display_value(value, out);
      }

      return terminal_core::parse_decimal(p, out);
    }

    // if <операнд><op><операнд> <команда> - команда выполняется при истинном
    // условии. В m61-скриптах вместе с "run :метка" даёт условные переходы.
    terminal_protocol::Result exec_if(bool script_mode) {
      const char* p = command_args();
      double lhs = 0.0;
      double rhs = 0.0;
      bool parsed = parse_if_operand(p, lhs);

      char op0 = 0;
      char op1 = 0;
      if(parsed) {
        p = terminal_core::skip_spaces(p);
        op0 = p[0];
        if(op0 == '>' || op0 == '<' || op0 == '=' || op0 == '!') {
          p++;
          if(*p == '=') { op1 = '='; p++; }
        }
        parsed = (op0 == '>' || op0 == '<') || ((op0 == '=' || op0 == '!') && op1 == '=');
      }
      if(parsed) parsed = parse_if_operand(p, rhs);

      const char* tail = terminal_core::skip_spaces(p);
      if(!parsed || *tail == 0) {
        recive_pos = 0;
        Serial.println("Usage: if <x|y|z|t|x1|r0..re> <op> <value> <command>");
        return terminal_protocol::Result::error();
      }

      bool condition = false;
      if(op0 == '>') condition = op1 ? (lhs >= rhs) : (lhs > rhs);
      if(op0 == '<') condition = op1 ? (lhs <= rhs) : (lhs < rhs);
      if(op0 == '=') condition = (lhs == rhs);
      if(op0 == '!') condition = (lhs != rhs);

      if(!condition) {
        recive_pos = 0;
        return terminal_protocol::Result::ok();
      }

      // Условие истинно: остаток строки выполняется как обычная команда.
      const usize tail_len = strlen(tail);
      memmove(input_buffer, tail, tail_len);
      input_buffer[tail_len] = CR; // контракт execute(): последний символ CR
      recive_pos = tail_len + 1;
      return execute(script_mode);
    }

    terminal_protocol::Result execute(bool script_mode = false) {
        if(recive_pos == 0 || recive_pos > MAX_INPUT_CHAR) return terminal_protocol::Result::error();
        input_buffer[--recive_pos] = 0;
        if(!script_mode && current_directory != program_store::ROOT_ID) {
          program_store::Entry cwd_entry;
          if(!program_store::entry_by_id(current_directory, cwd_entry) ||
             cwd_entry.kind != program_store::NodeKind::DIRECTORY) {
            current_directory = program_store::ROOT_ID;
          }
        }
        Serial.println();
        dbgln(MINI,"[", recive_pos, "] '", (char*) input_buffer);

        if(!script_mode && pending_confirmation_cmd != CMD_UNKNOWN) {
          const u8 pending = pending_confirmation_cmd;
          pending_confirmation_cmd = CMD_UNKNOWN;
          if(terminal_core::exact_confirmation((const char*) input_buffer, 'y')) {
            bool ok = true;
            switch(pending) {
              case CMD_CLEAR:
                MK61Emu_ClearCodePage();
                Serial.println("Code page cleared!");
                break;
              case CMD_DEL_SLOT:
                ok = DeleteSlot(nSlot);
                if(!ok) Serial.println("Delete failed (no such file?)");
                break;
              case CMD_SAVE:
                ok = pending_save_name[0] != 0
                    ? StoreProgram(pending_save_parent_id, pending_save_name)
                    : Store(nSlot);
                if(!ok) Serial.println("Failed save attempt!");
                break;
              case CMD_ERASE_STORAGE:
                ok = clear_storage();
                break;
              default:
                ok = false;
                break;
            }
            pending_save_name[0] = 0;
            pending_save_parent_id = program_store::ROOT_ID;
            nSlot = -1;
            recive_pos = 0;
            return ok ? terminal_protocol::Result::ok() : terminal_protocol::Result::error();
          }
          if(terminal_core::exact_confirmation((const char*) input_buffer, 'n')) {
            pending_save_name[0] = 0;
            pending_save_parent_id = program_store::ROOT_ID;
            nSlot = -1;
            recive_pos = 0;
            Serial.println("Cancelled.");
            return terminal_protocol::Result::ok();
          }
          // Any command other than a standalone Y/N cancels the stale request.
          pending_save_name[0] = 0;
          pending_save_parent_id = program_store::ROOT_ID;
          nSlot = -1;
        }

        const u8 command_id = terminal_command_lookup(&input_buffer[0]);
        dbgln(MINI, "command id ", (int) command_id);
        if(script_mode && !terminal_command_allowed_in_script(command_id)) {
          Serial.print("Command is not allowed in M61 scripts: ");
          Serial.println((const char*) input_buffer);
          recive_pos = 0;
          return terminal_protocol::Result::error();
        }
        switch (command_id) {
          case  CMD_VERSION:
              output_version();
            break;
          case  CMD_ISA:
              echo_ISA_61();
            break;
          case  CMD_LIST:
              list_mk61_code_page();
            break;
          case  CMD_RESET:
              if(Confirmation()) NVIC_SystemReset();
            break;
          case  CMD_DFU:
              DFU_enable();
            break;
          case  CMD_REG_DUMP:
              DumpRegisters();
            break;
          case  CMD_REG_SET: {
              // Индекс - hex-цифра: R0..RE, RF только в расширенной памяти
              // (иначе запись ушла бы за пределы классического кольца).
              const isize reg = HexdecimalDigit((char) input_buffer[1]);
              const isize reg_limit = core_61::expanded_program_is_on() ? 15 : 14;
              if(reg < 0 || reg > reg_limit) {
                Serial.println("Illegal register, R0..RE (RF in expanded mode)!");
                recive_pos = 0;
                return terminal_protocol::Result::error();
              }
              if(!write_register_value((u8) reg, command_args())) {
                Serial.println("Usage: R<0..F>= <finite number with exponent -99..99>");
                recive_pos = 0;
                return terminal_protocol::Result::error();
              }
            }
            break;
          case  CMD_1302:
              Dump1302();
            break;
          case  CMD_CLEAR:
          case  CMD_ERASE_STORAGE:
              pending_confirmation_cmd = command_id;
              Serial.println("Enter Y/y to confirm the operation!");
            break;
          case  CMD_CMD: {
              const terminal_protocol::Result result = command_to_kbd(script_mode);
              recive_pos = 0;
              return result;
            }
          case  CMD_KBD: {
              i32 scancode = -1;
              if(!scancode_to_kbd(scancode)) {
                recive_pos = 0;
                return terminal_protocol::Result::error();
              }
              // В скрипте клавиша нажимается сразу на ядре, интерактивно —
              // скан-код уходит в буфер клавиатуры через loop().
              if(script_mode) {
                recive_pos = 0;
                return hidden_press_scan_code(scancode) ? terminal_protocol::Result::ok() : terminal_protocol::Result::error();
              }
              recive_pos = 0;
              return terminal_protocol::Result::keyboard(scancode);
            }
          case  CMD_DISASM:  // включить/выключить режим верхней строки с дизассемблером МК61
              config.disassm = disassembler.turn_on_off();
            break;
          case  CMD_SAVE: {
              const char* args = command_args();
              usize slot = 0;
              pending_save_name[0] = 0;
              pending_save_parent_id = program_store::ROOT_ID;
              if(terminal_parse_slot_arg(args, slot)) {
                nSlot = (isize) slot;
              } else {
                storage_path::FileTarget target = {};
                const storage_path::Status status = storage_path::file_target(
                    current_directory, args, program_store::ProgramType::MK61,
                    target);
                if(status != storage_path::Status::OK) {
                  terminal_path_error("save", status);
                  Serial.println("Usage: save <slot|path[.m61]>");
                  recive_pos = 0;
                  return terminal_protocol::Result::error();
                }
                nSlot = -1;
                pending_save_parent_id = target.parent_id;
                strncpy(pending_save_name, target.name,
                        sizeof(pending_save_name) - 1);
                pending_save_name[sizeof(pending_save_name) - 1] = 0;
              }
              pending_confirmation_cmd = CMD_SAVE;
              Serial.println("Enter Y/y to confirm the operation!");
            }
            break;
          case  CMD_LOAD: {
              const char* args = command_args();
              usize slot = 0;
              if(terminal_parse_slot_arg(args, slot)) {
                // В скрипте слот выполняется вложенно (Load() отменил бы сценарий).
                if(script_mode) return script_action(terminal_protocol::ResultKind::LOAD_SLOT, args);
                if(!Load(slot)) {
                  Serial.println("Failed load attempt!");
                  recive_pos = 0;
                  return terminal_protocol::Result::error();
                }
              } else {
                if(script_mode) return script_action(terminal_protocol::ResultKind::OPEN_FILE, args);
                program_store::Entry entry;
                const storage_path::Status status = storage_path::resolve_file(
                    current_directory, args, program_store::ProgramType::MK61,
                    entry);
                if(status != storage_path::Status::OK) {
                  terminal_path_error("load", status);
                  Serial.println("Usage: load <slot|path[.m61]>");
                  recive_pos = 0;
                  return terminal_protocol::Result::error();
                }
                if(!LoadProgram(entry.id)) {
                  Serial.println("Failed load attempt!");
                  recive_pos = 0;
                  return terminal_protocol::Result::error();
                }
              }
            }
            break;
          case  CMD_PUB:
              pub_mk61_code_page();
            break;
          case  CMD_DUMP:
              dump_mk61_code_page();
            break;
          case  CMD_RING: {
              usize i = 0;
              usize n_chip = 0;
              usize count = 0;
              const ring_M::K745* chips = ring_M::active_chips();
              const usize chip_count = ring_M::active_chip_count();
              const usize ring_size = core_61::ring_size();
              Serial.print("MK61 ring M dump:");
              while(count < ring_size) {
                const u8 ring_cell = ringM[count];
                if(i == 0) {
                  i = 42;
                  Serial.println();
                  if(n_chip < chip_count && chips[n_chip].OFFSET == count) Serial.println(chips[n_chip++].NAME);

                  if(count < 100) Serial.write('0');
                  if(count < 10) Serial.write('0');
                  Serial.print(count); Serial.write(' ');
                }
                Serial.write((char) (ring_cell < 10)? ring_cell + '0' : ring_cell - 10 + 'A');
                count++;
                i--;
              }
            }
            Serial.println();
            break;
          case  CMD_LASM:
              lasm_mk61_code_page(mnemo_type::ISA_61);
            break;
          case  CMD_INS: { 
              const char* args = command_args();
              usize into_step = 0;
              usize opcode = 0;
              if(!terminal_core::parse_unsigned(args, 10, core_61::program_steps() - 1, into_step) ||
                 !terminal_core::parse_unsigned(args, 16, 0xFF, opcode) ||
                 !terminal_core::at_end(args)) {
                Serial.println("Usage: ins <step> <00..FF>");
                recive_pos = 0;
                return terminal_protocol::Result::error();
              }
              insert_cmd_in_program(into_step, opcode);
            break;
          }
          case  CMD_STACK:
              echo_mk61_stack();
            break;
          case  CMD_HOUT:
              PutHexString();
            break;
          case  CMD_SMAP:
              flash_map_list();
            break;
          case  CMD_VFAT_LOG: {
              const char* line = virtual_fat::trace_line_at(0);
              if(line == NULL) Serial.println("Trace is empty (build with MK61_VFAT_TRACE).");
              for(u16 i = 0; (line = virtual_fat::trace_line_at(i)) != NULL; i++) Serial.println(line);
            }
            break;
          case CMD_FS_PWD: {
              if(!terminal_core::at_end(command_args())) {
                Serial.println("Usage: pwd");
                recive_pos = 0;
                return terminal_protocol::Result::error();
              }
              char path[MAX_INPUT_CHAR];
              const storage_path::Status status = storage_path::format_directory(
                  current_directory, path, sizeof(path));
              if(status != storage_path::Status::OK) {
                terminal_path_error("pwd", status);
                recive_pos = 0;
                return terminal_protocol::Result::error();
              }
              Serial.println(path);
            }
            break;
          case CMD_FS_CD: {
              const char* args = command_args();
              u16 directory = program_store::ROOT_ID;
              storage_path::Status status = storage_path::Status::OK;
              if(!terminal_core::at_end(args)) {
                status = storage_path::resolve_directory(current_directory,
                                                         args, directory);
              }
              if(status != storage_path::Status::OK) {
                terminal_path_error("cd", status);
                recive_pos = 0;
                return terminal_protocol::Result::error();
              }
              current_directory = directory;
            }
            break;
          case CMD_FS_LIST: {
              const char* args = command_args();
              u16 directory = current_directory;
              if(!terminal_core::at_end(args)) {
                storage_path::Status status = storage_path::resolve_directory(
                    current_directory, args, directory);
                if(status != storage_path::Status::OK) {
                  program_store::Entry single;
                  status = storage_path::resolve_entry(current_directory,
                                                       args, single);
                  if(status == storage_path::Status::OK) {
                    terminal_print_fs_entry(single);
                    break;
                  }
                  terminal_path_error("ls", status);
                  recive_pos = 0;
                  return terminal_protocol::Result::error();
                }
              }
              const int count = program_store::child_count(directory);
              for(int index = 0; index < count; index++) {
                program_store::Entry entry;
                if(!program_store::child(directory, index, entry)) {
                  Serial.println("ls: storage error");
                  recive_pos = 0;
                  return terminal_protocol::Result::error();
                }
                terminal_print_fs_entry(entry);
              }
              Serial.print(count);
              Serial.println(count == 1 ? " entry." : " entries.");
            }
            break;
          case CMD_FS_MKDIR: {
              const char* cursor = command_args();
              char path[MAX_INPUT_CHAR];
              if(!terminal_core::parse_token(cursor, path, sizeof(path))) {
                Serial.println("Usage: mkdir [-p] <path>");
                recive_pos = 0;
                return terminal_protocol::Result::error();
              }
              bool parents = false;
              if(strcmp(path, "-p") == 0) {
                parents = true;
                if(!terminal_core::parse_token(cursor, path, sizeof(path))) {
                  Serial.println("Usage: mkdir [-p] <path>");
                  recive_pos = 0;
                  return terminal_protocol::Result::error();
                }
              }
              if(!terminal_core::at_end(cursor)) {
                Serial.println("Usage: mkdir [-p] <path>");
                recive_pos = 0;
                return terminal_protocol::Result::error();
              }
              u16 created = program_store::INVALID_ID;
              const storage_path::Status status = storage_path::create_directory(
                  current_directory, path, parents, created);
              if(status != storage_path::Status::OK) {
                terminal_path_error("mkdir", status);
                recive_pos = 0;
                return terminal_protocol::Result::error();
              }
            }
            break;
          case CMD_FS_MOVE: {
              const char* cursor = command_args();
              char path[MAX_INPUT_CHAR];
              if(!terminal_core::parse_token(cursor, path, sizeof(path))) {
                Serial.println("Usage: mv <source> <destination>");
                recive_pos = 0;
                return terminal_protocol::Result::error();
              }
              program_store::Entry source;
              storage_path::Status status = storage_path::resolve_entry(
                  current_directory, path, source);
              if(status != storage_path::Status::OK ||
                 !terminal_core::parse_token(cursor, path, sizeof(path)) ||
                 !terminal_core::at_end(cursor)) {
                if(status != storage_path::Status::OK) {
                  terminal_path_error("mv", status);
                } else {
                  Serial.println("Usage: mv <source> <destination>");
                }
                recive_pos = 0;
                return terminal_protocol::Result::error();
              }
              u16 parent = program_store::INVALID_ID;
              char name[program_store::NAME_SIZE];
              status = storage_path::move_target(current_directory, source,
                                                 path, parent, name,
                                                 sizeof(name));
              if(status != storage_path::Status::OK ||
                 !program_store::move_rename(source.id, parent, name)) {
                terminal_path_error("mv", status == storage_path::Status::OK
                    ? storage_path::Status::IO_ERROR : status);
                recive_pos = 0;
                return terminal_protocol::Result::error();
              }
            }
            break;
          case CMD_FS_REMOVE: {
              const char* cursor = command_args();
              char path[MAX_INPUT_CHAR];
              if(!terminal_core::parse_token(cursor, path, sizeof(path))) {
                Serial.println("Usage: rm [-r] <path>");
                recive_pos = 0;
                return terminal_protocol::Result::error();
              }
              bool recursive = false;
              if(strcmp(path, "-r") == 0 || strcmp(path, "-R") == 0) {
                recursive = true;
                if(!terminal_core::parse_token(cursor, path, sizeof(path))) {
                  Serial.println("Usage: rm [-r] <path>");
                  recive_pos = 0;
                  return terminal_protocol::Result::error();
                }
              }
              if(!terminal_core::at_end(cursor)) {
                Serial.println("Usage: rm [-r] <path>");
                recive_pos = 0;
                return terminal_protocol::Result::error();
              }
              program_store::Entry entry;
              const storage_path::Status status = storage_path::resolve_entry(
                  current_directory, path, entry);
              if(status != storage_path::Status::OK) {
                terminal_path_error("rm", status);
                recive_pos = 0;
                return terminal_protocol::Result::error();
              }
              if(entry.kind == program_store::NodeKind::DIRECTORY &&
                 !recursive) {
                Serial.println("rm: is a directory; use rm -r or rmdir");
                recive_pos = 0;
                return terminal_protocol::Result::error();
              }
              u16 removed = 0;
              if(!program_store::remove_tree(entry.id, &removed)) {
                Serial.println("rm: storage error");
                recive_pos = 0;
                return terminal_protocol::Result::error();
              }
              Serial.print("Removed ");
              Serial.print(removed);
              Serial.println(removed == 1 ? " entry." : " entries.");
            }
            break;
          case CMD_FS_RMDIR: {
              char path[MAX_INPUT_CHAR];
              if(!terminal_single_token(command_args(), path, sizeof(path))) {
                Serial.println("Usage: rmdir <path>");
                recive_pos = 0;
                return terminal_protocol::Result::error();
              }
              u16 directory = program_store::ROOT_ID;
              storage_path::Status status = storage_path::resolve_directory(
                  current_directory, path, directory);
              if(status != storage_path::Status::OK ||
                 directory == program_store::ROOT_ID) {
                terminal_path_error("rmdir",
                    directory == program_store::ROOT_ID &&
                    status == storage_path::Status::OK
                        ? storage_path::Status::ROOT : status);
                recive_pos = 0;
                return terminal_protocol::Result::error();
              }
              if(program_store::child_count(directory) != 0 ||
                 !program_store::remove_id(directory)) {
                Serial.println("rmdir: directory not empty or storage error");
                recive_pos = 0;
                return terminal_protocol::Result::error();
              }
            }
            break;
          case CMD_FS_STAT: {
              if(!terminal_core::at_end(command_args())) {
                Serial.println("Usage: df");
                recive_pos = 0;
                return terminal_protocol::Result::error();
              }
              u16 directories = 0;
              const int visible = program_store::total_count();
              for(int index = 0; index < visible; index++) {
                program_store::Entry entry;
                if(program_store::entry_at(index, entry) &&
                   entry.kind == program_store::NodeKind::DIRECTORY) {
                  directories++;
                }
              }
              const u16 used = program_store::used_nodes();
              const u16 maximum = program_store::max_nodes();
              Serial.print("Flash: ");
              Serial.print(program_store::geometry().capacity_bytes);
              Serial.println(" bytes");
              Serial.print("Nodes: "); Serial.print(used); Serial.print(" used, ");
              Serial.print(maximum - used); Serial.print(" free, ");
              Serial.print(maximum); Serial.println(" total");
              Serial.print("Visible: "); Serial.print(visible - directories);
              Serial.print(" files, "); Serial.print(directories);
              Serial.print(" directories, "); Serial.print(used - visible);
              Serial.println(" directory extents");
              Serial.print("FAT12 cluster: ");
              Serial.print((u32) program_store::geometry().sectors_per_cluster * 512U);
              Serial.println(" bytes (virtual)");
              Serial.print("Settings: "); Serial.print(program_store::settings_size());
              Serial.println(" bytes reserved");
            }
            break;
          case  CMD_FS_CLEAN: {
              const u16 purged = program_store::purge_empty();
              Serial.print("Removed ");
              Serial.print(purged);
              Serial.println(" empty entries.");
            }
            break;
          case  CMD_RUN: {
              // "run <имя>" — синоним open; без имени — запуск программы МК61.
              const char* args = command_args();
              if(*args == ':') { // run :метка - переход внутри m61-скрипта
                if(script_mode) return script_action(terminal_protocol::ResultKind::GOTO_LABEL, args + 1);
                Serial.println("Labels work in m61 scripts only!");
                recive_pos = 0;
                return terminal_protocol::Result::error();
              }
              if(*args != 0) {
                if(script_mode) return script_action(terminal_protocol::ResultKind::OPEN_FILE, args);
                if(!OpenStoredFile(current_directory, args)) {
                  Serial.println("Open failed!");
                  recive_pos = 0;
                  return terminal_protocol::Result::error();
                }
                break;
              }
              if(script_mode) return script_action(terminal_protocol::ResultKind::RUN_PROGRAM, "");
              kbd::push((i8) sw::F);   // F
              kbd::push((i8) sw::NEG); // /-/
              kbd::push((i8) sw::RET); // В/О
              kbd::push((i8) sw::RUN); // C/П
            }
            break;
          case CMD_OPEN: {
              const char* args = command_args();
              if(terminal_core::at_end(args)) {
                Serial.println("Usage: open <path>");
                recive_pos = 0;
                return terminal_protocol::Result::error();
              }
              if(script_mode) return script_action(terminal_protocol::ResultKind::OPEN_FILE, args);
              if(!OpenStoredFile(current_directory, args)) {
                Serial.println("Open failed!");
                recive_pos = 0;
                return terminal_protocol::Result::error();
              }
            }
            break;
          case  CMD_POKE:
              if(!write_stack_value(command_args())) {
                Serial.println("Usage: poke <X|Y|Z|T> <finite number with exponent -99..99>");
                recive_pos = 0;
                return terminal_protocol::Result::error();
              }
            break;
          case  CMD_DIR: {
              char slot_name[SIZEOF_SLOT_NAME];
              for(usize i=0; i < 100; i++) {
                if(IsOccupied(i)) {
                  Serial.print(i); Serial.print(". "); Serial.println(ReadSlotName(i, (char*) &slot_name[0]));
                }
              }
            }
            break;
          case  CMD_DEL_SLOT: {
              if(!flash_is_ok) {
                Serial.println("Error: spiflash chip is not installed!");
                recive_pos = 0;
                return terminal_protocol::Result::error();
              }
              usize slot = 0;
              if(!terminal_core::parse_single_unsigned(command_args(), 10, 99, slot)) {
                Serial.println("Usage: sdel <0..99>");
                recive_pos = 0;
                return terminal_protocol::Result::error();
              }
              nSlot = (isize) slot;
              Serial.print("\n\rDelete slot #"); Serial.println(nSlot);
              if(!IsOccupied(nSlot)) {
                Serial.println("Warning: slot is already empty.");
                recive_pos = 0;
                return terminal_protocol::Result::error();
              }
              pending_confirmation_cmd = CMD_DEL_SLOT;
              Serial.println("Enter Y/y to confirm the operation!");
            }
            break;
          case  CMD_RENAME: {
              const char* args = command_args();
              usize slot = 0;
              if(!terminal_core::parse_unsigned(args, 10, 99, slot)) {
                Serial.println("Usage: snm <0..99> <name>");
                recive_pos = 0;
                return terminal_protocol::Result::error();
              }
              char slot_name[SIZEOF_SLOT_NAME];
              if(!terminal_copy_arg(slot_name, sizeof(slot_name), args)) {
                Serial.println("Name must contain 1..15 characters.");
                recive_pos = 0;
                return terminal_protocol::Result::error();
              }
              Serial.print("Rename slot N"); Serial.print(slot); Serial.print(" to "); Serial.println(slot_name);
              if(!Rename(slot, slot_name)) {
                Serial.println("Rename failed (missing slot or duplicate name).");
                ErrorReaction();
                recive_pos = 0;
                return terminal_protocol::Result::error();
              }
            }
            break;
          case  CMD_HIN:
          case  CMD_SET_CODE:
              if(!GetHexString(command_id == CMD_SET_CODE ? (const char*) &input_buffer[4] : command_args())) {
                recive_pos = 0;
                return terminal_protocol::Result::error();
              }
            break;
          case  CMD_ASM:
              if(!Assembler()) {
                recive_pos = 0;
                return terminal_protocol::Result::error();
              }
            break;
          case  CMD_HELP:
              print_help();
            break;
          case  CMD_LED:
              if(!exec_led()) {
                Serial.println("Usage: led <0|1>[,<ms>,<0|1>,...]");
                recive_pos = 0;
                return terminal_protocol::Result::error();
              }
            break;
          case  CMD_BEEP:
              if(!exec_beep()) {
                Serial.println("Usage: beep <Hz>,<ms>[,<Hz>,<ms>,...]");
                recive_pos = 0;
                return terminal_protocol::Result::error();
              }
            break;
          case  CMD_IF:
              return exec_if(script_mode);
          case  CMD_HISTORY:
              history_print();
            break;
          default:
              if(input_buffer[0] != 0) {
                Serial.print("Unknown command: ");
                Serial.println((const char*) input_buffer);
              }
              recive_pos = 0;
              return terminal_protocol::Result::error();
        }

      recive_pos = 0;
      return terminal_protocol::Result::ok();
    }

    i32 serial_input_handler() {
      while(Serial.peek() >= 0) { // получен символ
        const u8 rx_char = Serial.read(); // уберем с буфера

        // --- escape-последовательности: стрелки листают историю ---
        if(esc_state == 1) {
          esc_state = (rx_char == '[') ? 2 : 0;
          continue;
        }
        if(esc_state == 2) {
          esc_state = 0;
          if(!input_overflow) {
            if(rx_char == 'A') history_key_up();
            if(rx_char == 'B') history_key_down();
          }
          continue;
        }
        if(rx_char == 0x1B) {
          esc_state = 1;
          continue;
        }

        if(rx_char == CR || rx_char == NL) {
          if(prev_terminator != 0 && rx_char != prev_terminator) {
            prev_terminator = 0; // второй символ пары CRLF/LFCR
            continue;
          }
          prev_terminator = rx_char;

          if(input_overflow) {
            // Переполненная строка отбрасывается целиком: выполнять обрезанную
            // команду нельзя (поток может идти и с другого устройства, без
            // реакции на звуковой сигнал занятости).
            input_overflow = false;
            recive_pos = 0;
            Serial.println();
            Serial.println("Error: input line too long, command ignored!");
            print_prompt();
            return -1;
          }

          if(recive_pos == 0) { // пустая строка - только новое приглашение
            Serial.println();
            print_prompt();
            continue;
          }

          history_add(input_buffer, recive_pos);
          hist_nav = -1;

          input_buffer[recive_pos++] = CR; // контракт execute(): последний символ CR
          const terminal_protocol::Result result = execute();
          print_prompt();
          // Остаток потока обработается в следующем вызове: каждая строка
          // выполняется до чтения следующей, пакетный ввод не склеивается.
          return result.kind == terminal_protocol::ResultKind::KEY ? result.key : -1;
        }
        prev_terminator = 0;

        if(rx_char == 0x08 || rx_char == 0x7F) { // backspace
          if(!input_overflow && recive_pos > 0) {
            recive_pos = utf8_view::previous_offset(input_buffer,
                                                    (u16) recive_pos,
                                                    (u16) recive_pos);
            Serial.print("\b \b");
          }
          continue;
        }

        if(rx_char < 0x20 && rx_char != '\t') continue; // управляющие символы не буферизуем

        if(input_can_append()) {
          input_buffer[recive_pos++] = rx_char;
          Serial.write(rx_char); // эхо
        } else if(!input_overflow) {
          input_overflow = true; // сигнал занятости - один раз на строку
          sound(PIN_BUZZER, 4000, 750, library_mk61::sound_volume());
        }
      }
      return -1;
    }

};

inline terminal_protocol::Result class_terminal::execute_script_line(const char* line) {
  if(line == NULL) return terminal_protocol::Result::error();

  // input_buffer один на прошивку: пока скрипт исполняется между итерациями
  // loop(), в буфере может лежать недонабранная строка интерактивного
  // терминала. Сохраняем её на стеке и возвращаем после выполнения строки.
  u8 interactive_line[MAX_INPUT_CHAR];
  memcpy(interactive_line, input_buffer, MAX_INPUT_CHAR);

  terminal_protocol::Result result = terminal_protocol::Result::error();
  usize len = 0;
  bool too_long = false;
  while(line[len] != 0) {
    if(!terminal_core::input_can_append(len)) {
      too_long = true;
      break;
    }
    input_buffer[len] = (u8) line[len];
    len++;
  }

  if(too_long) {
    recive_pos = 0;
  } else {
    input_buffer[len] = CR;
    recive_pos = len + 1;
    result = execute(true);
  }

  memcpy(input_buffer, interactive_line, MAX_INPUT_CHAR);
  return result;
}

#endif
