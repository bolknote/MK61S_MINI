// Immutable command catalog; included only by terminal_catalog.cpp.
COMMAND("ver", CMD_VERSION, "версия прошивки")
COMMAND("identity", CMD_IDENTITY, "идентификаторы устройства и сборки")
COMMAND("date", CMD_DATE, "date [ms|ГГГГ-ММ-ДД ЧЧ:ММ:СС] — часы")
#if MK61_ENABLE_RTC_ALARM_TERMINAL
COMMAND("alarm", CMD_ALARM, "состояние и настройка будильников RTC A/B")
#endif
COMMAND("help", CMD_HELP, "эта справка")
COMMAND("history", CMD_HISTORY, "история команд")
COMMAND("list", CMD_LIST, "память программ: HEX, столбцом")
COMMAND("dump", CMD_DUMP, "память программ: HEX, строками")
COMMAND("pub", CMD_PUB, "листинг программы для публикации")
COMMAND("lasm", CMD_LASM, "дизассемблировать программу")
COMMAND("isa", CMD_ISA, "справочник мнемоник ассемблера")
COMMAND("asm", CMD_ASM, "asm [адрес] <мнемоники> — ассемблировать")
COMMAND("ins", CMD_INS, "ins <шаг> <код> — вставить команду")
COMMAND("hin", CMD_HIN, "hin <адрес> <hex> — записать память программ")
COMMAND("hout", CMD_HOUT, "память программ в виде команд hin")
COMMAND("reg", CMD_REG_DUMP, "показать регистры R0…RE")
COMMAND("stk", CMD_STACK, "показать стек X,Y,Z,T,X1")
COMMAND("poke", CMD_POKE, "poke <X|Y|Z|T> <число> — записать стек")
COMMAND("1302", CMD_1302, "показать регистр R К145ИК1302")
COMMAND("ring", CMD_RING, "показать кольцевую память M")
COMMAND("kbd", CMD_KBD, "kbd <сканкод> — нажать клавишу")
COMMAND("led", CMD_LED, "led <0|1>[,мс,…] — сценарий светодиода")
COMMAND("beep", CMD_BEEP, "beep <Гц>,<мс>[,…] — звуковой сценарий")
COMMAND("if", CMD_IF, "if <регистр><условие><число> <команда>")
COMMAND("print", CMD_PRINT, "print \"текст {X}\"|off|on — экран M61")
COMMAND("wait", CMD_WAIT, "wait <1..60000> — пауза сценария, мс")
COMMAND("ret", CMD_RET, "возврат из сценария или ловушки M61")
COMMAND("reinit", CMD_REINIT, "очистить калькулятор и обработчики M61")
COMMAND("cmd", CMD_CMD, "cmd <код> — набрать команду клавишами")
COMMAND("run", CMD_RUN, "run [имя] — запустить программу или файл")
COMMAND("open", CMD_OPEN, "open <имя> — открыть файл")
COMMAND("save", CMD_SAVE, "save <номер|путь.m61> — сохранить программу")
COMMAND("load", CMD_LOAD, "load <номер|путь.m61> — загрузить программу")
COMMAND("pwd", CMD_FS_PWD, "текущий каталог хранилища")
COMMAND("cd", CMD_FS_CD, "cd [путь] — сменить каталог")
COMMAND("ls", CMD_FS_LIST, "ls [путь] — показать каталог")
COMMAND("dir", CMD_FS_LIST, "то же, что ls")
COMMAND("mkdir", CMD_FS_MKDIR, "mkdir [-p] <путь> — создать каталоги")
COMMAND("mv", CMD_FS_MOVE, "mv <откуда> <куда>")
COMMAND("rm", CMD_FS_REMOVE, "rm [-r] <путь> — удалить файл или дерево")
COMMAND("del", CMD_FS_REMOVE, "то же, что rm")
COMMAND("rmdir", CMD_FS_RMDIR, "rmdir <путь> — удалить пустой каталог")
COMMAND("df", CMD_FS_STAT, "ёмкость C6 и число узлов")
#if MK61_ENABLE_READ_BENCHMARKS
COMMAND("bench", CMD_BENCHMARK, "тест чтения C6 без записи")
#endif
COMMAND("fsget", CMD_FS_GET, "fsget <путь> — машинное чтение файла")
COMMAND("fsput", CMD_FS_PUT, "fsput begin|data|end|cancel — загрузка файла")
COMMAND("format", CMD_FORMAT_STORAGE, "format C6 — форматировать (Y/y)")
COMMAND("clr", CMD_CLEAR, "очистить память программ (Y/y)")
COMMAND("vlog", CMD_VFAT_LOG, "диагностика импорта USB [clear]")
COMMAND("usbdisk", CMD_USB_DISK, "запустить режим USB-диска до безопасного извлечения")
COMMAND("fsls", CMD_FS_LIST, "ls [путь] — показать каталог")
COMMAND("fsrm", CMD_FS_REMOVE, "rm [-r] <путь> — удалить файл или дерево")
COMMAND("fsstat", CMD_FS_STAT, "ёмкость C6 и число узлов")
COMMAND("fsclean", CMD_FS_CLEAN, "удалить все пустые записи хранилища")
COMMAND("disa", CMD_DISASM, "включить или выключить дизассемблер")
#if MK61_ENABLE_USB_SCREEN
COMMAND("uscreen", CMD_USB_SCREEN, "запустить режим USB-экрана")
#endif
#if MK61_DWT_PROFILER_SUPPORTED
  #if MK61_DEEP_IDLE_SUPPORTED
    #if MK61_ENABLE_PROFILE_SAVE
COMMAND("prof", CMD_PROFILE, "prof [start|stop|reset|core|deep <1..5> [циклы]|save] — профиль")
    #else
COMMAND("prof", CMD_PROFILE, "prof [start|stop|reset|core|deep <1..5> [циклы]] — профиль")
    #endif
  #else
    #if MK61_ENABLE_PROFILE_SAVE
COMMAND("prof", CMD_PROFILE, "prof [start|stop|reset|core [шаги]|save [путь.txt]] — профиль")
    #else
COMMAND("prof", CMD_PROFILE, "prof [start|stop|reset|core [шаги]] — профиль")
    #endif
  #endif
#endif
#if MK61_CRASH_DUMP_SUPPORTED
  #if MK61_ENABLE_FAULT_INJECTION
COMMAND("crash", CMD_CRASH, "crash [show|clear|save [путь.txt]|test <сбой>] — сбои")
  #else
COMMAND("crash", CMD_CRASH, "crash [show|clear|save [путь.txt]] — сбои")
  #endif
#endif
#if MK61_INDEPENDENT_WATCHDOG_SUPPORTED
  #if MK61_ENABLE_WATCHDOG_TEST
COMMAND("wdog", CMD_WATCHDOG, "wdog [status|test <starve|hang>] — сторожевой таймер")
  #else
COMMAND("wdog", CMD_WATCHDOG, "wdog [status] — сторожевой таймер")
  #endif
#endif
#if MK61_MPU_GUARD_SUPPORTED
  #if MK61_ENABLE_MPU_TEST
COMMAND("mpu", CMD_MPU, "mpu [status|test <guard|null|exec>] — защита памяти")
  #else
COMMAND("mpu", CMD_MPU, "mpu [status] — защита памяти")
  #endif
#endif
COMMAND("display", CMD_DISPLAY, "display status|reinit|on|off|test <режим>: text/alphabet/symbols/map/ddram/row/cgram/zero/clear/home/cursor/entry/autoshift/sleep/graphics/graphics-read/restore — экран")
COMMAND("rst", CMD_RESET, "rst [now] — перезапуск; без now просит подтверждение")
COMMAND("dfu", CMD_DFU, "dfu [status] — войти в ROM DFU или показать состояние")
