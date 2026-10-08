"""Design artefacts only: render proposed screens using the firmware's fonts."""
from pathlib import Path
import html
import json
import re

from PIL import Image, ImageDraw, ImageFont


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = (ROOT / "code/ERM19264_graphics_font.cpp").read_text()
BUILTIN = (ROOT / "code/builtin_font.cpp").read_text()


def table(source, name):
    match = re.search(r"\b" + name + r"\[\][^{]*\{(.*?)\n\};", source, re.S)
    if not match:
        raise ValueError(name)
    return re.sub(r"//[^\n]*", "", match.group(1))


ASCII5 = [int(v, 16) for v in re.findall(r"0x[0-9A-Fa-f]+", table(SOURCE, "UC_Font_One"))]
ASCII3 = [int(v, 16) for v in re.findall(r"0x[0-9A-Fa-f]+", table(SOURCE, "UC_Font_3x5"))]


def row_glyphs(source):
    glyphs = {}
    for cp, rows in re.findall(r"\{(0x[0-9A-Fa-f]+),\s*\{([^{}]+)\}\}", source):
        values = [int(v.strip(), 0) for v in rows.split(",") if v.strip()]
        glyphs[chr(int(cp, 16))] = values
    return glyphs


ROWS5 = row_glyphs(BUILTIN)
ROWS3 = row_glyphs(SOURCE)
ALIASES3 = {"←": 0x0D, "→": 0x0C, "↑": 0x0B, "π": 0x0A, "√": 0x09, "÷": 0x08}


class Screen:
    def __init__(self, compact=False):
        self.image = Image.new("1", (192, 64), 1)
        self.draw = ImageDraw.Draw(self.image)
        self.compact = compact
        self.w, self.h, self.advance = (3, 5, 4) if compact else (5, 8, 6)

    def text(self, x, y, text, inverse=False):
        if x < 0 or y < 0 or x + len(text) * self.advance > 192 or y + self.h > 64:
            raise ValueError(f"Text outside display: {x}, {y}, {text}")
        if inverse:
            self.draw.rectangle((x, y, x + len(text) * self.advance - 1, y + self.h - 1), fill=0)
        for ch in text:
            cp = ord(ch)
            rows = ROWS3.get(ch) if self.compact else ROWS5.get(ch)
            if self.compact and rows is None:
                cp = ALIASES3.get(ch, cp)
                if cp >= 128:
                    raise ValueError(f"Missing compact glyph: {ch}")
                rows = ASCII3[cp * 5:cp * 5 + 5]
            if not self.compact and rows is None and cp >= 128:
                raise ValueError(f"Missing glyph: {ch}")
            for gy in range(self.h):
                for gx in range(self.w):
                    if rows is not None:
                        bit = gx if self.compact else self.w - 1 - gx
                        on = bool(rows[gy] & (1 << bit))
                    else:
                        on = bool(ASCII5[cp * 5 + gx] & (1 << gy))
                    if on:
                        self.image.putpixel((x + gx, y + gy), 1 if inverse else 0)
            x += self.advance

    def band(self, y, text):
        self.draw.rectangle((0, y, 191, y + 7), fill=0)
        self.text(2, y, text, inverse=True)


DATA = [
    ["КОЛ-ВО", "ЦЕНА", "СУММА", "НАЛОГ"],
    ["2", "125", "250", "50"],
    ["3", "80", "240", "48"],
    ["1", "350", "350", "70"],
    ["", "ИТОГО", "840", "168"],
    ["", "", "", ""],
    ["", "", "", ""],
]


def grid(compact=False, picking=False, error=False, anchor=0):
    screen = Screen(compact)
    step, header_y, start_y, footer_y = (6, 6, 12, 56) if compact else (8, 8, 16, 56)
    columns, rows = (4, 7) if compact else (3, 5)
    column_width = 180 // columns
    if picking:
        reference = ["B2", "$B2", "B$2", "$B$2"][anchor]
        screen.text(0, 0, f"ССЫЛКА: {reference} → C2")
        screen.text(162, 0, "125")
    elif error:
        screen.text(0, 0, "C2: ЦИКЛ C2 → C3 → C2")
    else:
        screen.text(0, 0, "C2 = A2 В↑ B2 ×")
        screen.text(174 if compact else 168, 0, "DEG")
    screen.draw.rectangle((0, header_y, 191, header_y + step - 1), fill=0)
    for c in range(columns):
        x = 13 + c * column_width
        screen.text(x + (column_width - screen.advance) // 2, header_y, chr(65 + c), inverse=True)
    for r in range(rows):
        y = start_y + r * step
        screen.text(0, y, str(r + 1))
        for c in range(columns):
            left = 13 + c * column_width
            right = min(left + column_width - 1, 191)
            selected = (r == 1 and c == (1 if picking else 2))
            value = "#ЦИКЛ" if error and r in (1, 2) and c == 2 else DATA[r][c]
            if selected:
                screen.draw.rectangle((left, y, right, y + step - 1), fill=0)
            numeric = value[:1].isdigit() or value.startswith("#")
            x = right - len(value) * screen.advance if numeric else left + 2
            if value:
                screen.text(x, y, value, inverse=selected)
            if picking and r == 1 and c == 2:
                screen.draw.rectangle((left, y, right, y + step - 1), outline=0)
    for c in range(columns):
        x = 12 + c * column_width
        screen.draw.line((x, header_y, x, start_y + rows * step - 1), fill=0)
    screen.draw.line((0, 55, 191, 55), fill=0)
    footer = "OK:ВСТАВИТЬ USER:ФИКС ESC:НАЗАД" if picking else "OK:ПРАВКА  USER:МЕНЮ"
    if error:
        footer = "OK:ПРАВКА  USER:ПРИЧИНА"
    screen.text(0, footer_y, footer)
    return screen.image


def editor():
    screen = Screen()
    screen.band(0, "C2  ФОРМУЛА                 DEG")
    screen.text(2, 10, "A2 В↑ B2 ")
    screen.text(56, 10, "×", inverse=True)
    screen.text(2, 24, "РЕЗУЛЬТАТ: 250")
    screen.text(2, 32, "A2=2     B2=125")
    screen.text(2, 40, "USER:ССЫЛКА  Cx:УДАЛИТЬ")
    screen.text(2, 48, "←→:ШАГ  F/K:ФУНКЦИИ")
    screen.band(56, "OK:ЗАПИСАТЬ  ESC:ОТМЕНА")
    return screen.image


def actions():
    screen = Screen()
    screen.band(0, "C2  ДЕЙСТВИЯ")
    items = ["ОТМЕНИТЬ", "КОПИРОВАТЬ", "ЗАПОЛНИТЬ ВНИЗ", "ОЧИСТИТЬ", "ТИП/ФОРМАТ", "ЛИСТ..."]
    for i, item in enumerate(items):
        y = 8 + i * 8
        if i == 2:
            screen.band(y, "→ " + item)
        else:
            screen.text(14, y, item)
    screen.band(56, "OK:ВЫБОР  ESC:НАЗАД")
    return screen.image


SCREENS = {
    "01-sheet": grid(),
    "02-compact": grid(compact=True),
    "03-formula": editor(),
    "04-reference": grid(picking=True),
    "05-actions": actions(),
    "06-cycle": grid(error=True),
    "07-fixed-column": grid(picking=True, anchor=1),
    "08-fixed-row": grid(picking=True, anchor=2),
    "09-fixed-both": grid(picking=True, anchor=3),
}

PAPER = "#f5f3ed"
INK = "#202a25"
MUTED = "#5b6761"
ACCENT = "#376047"
FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"


def font(size, bold=False):
    return ImageFont.truetype(BOLD if bold else FONT, size)


def label(image, xy, text, size=24, bold=False, color=INK):
    ImageDraw.Draw(image).text(xy, text, font=font(size, bold), fill=color)


def lcd(image, xy, screen, scale=4):
    x, y = xy
    draw = ImageDraw.Draw(image)
    w, h = 192 * scale, 64 * scale
    draw.rounded_rectangle((x - 14, y - 14, x + w + 14, y + h + 14), radius=18, fill="#25302a")
    dark, light = (27, 43, 30), (216, 226, 192)
    rgb = Image.new("RGB", screen.size)
    rgb.putdata([light if value else dark for value in screen.get_flattened_data()])
    image.paste(rgb.resize((w, h), Image.Resampling.NEAREST), (x, y))


def comparison():
    image = Image.new("RGB", (1720, 720), PAPER)
    label(image, (48, 30), "ТАБЛИЦА НА МК-61s", 42, True)
    label(image, (49, 87), "Один экран 192×64. Два варианта плотности. Масштаб обоих экранов — ×4.", 24, color=MUTED)
    label(image, (48, 150), "01 / Основной режим", 28, True)
    label(image, (900, 150), "02 / Обзор", 28, True)
    lcd(image, (48, 220), SCREENS["01-sheet"])
    lcd(image, (900, 220), SCREENS["02-compact"])
    for x, lines in [(48, ["5×8 · 3 столбца × 5 строк", "Формула сверху, результат в ячейке.", "Выбранный режим по умолчанию."]),
                     (900, ["3×5 · 4 столбца × 7 строк", "Больше соседних ячеек на экране.", "Мелкий шрифт — проверить на приборе."])]:
        for i, line in enumerate(lines):
            label(image, (x, 516 + i * 39), line, 25, i == 0, ACCENT if i == 0 else INK)
    label(image, (48, 663), "Без новых кнопок: ← → — столбец; ШГ− / ШГ+ — строка; OK — правка; USER — действия.", 23, color=MUTED)
    return image


def workflow():
    image = Image.new("RGB", (1720, 1060), PAPER)
    label(image, (48, 26), "КАК ВВЕСТИ ФОРМУЛУ", 42, True)
    label(image, (49, 81), "C2 = A2 В↑ B2 ×   →   2 × 125 = 250", 27, color=MUTED)
    cards = [
        (48, 146, "1 / Выбрать C2", "01-sheet", ["Таблица показывает значения.", "OK открывает содержимое ячейки."]),
        (900, 146, "2 / Набирать как на калькуляторе", "03-formula", ["Числа, В↑, операции и функции F/K.", "USER временно включает выбор ссылки."]),
        (48, 575, "3 / Указать ячейку", "04-reference", ["B2 выделена; рамка удерживает цель C2.", "OK вставляет ссылку, USER фиксирует адрес ($)."]),
        (900, 575, "4 / Копировать формулу", "05-actions", ["После записи: USER → «Заполнить вниз».", "C3 = A3 В↑ B3 ×; C4 = A4 В↑ B4 ×."]),
    ]
    for x, y, title, key, lines in cards:
        label(image, (x, y), title, 27, True)
        lcd(image, (x, y + 71), SCREENS[key])
        for i, line in enumerate(lines):
            label(image, (x, y + 354 + i * 33), line, 23, color=MUTED)
    label(image, (48, 1006), "OK записывает формулу; ESC отменяет черновик. Пересчёт зависимых ячеек — автоматически.", 23, color=ACCENT)
    return image


def reference_modes():
    image = Image.new("RGB", (1720, 1020), PAPER)
    label(image, (48, 26), "КАК ЗАКРЕПИТЬ ССЫЛКУ", 42, True)
    label(image, (49, 81), "USER открывает выбор ячейки. В этом режиме USER переключает фиксацию; OK вставляет ссылку.", 23, color=MUTED)
    cards = [
        (48, 146, "1 / B2 — относительная", "04-reference", "При копировании меняются строка и столбец."),
        (900, 146, "2 / $B2 — закрепить столбец", "07-fixed-column", "Столбец B остаётся, номер строки меняется."),
        (48, 560, "3 / B$2 — закрепить строку", "08-fixed-row", "Строка 2 остаётся, буква столбца меняется."),
        (900, 560, "4 / $B$2 — закрепить оба", "09-fixed-both", "При копировании ссылка всегда ведёт в B2."),
    ]
    for x, y, title, key, caption in cards:
        label(image, (x, y), title, 27, True)
        lcd(image, (x, y + 64), SCREENS[key])
        label(image, (x, y + 350), caption, 23, color=MUTED)
    label(image, (48, 970), "Цикл: B2 → $B2 → B$2 → $B$2 → B2. Символ $ появляется в адресе автоматически.", 24, color=ACCENT)
    return image


SPEC = {
    "status": "UI proposal; not a firmware implementation",
    "accepted_by_user": "5x8, 3 columns x 5 rows as default; 3x5 as overview",
    "target": "MK61s UC1609 / USB screen, 192x64 monochrome",
    "default": {"font": "firmware 5x8", "visible_columns": 3, "visible_rows": 5},
    "overview": {"font": "firmware Compact 3x5", "visible_columns": 4, "visible_rows": 7},
    "formula_input": "MK61 RPN keystrokes; a cell reference behaves as numeric entry into X",
    "example": {"A2": 2, "B2": 125, "C2": "=A2 В↑ B2 ×", "result": 250},
    "keymap": {
        "sheet": {"left/right": "column", "SHG-/SHG+": "row", "OK": "edit", "digit": "replace with number draft", "USER": "actions", "ESC": "leave sheet"},
        "editor": {"left/right": "previous/next token", "digit, operations, F, K, В↑": "calculator input", "USER": "pick reference", "Cx": "delete token / last digit", "OK": "commit", "ESC": "cancel draft"},
        "reference": {"left/right": "column", "SHG-/SHG+": "row", "OK": "insert reference", "USER": "cycle A2 / $A2 / A$2 / $A$2", "ESC": "return to draft"},
    },
    "cell_types": ["number", "text", "formula"],
    "new_cell": "One numeric literal commits as a number. A reference or calculator operation promotes the draft to a formula; no equals key is needed. Text is entered through USER > type/format > text using the existing alpha editor.",
    "copying": "Relative addresses shift by destination offset; $ fixes row or column. Structural insert/delete tracks referenced cells.",
    "recalculation": "After commit, recalculate only dependent cells. Formula evaluation uses its own initialized stack. Angle mode DEG/RAD/GRD is saved with the sheet.",
    "errors": {"#ЦИКЛ": "dependency cycle with path in detail view", "#ССЫЛ": "deleted or invalid cell", "#ЧИСЛО": "domain or numeric range", "#ТИП": "text used as a numeric operand"},
    "blank_reference": "0; text references are errors",
    "formatting": "Never silently truncate a number; use scientific format or #####, with full value in cell details. Text can be cropped with an overflow marker.",
    "scope": "First version: one sheet, navigation, numbers/text/formulas, reference picker, copy/fill, undo, save/load. Finite sheet size and budgets require measurement before implementation.",
    "determinism": "Use pure calculator operations. No dependence on current calculator registers, random inputs, I/O, or program control flow in the first version.",
    "open_decisions": ["physical readability of 3x5", "text entry through the existing alpha editor", "sheet size and memory budget", "autosave policy and file format", "save/load UI"],
    "native_screen_files": [f"{key}-192x64.png" for key in SCREENS],
}


def review_html():
    options = [
        ("01-sheet", "Таблица", "Режим по умолчанию: 5×8, 3 столбца и 5 строк. Сверху — формула выбранной ячейки; внутри таблицы — её результат."),
        ("02-compact", "Обзор", "3×5, 4 столбца и 7 строк. Это дополнительный обзор; читаемость нужно проверить на физическом дисплее."),
        ("03-formula", "Формула", "Лента операций МК-61. USER выбирает ссылку, ←/→ перемещаются между шагами. OK записывает черновик, ESC отменяет."),
        ("04-reference", "Ссылка", "B2 выделена инверсией, цель C2 остаётся в рамке. OK вставляет ссылку. USER переключает B2 / $B2 / B$2 / $B$2."),
        ("05-actions", "Действия", "Копирование, заполнение вниз, отмена, тип, формат и очистка — в одном меню. «Лист…» ведёт к сохранению, открытию и настройкам листа."),
        ("06-cycle", "Ошибка", "Цикл показан в ячейке и строке состояния. Подробности объясняют причину, соседние независимые значения остаются доступными."),
        ("09-fixed-both", "Фиксация", "В выборе ячейки USER переключает B2 → $B2 → B$2 → $B$2 → B2. Символ $ появляется автоматически; OK вставляет выбранный вариант ссылки."),
    ]
    buttons = "".join(f'<button data-screen="{key}" aria-pressed="{str(i == 0).lower()}">{html.escape(title)}</button>' for i, (key, title, _) in enumerate(options))
    descriptions = {key: desc for key, _, desc in options}
    data = json.dumps(descriptions, ensure_ascii=False).replace("</", "<\\/")
    return f'''<!doctype html>
<html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Таблица МК-61s — проект интерфейса</title>
<style>
:root{{color-scheme:light;--ink:#202a25;--muted:#5b6761;--paper:#f5f3ed;--green:#376047}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:17px/1.6 system-ui,sans-serif}}main{{max-width:1120px;margin:auto;padding:48px 28px}}.eyebrow{{font-size:13px;letter-spacing:.12em;color:var(--green)}}h1{{font-size:clamp(32px,5vw,56px);line-height:1.1;margin:12px 0 20px}}h2{{font-size:26px;margin-top:42px}}p{{max-width:850px}}.lead{{font-size:21px;color:var(--muted)}}nav{{display:flex;gap:8px;flex-wrap:wrap;margin:28px 0 22px}}button{{font:inherit;padding:8px 16px;background:transparent;border:1px solid #b3bdb4;border-radius:7px;cursor:pointer}}button[aria-pressed=true]{{background:var(--green);color:white;border-color:var(--green)}}.lcd{{background:#25302a;border:16px solid #25302a;border-radius:16px;max-width:992px}}.lcd img{{width:100%;display:block;image-rendering:pixelated}}.caption{{color:var(--muted);min-height:64px}}.boards img{{max-width:100%;height:auto;border-radius:8px}}table{{border-collapse:collapse;width:100%;max-width:940px}}td,th{{border-bottom:1px solid #d5dcd4;padding:12px;text-align:left;vertical-align:top}}code{{background:#e6eade;padding:3px 6px;border-radius:4px}}.note{{padding:20px 24px;background:#e6eade;border-radius:8px;margin:24px 0}}a{{color:var(--green)}}small{{color:var(--muted)}}
</style><main>
<div class="eyebrow">МК-61s / КОНЦЕПЦИЯ 01 / 8 ОКТЯБРЯ 2026</div>
<h1>Таблица, которая считает<br>как калькулятор</h1>
<p class="lead">Лист с адресами A1, B2… Формула — последовательность операций МК-61 со ссылками на ячейки. Макеты используют настоящие растры 5×8 и 3×5 из прошивки; исходные экраны — ровно 192×64.</p>
<nav aria-label="Макеты экранов">{buttons}</nav>
<div class="lcd"><img id="screen" src="01-sheet-preview.png" alt="Предлагаемый экран таблицы МК-61s"></div>
<p id="caption" class="caption">{html.escape(options[0][2])}</p>
<small>Переключатель показывает состояния макета. Ввод формул и вычисления здесь не реализованы.</small>
<h2>Выбранная компоновка</h2>
<p>Основной вид — <strong>3 столбца × 5 строк, шрифт 5×8</strong>. Компактный режим 3×5 — для обзора. Верхняя строка всегда принадлежит выбранной ячейке, нижняя — доступным действиям. Заголовок приложения не занимает место в рабочем экране.</p>
<div class="boards"><img src="imagegen-concept.png" alt="Иллюстрация предложенного интерфейса на концептуальном приборе с графическим дисплеем"><p><small>Иллюстрация компоновки, созданная встроенным imagegen. Корпус взят как визуальный ориентир; это концепт графического прибора. Точную геометрию показывают следующие пиксельные макеты. <a href="imagegen-prompt.txt">Промпт генерации</a>.</small></p><img src="layout-options.png" alt="Сравнение двух вариантов плотности таблицы"><img src="formula-workflow.png" alt="Выбор C2, ввод формулы, выбор ссылки B2 и заполнение вниз"></div>
<h2>Ввод формулы</h2>
<p>Пример: в A2 записано 2, в B2 — 125. Для C2 вводим <code>A2 В↑ B2 ×</code> и получаем 250. Ссылки вставляются выбором ячейки: печатать латинские адреса на приборе не требуется. Знак <code>=</code> на экране означает формулу и добавляется автоматически.</p>
<p>Ссылка ведёт себя как ввод числа в X по правилам МК-61; <code>В↑</code> отделяет операнды, а <code>OK</code> сохраняет всю формулу. Пользователь редактирует последовательность операций; читабельный результат появляется сразу, когда черновик можно вычислить.</p>
<p>В новой ячейке одиночное число сохраняется как число. Как только добавлена ссылка или операция, черновик становится формулой. Отдельная клавиша «=» не нужна. Подпись вводится через <code>USER → Тип/формат → Текст</code> существующим буквенным редактором.</p>
<h2>Как закрепить адрес</h2>
<p>В режиме выбора ссылки <strong>USER</strong> переключает <code>B2 → $B2 → B$2 → $B$2 → B2</code>. Эти варианты означают свободную ссылку, закреплённый столбец B, закреплённую строку 2 и закрепление обоих. <strong>OK</strong> вставляет ссылку. Символ <code>$</code> появляется автоматически; набирать его буквенным редактором не требуется.</p>
<div class="boards"><img src="reference-modes.png" alt="Четыре режима фиксации ссылки B2, переключаемые кнопкой USER"></div>
<table><tr><th>Клавиша</th><th>В таблице</th><th>В формуле</th></tr>
<tr><td>← / →</td><td>Столбец</td><td>Предыдущий / следующий шаг</td></tr>
<tr><td>ШГ− / ШГ+</td><td>Строка вверх / вниз</td><td>Переход по строкам при выборе ссылки</td></tr>
<tr><td>OK</td><td>Редактировать</td><td>Записать; в выборе ссылки — вставить</td></tr>
<tr><td>USER</td><td>Действия с ячейкой и листом</td><td>Выбрать ссылку; в выборе ссылки — фиксация адреса $</td></tr>
<tr><td>Цифры, В↑, + − × ÷, F, K</td><td>Цифра начинает черновик нового значения</td><td>Обычный ввод калькулятора, включая функции</td></tr>
<tr><td>Cx</td><td>Очистка через меню действий</td><td>Удалить цифру / выбранный шаг</td></tr>
<tr><td>ESC</td><td>Выйти из листа</td><td>Отменить черновик; из выбора ссылки — вернуться к черновику</td></tr></table>
<h2>Поведение ячеек</h2>
<p>Три типа: число, подпись, формула. При копировании C2 в C3 относительные ссылки A2 и B2 становятся A3 и B3. USER в выборе ссылки переключает <code>A2</code>, <code>$A2</code>, <code>A$2</code>, <code>$A$2</code>. Фиксация действует на копирование; при вставке или удалении строк ссылка следует за исходной ячейкой.</p>
<p>После записи меняются только зависимые ячейки. Каждая формула считает с собственным начальным стеком; режим углов DEG/RAD/GRD хранится в листе. Пустая ячейка в числовой формуле даёт 0, ссылка на текст — ошибку типа.</p>
<p>Ошибки локальны: <code>#ЦИКЛ</code>, <code>#ССЫЛ</code>, <code>#ЧИСЛО</code>, <code>#ТИП</code>. Полное значение и объяснение ошибки открываются в деталях ячейки. Число не обрезается до другого числа: сначала научная запись, затем <code>#####</code>, если оно всё ещё не помещается.</p>
<div class="note"><strong>Первая версия:</strong> один лист, числа и подписи, формулы, выбор ссылок, копирование и заполнение, отмена, сохранение и открытие. Функции — чистые операции калькулятора; размер листа, память, формат файла и скорость пересчёта требуют отдельного измерения.</div>
<p>Следующие решения: проверка шрифта на физическом экране, ввод подписей через существующий текстовый редактор, полный экран сохранения/открытия, политика автосохранения. Макет 16×2 можно спроектировать отдельно как просмотр одной ячейки.</p>
<p><a href="ui-proposal.json">Структурированная спецификация</a> · <a href="render_mockups.py">Исходник растровых макетов</a></p>
</main><script>
const captions={data};
document.querySelectorAll('button[data-screen]').forEach(button=>button.addEventListener('click',()=>{{
 document.querySelectorAll('button[data-screen]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));
 document.getElementById('screen').src=button.dataset.screen+'-preview.png';
 document.getElementById('caption').textContent=captions[button.dataset.screen];
}}));
</script></html>'''


if __name__ == "__main__":
    for key, screen in SCREENS.items():
        screen.save(HERE / f"{key}-192x64.png")
        dark, light = (27, 43, 30), (216, 226, 192)
        native = Image.new("RGB", screen.size)
        native.putdata([light if value else dark for value in screen.get_flattened_data()])
        native.resize((768, 256), Image.Resampling.NEAREST).save(HERE / f"{key}-preview.png")
    comparison().save(HERE / "layout-options.png")
    workflow().save(HERE / "formula-workflow.png")
    reference_modes().save(HERE / "reference-modes.png")
    (HERE / "ui-proposal.json").write_text(json.dumps(SPEC, ensure_ascii=False, indent=2) + "\n")
    (HERE / "index.html").write_text(review_html())
    print(f"Rendered {len(SCREENS)} native screens, three boards and {HERE / 'index.html'}")
