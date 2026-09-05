// Immutable command catalog; included only by terminal_catalog.cpp.
COMMAND("ver", CMD_VERSION, "firmware version")
COMMAND("identity", CMD_IDENTITY, "stable device/build identity")
COMMAND("date", CMD_DATE, "date [ms|YYYY-MM-DD HH:MM:SS] - read/set clock")
#if MK61_ENABLE_RTC_ALARM_TERMINAL
COMMAND("alarm", CMD_ALARM, "RTC Alarm A/B status, daily or one-shot")
#endif
COMMAND("help", CMD_HELP, "this list")
COMMAND("history", CMD_HISTORY, "recent command lines")
COMMAND("list", CMD_LIST, "program memory in hex, vertical")
COMMAND("dump", CMD_DUMP, "program memory in hex, horizontal")
COMMAND("pub", CMD_PUB, "program listing in publication format")
COMMAND("lasm", CMD_LASM, "disassemble program memory")
COMMAND("isa", CMD_ISA, "list of assembler mnemonics")
COMMAND("asm", CMD_ASM, "asm [TA] <mnemonics> - assemble line")
COMMAND("ins", CMD_INS, "ins <step> <opcode> - insert into program")
COMMAND("hin", CMD_HIN, "hin <addr> <hex> - write program memory")
COMMAND("hout", CMD_HOUT, "program memory as hin lines")
COMMAND("reg", CMD_REG_DUMP, "dump R0..RE registers")
COMMAND("stk", CMD_STACK, "dump stack X,Y,Z,T,X1")
COMMAND("poke", CMD_POKE, "poke <X|Y|Z|T> <1.25e02> - write stack")
COMMAND("1302", CMD_1302, "dump K145IK1302 R register")
COMMAND("ring", CMD_RING, "dump ring M memory")
COMMAND("kbd", CMD_KBD, "kbd <hex scancode> - press key")
COMMAND("led", CMD_LED, "led <0|1>[,ms,0|1,...] - LED pattern")
COMMAND("beep", CMD_BEEP, "beep <Hz>,<ms>[,...] - sound pattern")
COMMAND("if", CMD_IF, "if <reg><op><val> <cmd> - conditional")
COMMAND("print", CMD_PRINT, "print \"text {X}\"|off|on - M61 display")
COMMAND("wait", CMD_WAIT, "wait <1..60000> - pause M61 script (ms)")
COMMAND("ret", CMD_RET, "return from an M61 script/trap")
COMMAND("reinit", CMD_REINIT, "clear calculator state and M61 handlers")
COMMAND("cmd", CMD_CMD, "cmd <hex opcode> - press keys of opcode")
COMMAND("run", CMD_RUN, "run [name] - run program / stored file")
COMMAND("open", CMD_OPEN, "open <name> - run stored file")
COMMAND("save", CMD_SAVE, "save <slot|path.m61> - store program (Y/y)")
COMMAND("load", CMD_LOAD, "load <slot|path.m61> - load program")
COMMAND("pwd", CMD_FS_PWD, "print current storage directory")
COMMAND("cd", CMD_FS_CD, "cd [path] - change storage directory")
COMMAND("ls", CMD_FS_LIST, "ls [path] - list one storage directory")
COMMAND("dir", CMD_FS_LIST, "alias for ls")
COMMAND("mkdir", CMD_FS_MKDIR, "mkdir [-p] <path> - create directories")
COMMAND("mv", CMD_FS_MOVE, "mv <source> <destination>")
COMMAND("rm", CMD_FS_REMOVE, "rm [-r] <path> - remove file or tree")
COMMAND("del", CMD_FS_REMOVE, "alias for rm")
COMMAND("rmdir", CMD_FS_RMDIR, "rmdir <path> - remove empty directory")
COMMAND("df", CMD_FS_STAT, "show C5 capacity and node quota")
#if MK61_ENABLE_READ_BENCHMARKS
COMMAND("bench", CMD_BENCHMARK, "read-only C5 benchmark")
#endif
COMMAND("fsget", CMD_FS_GET, "fsget <path> - machine file download")
COMMAND("fsput", CMD_FS_PUT, "fsput begin|data|end|cancel - machine upload")
COMMAND("smap", CMD_SMAP, "numeric M1 slot occupancy map")
COMMAND("sdir", CMD_DIR, "list numeric M1 slots")
COMMAND("snm", CMD_RENAME, "snm <slot> <name> - rename slot")
COMMAND("sdel", CMD_DEL_SLOT, "sdel <slot> - delete numeric M1 slot (Y/y)")
COMMAND("sera", CMD_ERASE_STORAGE, "erase all slots (Y/y)")
COMMAND("clr", CMD_CLEAR, "clear program memory (Y/y)")
COMMAND("vlog", CMD_VFAT_LOG, "USB import diagnostic [clear]")
COMMAND("fsls", CMD_FS_LIST, "alias for ls")
COMMAND("fsrm", CMD_FS_REMOVE, "alias for rm")
COMMAND("fsstat", CMD_FS_STAT, "alias for df")
COMMAND("fsclean", CMD_FS_CLEAN, "remove all zero-length store entries")
COMMAND("disa", CMD_DISASM, "toggle disassembler on display")
#if MK61_ENABLE_USB_SCREEN
COMMAND("uscreen", CMD_USB_SCREEN, "start USB Screen mode")
#endif
#if MK61_DWT_PROFILER_SUPPORTED
  #if MK61_DEEP_IDLE_SUPPORTED
    #if MK61_ENABLE_PROFILE_SAVE
COMMAND("prof", CMD_PROFILE, "prof [start|stop|reset|core|deep <1..5> [cycles]|save]")
    #else
COMMAND("prof", CMD_PROFILE, "prof [start|stop|reset|core|deep <1..5> [cycles]]")
    #endif
  #else
    #if MK61_ENABLE_PROFILE_SAVE
COMMAND("prof", CMD_PROFILE, "prof [start|stop|reset|core [steps]|save [path.txt]]")
    #else
COMMAND("prof", CMD_PROFILE, "prof [start|stop|reset|core [steps]]")
    #endif
  #endif
#endif
#if MK61_CRASH_DUMP_SUPPORTED
  #if MK61_ENABLE_FAULT_INJECTION
COMMAND("crash", CMD_CRASH, "crash [show|clear|save [path.txt]|test <fault>]")
  #else
COMMAND("crash", CMD_CRASH, "crash [show|clear|save [path.txt]]")
  #endif
#endif
#if MK61_INDEPENDENT_WATCHDOG_SUPPORTED
  #if MK61_ENABLE_WATCHDOG_TEST
COMMAND("wdog", CMD_WATCHDOG, "wdog [status|test <starve|hang>]")
  #else
COMMAND("wdog", CMD_WATCHDOG, "wdog [status]")
  #endif
#endif
#if MK61_MPU_GUARD_SUPPORTED
  #if MK61_ENABLE_MPU_TEST
COMMAND("mpu", CMD_MPU, "mpu [status|test <guard|null|exec>]")
  #else
COMMAND("mpu", CMD_MPU, "mpu [status]")
  #endif
#endif
COMMAND("mem", CMD_MEMORY, "shared SRAM arenas [reset]")
COMMAND("display", CMD_DISPLAY, "display status/test/reinit/on/off")
COMMAND("rst", CMD_RESET, "rst [now] - reboot; plain rst confirms on device")
COMMAND("dfu", CMD_DFU, "dfu [status] - enter/report ROM DFU")
