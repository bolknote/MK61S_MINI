# MK61 USB Screen

Настольное приложение для особого режима прошивки MK61S Mini. Оно принимает
по USB графический framebuffer 192×64, атомарно применяет сжатые кадры,
передаёт нажатия виртуальной клавиатуры и одновременно даёт доступ к обычному
интерактивному терминалу устройства.

Это не зеркало LCD1602. После handshake прошивка гасит физический дисплей и
переключает весь интерфейс на графический UC1609-совместимый вид. Поэтому даже
у варианта с LCD1602 приложение показывает многострочный экран 192×64 без
ограничения в восемь CGRAM-символов.

## Требования к сборке

Воспроизводимая версия из CI - Flutter 3.41.9 stable с Dart 3.11.5. Перед
сборкой проверьте toolchain:

```sh
flutter --version
flutter doctor -v
flutter devices
```

Дополнительные требования платформ:

- macOS: Xcode, Command Line Tools и CocoaPods; deployment target 10.15;
- Windows: Visual Studio 2022 с workload **Desktop development with C++** и
  Windows SDK;
- Ubuntu/Debian: `clang cmake ninja-build pkg-config libgtk-3-dev
  libstdc++-12-dev`.

Если desktop-цель отсутствует, включите её командой
`flutter config --enable-macos-desktop`, `--enable-windows-desktop` или
`--enable-linux-desktop`, затем снова выполните `flutter doctor -v`.

## Быстрый запуск

В каталоге приложения получите закреплённые в `pubspec.lock` зависимости и
запустите нужную desktop-цель:

```sh
cd apps/mk61_usb_screen
flutter pub get
flutter run -d macos
```

На Windows используется `flutter run -d windows`, на Linux —
`flutter run -d linux`.

После запуска:

1. подключить калькулятор по USB;
2. выбрать на калькуляторе **Development → USB Screen** или
   **Разработка → USB-экран**;
3. оставить включённым автоподключение или выбрать CDC-порт вручную;
4. дождаться статуса «USB Screen подключён» — только тогда физический экран
   погаснет.

Если связь пропадёт, firmware через heartbeat timeout снова включает физический
экран. Удержание физической клавиши `ESC` 1,5 секунды также аварийно завершает
режим.

## Управление

Экранная клавиатура повторяет активную матрицу Mini, Classic или 40th, которую
прошивка сообщает при подключении. Для Mini/A00 она воспроизводит физический
порядок 5×8 и дополнительные надписи слоёв `F`, `K` и `a`…`e`.

Когда нижняя шторка терминала скрыта, клавиатура ПК направлена в MK61 и
интерпретируется как физическая US-QWERTY независимо от выбранного источника
ввода macOS, Windows или Linux. Приложение не переключает системный язык и не
затрагивает другие программы:

- цифры и цифровой блок — `0`…`9`;
- латинские `A`…`Z`; строчные буквы вводятся как прописные через штатный
  многонажатийный алфавит прошивки;
- `+`, `-`, `*`, `/`, `^`, точка, пробел и поддерживаемые редакторами знаки
  `! @ # $ % & ( ) : ; , " = ' < >`;
- стрелки `←↑↓→`, Backspace/Delete, Enter → `OK`, Escape → `ESC`;
- F1 → `K`, F2 → `F`, F3 → `USER`, F5 → `С/П`, F6 → `SAVE`, F7 → `LOAD`.

`Shift` выбирает символы американской раскладки; `Command`, `Control` и
`Option/Alt` не отправляются в устройство, чтобы системные сочетания не
превращались в нажатия MK61.

Неподдерживаемые печатные символы игнорируются. В меню и редакторах все события
остаются обычными клавишами матрицы, поэтому одинаково работают во всех трёх
раскладках. Клиент берёт scan-code из сообщённой прошивкой раскладки и передаёт
все клавиши ПК, включая стрелки, штатными командами `kbd XX` через terminal
multiplex. Повторные SMS-нажатия букв поэтому не теряются в пачке `down/up`.

При потере фокуса и закрытии приложение посылает `RELEASE_ALL_KEYS`, чтобы на
устройстве не оставалась логически зажатая клавиша.

## Терминал и скорость USB

Выдвижная нижняя панель «Терминал» использует тот же открытый CDC-порт одновременно
с экраном. При открытии фокус переходит в строку команды; она принимает обычный
UTF-8-текст с текущей системной раскладкой и не ограничена набором клавиш MK61.
`Esc` скрывает панель и возвращает фокус устройству.

Прошивка обслуживает terminal multiplex и внутри блокирующих редакторов FOCAL и
TinyBASIC. Поэтому скрытая панель может передавать `kbd`-команды, не дожидаясь
выхода из редактора.

В ней доступны обычные команды `help`, `ver`, `reg`, `ls` и остальные команды
firmware; отдельный serial terminal открывать не нужно и нельзя, пока порт занят
приложением.

Бинарные пакеты имеют границы `00 + COBS + 00`, а текст идёт между ними, поэтому
ответ команды не повреждает кадр. `115200` — только совместимое значение USB CDC
line coding: у STM32 native USB оно не ограничивает throughput, и замена числа на
`2500000` сама по себе не ускоряет передачу.

## Release-сборка

Собирать каждую desktop-цель нужно на соответствующей ОС. Из каталога
`apps/mk61_usb_screen` выполните одну команду:

```sh
flutter build macos --release
flutter build windows --release
flutter build linux --release
```

Результаты находятся соответственно в:

- `build/macos/Build/Products/Release/mk61_usb_screen.app`;
- `build/windows/x64/runner/Release/`;
- `build/linux/x64/release/bundle/`.

На Windows и Linux распространяйте весь каталог, не только исполняемый файл:
рядом находятся Flutter runtime, data и native-библиотека `libserialport`.

### macOS

```sh
flutter build macos --release
ditto -c -k --sequesterRsrc --keepParent \
  build/macos/Build/Products/Release/mk61_usb_screen.app \
  MK61-USB-Screen-macOS.zip
```

Приложение намеренно собирается без App Sandbox: прямой доступ к
`/dev/cu.usbmodem*` нужен `libserialport`. Workflow не подписывает и не
notarize-ит bundle; для публичного распространения эти шаги добавляются
отдельно.

### Windows

```powershell
flutter build windows --release
Compress-Archive `
  -Path build\windows\x64\runner\Release\* `
  -DestinationPath MK61-USB-Screen-Windows-x64.zip
```

Для стандартного USB CDC ACM отдельный драйвер обычно не нужен.

### Linux

```sh
sudo apt-get update
sudo apt-get install -y clang cmake ninja-build pkg-config \
  libgtk-3-dev libstdc++-12-dev
flutter build linux --release
tar -C build/linux/x64/release \
  -czf MK61-USB-Screen-Linux-x64.tar.gz bundle
```

Пользователь должен иметь доступ к последовательному порту, обычно через
группу `dialout`:

```sh
sudo usermod -aG dialout "$USER"
```

После добавления в группу требуется новый вход в систему.

### Чистая пересборка

После смены Flutter или при повреждённом native cache:

```sh
flutter clean
flutter pub get
flutter build macos --release
```

Последнюю строку замените на нужную платформу.

## Проверка

```sh
flutter analyze
flutter test
```

В набор входит сквозной fake-device тест настоящего `DeviceController`: serial
fragmentation, handshake, terminal/video multiplex, атомарный кадр, клавиши,
heartbeat, CRC/sequence recovery и повторное подключение после сброса сессии.
GitHub Actions workflow `.github/workflows/usb-screen-desktop.yml` сначала
выполняет анализ и тесты, затем нативно собирает готовые архивы на macOS,
Windows x64 и Linux x64. Artifacts хранятся 14 дней.

Описание wire protocol и состояний firmware находится в
[`../../doc/src/MK61s-mini-USB-Screen.md`](../../doc/src/MK61s-mini-USB-Screen.md).
