# MK61s System APP

Этот каталог автономно собирает штатные модули STM32F401:

- `focal/main.cpp` → `FOCAL.APP`;
- `basic/main.cpp` → `BASIC.APP`;
- `wbmp/main.cpp` → `WBMP.APP`;
- `markdown/main.cpp` → `MARKDOWN.APP`;
- `chip8/main.cpp` → `CHIP8.APP`.

Каждый модуль компилируется как одна единица трансляции через
`arm-none-eabi-g++`, связывается с точным resident ELF и извлекается через
`arm-none-eabi-objcopy`. Готовый контейнер имеет payload `NONE` и содержит
размер и CRC соответствующего resident BIN.

Обычно сборщик вызывает `tools/mk61-firmware.cmd`. Отдельный запуск в Windows:

```bat
system_apps\build.cmd ^
  -BuildPath C:\work\mk61-resident ^
  -Focal 1 -Basic 1 -Wbmp 0 -Markdown 1 -Chip8 1
```

В `BuildPath` должны находиться resident `.elf`, `.bin` и созданный той же
сборкой `compile_commands.json`. Это может быть как сборка Arduino, так и
прямая CMake/GCC-сборка через `tools\build-gcc.cmd`. Из базы берутся точные
пути к ARM toolchain, include-каталогам и compile-time ключи. По умолчанию
результат появляется в `system_apps\System`; для другого места передайте
`-OutputDirectory`. При `Markdown=1` отдельный `WBMP.APP` не создаётся:
графический `MARKDOWN.APP` обслуживает и `T2`, и `I1`, используя одну копию
WBMP-декодера. При `Markdown=0` и `Wbmp=1` обработчик `I1` находится в
`WBMP.APP`; `CHIP8.APP` обслуживает `C1`. В сборке без
графического экрана вместо полного компилятора Markdown используется отдельный
потоковый stripper: он преобразует исходник в plain text на месте и не линкует
графическую модель документа.

Сборщик не линкует Arduino-библиотеки внутрь APP. Общие функции resident
разрешаются через `--just-symbols`, поэтому нельзя смешивать `.APP` и `.bin`
из разных запусков сборки.
