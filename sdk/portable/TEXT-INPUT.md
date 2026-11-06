# Текстовый ввод, потоковая запись и меню ABI 6

Расширения append-only: common services v2 и APP ABI 6 сохраняются.
Проверять capability через mk61_app_get_services/CAPABILITIES. Контракты C/C++
находятся в loadable_app_services.h и mk61_app.h, Rust — в mk61_app.rs.

## TEXT_INPUT

Capability бит 25, операция 46. Один сеанс принадлежит текущему APP.
Не читать одновременно keyboard API и TEXT_INPUT: они потребляют одну очередь.
Исходное событие сохраняется до преобразования клавиш калькулятора.

BEGIN получает mk61_service_text_event с layout=0 EN или 1 RU, reserved=0.
POLL копирует событие и возвращает 1, при отсутствии события — 0. END
закрывает сеанс и допускает NULL/c=0. Для BEGIN/POLL c=sizeof(event),
payload=event. Повторный BEGIN активного сеанса отвергается. C helper
mk61_app_text_input заполняет раскладку при BEGIN.

Событие: четыре u32 kind, value, layout, reserved. CHAR содержит M8-байт.
Остальные kinds: LEFT/RIGHT, BACKSPACE/DELETE, HOME/END_LINE, UP/DOWN,
PAGE_UP/PAGE_DOWN, SUBMIT/CANCEL/MENU/LAYOUT. Reserved возвращается 0.
F8 меняет layout и не вводит символ. Shift уже учтён клавиатурой.
ENTER/ESC/Tab передают причинный жест через handoff: удержание/повтор
не подтверждают следующий экран, соседняя независимая клавиша сохраняется.
Для стрелок и букв допускаются повторы. Возврат APP закрывает сеанс.

Оболочка отвечает за курсор, буфер, отмену без отправки и отрисовку.
МК-61 использует общий с SHEET helper code/phone_input.hpp с F/K/Cx.

## FILE_WRITE_SOURCE

Capability бит 26, операция 47. a=parent ID, b=preferred ID или INVALID_ID,
c=тип файла, payload=mk61_service_write_source: name, context, read, size, id.
Callback read(context,offset,out,size) возвращает ненулевое значение только
после заполнения полного диапазона.

Callback синхронный, может вызываться многократно и в произвольном порядке.
Контекст и данные остаются неизменными до возврата сервиса. Callback не
запускает другое APP и не меняет сериализуемое состояние. Указатели не
сохраняются файловой службой. Успех: 1 и id. Отказ: 0, прежний файл сохранён.
C helper mk61_app_file_write_source проверяет capability. Запись использует
существующий атомарный C9/FAT-путь без второй копии файла в RAM.

Типы URQ=13 (C2/.urq), URQ_DATA=14 (R1/.uqd), URQ_SAVE=15 (S2/.urs)
бинарные, до 61440 байт, без повторного прозрачного сжатия.

## Дополнительные сервисы

MENU_SOURCE (бит 28): MENU a=b=0, c=sizeof(menu_source). Структура: title,
context, count, selected, label. Callback label(context,index,out,capacity)
пишет NUL-терминированную M8-строку до 127 байт. Сервис прокручивает список,
возвращает 1/selected при OK, 0 при отмене. Старый c=0 формат меню сохранён.

NUMBER_FIXED (бит 29): NUMBER_FORMAT a=1 — фиксированная дробная часть,
a=2 — с целыми без дробной части. Обычные NUMBER_FORMAT/PARSE сохраняют
свой контракт. Точное ECMAScript-преобразование и URQL-подстановки теперь
входят в URQ.APP/URQUI.APP и не занимают resident Flash. ECMA_NUMBERS
(бит 31), NUMBER_FORMAT a=3/4 и NUMBER_PARSE a=1 зарезервированы для
совместимости с прежними пакетами SDK; текущая прошивка их не объявляет.
Устанавливайте URQ и URQUI из одного комплекта с прошивкой.

SETUP_FEATURE_RTC_VALUE (бит 9 в SETUP/FEATURES) предоставляет SETUP/RTC_VALUE:
b=0 — местные секунды с полуночи, b=1 — номер местного календарного дня от
1970-01-01; c=0, payload=NULL. Преобразуются гражданские показания RTC,
без неявного смещения часового пояса. Режим RTC_READ со структурой сохранён.

TEXT_COLORS (бит 30, цветной native-дисплей): DISPLAY/UI_COLORS получает
b=foreground, c=background RGB565, payload=NULL. Применяется к следующим
UI_LINE/WRITE. UI_RUN_COLORS: b=row, c=count<=64, payload=u16[count] —
синхронно копируемые цвета отдельных символов. Шрифты и координаты совпадают
с монохромным выводом. END_UI_TEXT завершает цветной сеанс. Прямоугольник
COLOR_DISPLAY с флагом COLOR_PRESERVE_OUTSIDE сохраняет пиксели снаружи;
остальные вызовы COLOR_DISPLAY сохраняют прежнее поведение заливки фона.

## FILE_OPEN и APP flow

Hook mk61_app_file_flow возвращает FLOW_MAGIC, разрешая FILE_INFO=5.
Тогда FILE_OPEN начинает cooperative STEP в FILE_PHASE=2; первые четыре байта
64-байтного context содержат document ID. Без opt-in используется прежний
FILE_OPEN=2. Контекст, аренды и возврат описаны в app_flow.h. Нельзя загружать
второй образ из живого callback: URQ делает CALL после возврата STEP.
