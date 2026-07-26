# MK61s System APP

Этот каталог автономно собирает штатные модули STM32F401:

- `focal/main.cpp` → `FOCAL.APP`;
- `basic/main.cpp` → `BASIC.APP`;
- `wbmp/main.cpp` → `WBMP.APP`;
- `chip8/main.cpp` → `CHIP8.APP`.

Каждый модуль компилируется как одна единица трансляции через
`arm-none-eabi-g++`, связывается с точным resident ELF и извлекается через
`arm-none-eabi-objcopy`. Готовый контейнер имеет payload `NONE` и содержит
размер и CRC соответствующего resident BIN.

Обычно сборщик вызывает `tools/mk61-firmware.cmd`. Отдельный запуск в Windows:

```bat
system_apps\build.cmd ^
  -BuildPath C:\work\mk61-resident ^
  -Focal 1 -Basic 1 -Wbmp 1 -Chip8 1
```

В `BuildPath` должны находиться resident `.elf`, `.bin` и созданный той же
Arduino-сборкой `compile_commands.json`. Из него берутся точные пути к ARM
toolchain, include-каталогам и compile-time ключи. По умолчанию результат
появляется в `system_apps\System`; для другого места передайте
`-OutputDirectory`. `WBMP.APP` регистрирует обработчик файлов `I1`, а
`CHIP8.APP` — обработчик `C1`.

Сборщик не линкует Arduino-библиотеки внутрь APP. Общие функции resident
разрешаются через `--just-symbols`, поэтому нельзя смешивать `.APP` и `.bin`
из разных запусков сборки.
