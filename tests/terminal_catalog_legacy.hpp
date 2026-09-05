// Characterization fixture from the pre-R4 catalog, not production data.
static constexpr TerminalCommand legacy_commands[] = {
  { "ver",     CMD_VERSION,       "firmware version" },
  { "identity",CMD_IDENTITY,      "stable device/build identity" },
  { "date",    CMD_DATE,          "date [ms|YYYY-MM-DD HH:MM:SS] - read/set clock" },
#if MK61_ENABLE_RTC_ALARM_TERMINAL
  { "alarm",   CMD_ALARM,         "RTC Alarm A/B status, daily or one-shot" },
#endif
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
  { "print",   CMD_PRINT,          "print \"text {X}\"|off|on - M61 display" },
  { "wait",    CMD_WAIT,           "wait <1..60000> - pause M61 script (ms)" },
  { "ret",     CMD_RET,            "return from an M61 script/trap" },
  { "reinit",  CMD_REINIT,         "clear calculator state and M61 handlers" },
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
#if MK61_ENABLE_READ_BENCHMARKS
  { "bench",   CMD_BENCHMARK,     "read-only C5 benchmark" },
#endif
  { "fsget",   CMD_FS_GET,        "fsget <path> - machine file download" },
  { "fsput",   CMD_FS_PUT,        "fsput begin|data|end|cancel - machine upload" },
  { "smap",    CMD_SMAP,          "numeric M1 slot occupancy map" },
  { "sdir",    CMD_DIR,           "list numeric M1 slots" },
  { "snm",     CMD_RENAME,        "snm <slot> <name> - rename slot" },
  { "sdel",    CMD_DEL_SLOT,      "sdel <slot> - delete numeric M1 slot (Y/y)" },
  { "sera",    CMD_ERASE_STORAGE, "erase all slots (Y/y)" },
  { "clr",     CMD_CLEAR,         "clear program memory (Y/y)" },
  { "vlog",    CMD_VFAT_LOG,      "USB import diagnostic [clear]" },
  { "fsls",    CMD_FS_LIST,       "alias for ls" },
  { "fsrm",    CMD_FS_REMOVE,     "alias for rm" },
  { "fsstat",  CMD_FS_STAT,       "alias for df" },
  { "fsclean", CMD_FS_CLEAN,      "remove all zero-length store entries" },
  { "disa",    CMD_DISASM,        "toggle disassembler on display" },
#if MK61_ENABLE_USB_SCREEN
  { "uscreen", CMD_USB_SCREEN,    "start USB Screen mode" },
#endif
#if MK61_DWT_PROFILER_SUPPORTED
  #if MK61_DEEP_IDLE_SUPPORTED
    #if MK61_ENABLE_PROFILE_SAVE
  { "prof",    CMD_PROFILE,       "prof [start|stop|reset|core|deep <1..5> [cycles]|save]" },
    #else
  { "prof",    CMD_PROFILE,       "prof [start|stop|reset|core|deep <1..5> [cycles]]" },
    #endif
  #else
    #if MK61_ENABLE_PROFILE_SAVE
  { "prof",    CMD_PROFILE,       "prof [start|stop|reset|core [steps]|save [path.txt]]" },
    #else
  { "prof",    CMD_PROFILE,       "prof [start|stop|reset|core [steps]]" },
    #endif
  #endif
#endif
#if MK61_CRASH_DUMP_SUPPORTED
  #if MK61_ENABLE_FAULT_INJECTION
  { "crash",   CMD_CRASH,         "crash [show|clear|save [path.txt]|test <fault>]" },
  #else
  { "crash",   CMD_CRASH,         "crash [show|clear|save [path.txt]]" },
  #endif
#endif
#if MK61_INDEPENDENT_WATCHDOG_SUPPORTED
  #if MK61_ENABLE_WATCHDOG_TEST
  { "wdog",    CMD_WATCHDOG,      "wdog [status|test <starve|hang>]" },
  #else
  { "wdog",    CMD_WATCHDOG,      "wdog [status]" },
  #endif
#endif
#if MK61_MPU_GUARD_SUPPORTED
  #if MK61_ENABLE_MPU_TEST
  { "mpu",     CMD_MPU,           "mpu [status|test <guard|null|exec>]" },
  #else
  { "mpu",     CMD_MPU,           "mpu [status]" },
  #endif
#endif
  { "mem",     CMD_MEMORY,        "shared SRAM arenas [reset]" },
  { "display", CMD_DISPLAY,       "display status/test/reinit/on/off" },
  { "rst",     CMD_RESET,         "rst [now] - reboot; plain rst confirms on device" },
  { "dfu",     CMD_DFU,           "dfu [status] - enter/report ROM DFU" },
};
