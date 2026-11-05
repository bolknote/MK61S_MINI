# Иллюстрации устройств для README

Готовые изображения: [`img/devices`](../../img/devices/). Размер каждого —
2000×1124. Это иллюстрации внешнего вида, а не монтажные чертежи.

PicoCalc — предоставленный пользователем готовый рендер, скопированный без
изменений. Основы mini, Classic и 40th созданы встроенным `image_gen`:
[финальные промпты](prompts.json). Фотографии пользователя служили ориентиром
по компоновке и механике. Исходное фото mini —
[`img/mk-61s-mini-c.jpg`](../../img/mk-61s-mini-c.jpg).

По замечаниям пользователя приняты маленькие стандартные цилиндрические
толкатели mini/Classic, убраны декоративные дорожки Classic, уменьшены
кнопки 40th. Последнее поручение по mini — оставить корпус без выступающих
переключателей. Верхний переключатель и наружный USB-разъём удалены вручную
в [`clean_mini.py`](clean_mini.py); клавиатура и корпус при этой операции
не меняются. Оригинал до ручной правки сохранён как
`bases/mini-original.png`, очищенная основа — `bases/mini.png`.

Надписи не генерировались нейросетью и не набирались похожим шрифтом.
По предложению пользователя на основы наложены сами векторные контуры
шелкографии из Gerber-файлов UN7FGO:

- [mini, передняя панель](https://github.com/UN7FGO/MK61S_MINI/blob/main/gerbers/Gerber_MK61S_MINI_V3_SHIELD.zip);
- [Classic, клавиатура](https://github.com/UN7FGO/MK-61s-Classic/blob/main/Gerber_MK61S_MINI_V3_Classic_Keyboard.zip)
  и [название на основной плате](https://github.com/UN7FGO/MK-61s-Classic/blob/main/Gerber_MK61S_MINI_V3_Classic_MainBoard.zip);
- [40th, передняя панель с юбилейными надписями](https://github.com/UN7FGO/MK52S/blob/main/gerber/Gerber_MK_52s_40_Th_shield.zip).

Слои клавиатур в [`sources/`](sources/) сохранены без изменений. Для названия
Classic оставлены только исходные полигональные контуры букв из основной платы.
Авторство рисунков — UN7FGO. Исходные репозитории mini и 40th распространяются
под GPLv3; текст совпадает с [лицензией проекта](../../LICENSE).
Адреса архивов и контрольные суммы сохранены в [`sources.json`](sources.json).

Вручную задана только привязка к геометрии рендеров в [`layout.json`](layout.json).
[`silkscreen.py`](silkscreen.py) переносит все 40 ячеек каждого устройства,
сохраняя исходные символы, F/K-функции и буквенные метки. Основные подписи
слегка уменьшены относительно ячейки, чтобы не заходить под тени толкателей;
угловые метки не уменьшаются. Верхний ряд 40th подписан над кнопками, как на фото.
Юбилейные строки и название mini взяты из тех же исходных контуров.
Результат — редактируемые `mini.svg`, `classic.svg`, `40th.svg` и итоговые PNG.

Функции также сверены с
[фотографией исходной «Электроники МК-61»](https://calculator-museum.nl/calculators/pictures/elektronika-mk61.png).

Содержимое дисплеев — статическое состояние с нулём. Растр UC1609 получен
настоящим `calculator_face`, LCD1602 использует штатный шрифт 5×8.
Это иллюстрация интерфейса, не аппаратный снимок и не свидетельство
тестирования подключённого калькулятора. Растры сохранены в `display.json`;
их небольшой генератор — [`display.cpp`](display.cpp).

Для повторного экспорта нужны Python 3, Pillow и `rsvg-convert`;
установка шрифтов не требуется:

```sh
python3 doc/readme-renders/clean_mini.py
python3 doc/readme-renders/render.py mini classic 40th
```

Для обновления растра дисплеев из корня проекта:

```sh
clang++ -std=c++17 -O2 -DMK61_CORE_STANDALONE=1 -DMK61_DISPLAY_UC1609 -Icode \
  doc/readme-renders/display.cpp code/calculator_face.cpp code/text_screen.cpp \
  code/builtin_font.cpp code/ERM19264_graphics_font.cpp code/fmk_font.cpp \
  -o /tmp/mk61-readme-display
/tmp/mk61-readme-display doc/readme-renders/display.json
```
