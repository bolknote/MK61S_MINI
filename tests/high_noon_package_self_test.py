#!/usr/bin/env python3
"""Offline completeness and layout checks for the split High Noon port."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def quoted_payload(path: Path) -> str:
    return compact("".join(re.findall(r'"([^"]*)"', path.read_text(encoding="utf-8"))))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
game = root / "programs" / "games" / "High Noon"
parts = [game / name for name in ("intro.tbi", "player.tbi", "bart.tbi", "reward.tbi")]
driver = game / "autoexec.m61"
manual = game / "manual.md"
font = game / "HighNoon.FMK"

require(driver.is_file(), "High Noon autoexec.m61 is missing")
require(driver.stat().st_size <= 1536, "High Noon M61 dispatcher exceeds 1536 bytes")
require(manual.is_file() and manual.stat().st_size <= 1536,
        "High Noon manual exceeds the Markdown quota")
require(font.is_file(), "High Noon local FMK is missing")
font_data = font.read_bytes()
require(font_data[:4] == b"FMK1", "High Noon local FMK is invalid")
require(font_data[4] == 0, "High Noon Russian FMK must be proportional")
require(font_data[5:8] == bytes((5, 5, 0x31)),
        "High Noon Russian FMK has unexpected geometry")
require(int.from_bytes(font_data[8:10], "little") == 65,
        "High Noon Russian FMK has an unexpected glyph count")
require(font_data[10] == 3, "High Noon Russian FMK must have three ranges")
font_ranges = tuple(
    (int.from_bytes(font_data[16 + offset:18 + offset], "little"),
     font_data[18 + offset] + 1)
    for offset in range(0, 9, 3)
)
require(font_ranges == ((0x20, 0x20), (0x0401, 1), (0x0410, 0x20)),
        "High Noon FMK must contain symbols/digits and Russian uppercase only")

# The letters most easily confused in a 3x5 cell must retain their wider
# records.  Decode just the per-glyph metrics; the common FMK tests validate
# every bitmap and CRC in full.
bit = (16 + 3 * font_data[10]) * 8
font_widths = {}
font_advances = {}
font_bitmaps = {}


def read_font_bits(count: int) -> int:
    global bit
    value = 0
    for _ in range(count):
        value = (value << 1) | ((font_data[bit // 8] >>
                                 (7 - bit % 8)) & 1)
        bit += 1
    return value


for first, count in font_ranges:
    for codepoint in range(first, first + count):
        width = read_font_bits(4) + 1
        advance = read_font_bits(4) + 1
        font_widths[codepoint] = width
        font_advances[codepoint] = advance
        require(advance == width + 1,
                f"High Noon FMK U+{codepoint:04X} lost its one-pixel gap")
        mode = read_font_bits(1)
        require(mode == 0, "High Noon generator unexpectedly emitted RLE")
        font_bitmaps[codepoint] = tuple(read_font_bits(width) for _ in range(5))
require(font_widths[ord("$")] == 5,
        "High Noon dollar must use its readable wide glyph")
require(font_bitmaps[ord("$")] == (0b01110, 0b10100, 0b01110, 0b00101, 0b01110),
        "High Noon dollar bitmap is no longer recognizable")
for letter in "ДЖИЙЛМФШЩЫЮЯ":
    require(font_widths[ord(letter)] == 5,
            f"High Noon Russian {letter} must use its readable wide glyph")
require(not (root / "programs" / "Fonts" / "HighNoon.FMK").exists(),
        "High Noon FMK must not be duplicated in the global Fonts directory")
for path in parts:
    require(path.is_file(), f"High Noon part is missing: {path.name}")
    data = path.read_bytes()
    require(len(data) <= 3584, f"{path.name} exceeds the TinyBASIC quota")
    require(len(data) + data.count(b"\n") <= 3584,
            f"{path.name} would exceed the quota after LF-to-CRLF conversion")

driver_text = driver.read_text(encoding="utf-8")
for line in (
    "reinit",
    "loadfont HighNoon",
    "open intro.tbi",
    "if re==1 run :player",
    "if re==2 run :bart",
    "if re==3 run :bart",
    "if re==80 run :reward",
    "open player.tbi",
    "open bart.tbi",
    "open reward.tbi",
):
    require(line in driver_text, f"High Noon dispatcher lost: {line}")
require("LOADFONT" not in "".join(path.read_text(encoding="utf-8") for path in parts).upper(),
        "High Noon must select its font in M61, not TinyBASIC")

# These phrases cover every scene of the complete Russian translation.
# Whitespace is ignored because its deterministic 47-cell page layout may
# split one sentence across adjacent PRINT statements.
required_text = (
    "Р О В Н О  В  П О Л Д Е Н Ь",
    "----------------",
    "ПОКАЗАТЬ ИНСТРУКЦИЮ? 1 ДА 0 НЕТ",
    "ЧЁРНЫЙ БАРТ ВЫЗВАЛ ВАС НА ДУЭЛЬ.",
    "ЭТО ОДИН ИЗ САМЫХ ОПАСНЫХ БАНДИТОВ К ЗАПАДУ ОТ АЛЛЕГАНСКИХ ГОР.",
    "ВЫ ИДЁТЕ ПО ПЫЛЬНОЙ ПУСТЫННОЙ УЛИЦЕ. ИЗ САЛУНА ВЫХОДИТ ЧЁРНЫЙ БАРТ.",
    "МЕЖДУ ВАМИ СТО ШАГОВ.",
    "У КАЖДОГО ПО ЧЕТЫРЕ ПАТРОНА В РЕВОЛЬВЕРЕ. СТРЕЛЯЕТЕ ВЫ ОДИНАКОВО МЕТКО.",
    "В НАЧАЛЕ ПУТИ НИКТО НЕ МОЖЕТ ПОПАСТЬ, НО В КОНЦЕ УЖЕ НИКТО НЕ ПРОМАХНЁТСЯ.",
    "ЧЕМ ВЫ БЛИЖЕ, ТЕМ ВЫШЕ ВАШИ ШАНСЫ ПОПАСТЬ В БАРТА. НО И ЕГО ШАНСЫ РАСТУТ.",
    "ПРОДОЛЖИТЬ? 1 ДА 0 НЕТ",
    "ВАШИ ВОЗМОЖНЫЕ ХОДЫ:",
    "* Х О Д Ы *",
    "===========",
    "1. ИДТИ ВПЕРЁД",
    "2. СТОЯТЬ НА МЕСТЕ",
    "3. СТРЕЛЯТЬ",
    "4. СПРЯТАТЬСЯ ЗА КОНСКОЙ ПОИЛКОЙ",
    "5. СДАТЬСЯ",
    "6. ПОВЕРНУТЬСЯ И БЕЖАТЬ",
    "ВАША СТРАТЕГИЯ?",
    "СКОЛЬКО ШАГОВ ПРОЙТИ:",
    "С ТАКИМ ЗНАНИЕМ ПРАВИЛ ДОЛГО НЕ ПРОЖИВЁТЕ.",
    "ТАК БЫСТРО НЕ ХОДЯТ.",
    "НАЗАД НЕЛЬЗЯ, ПАРТНЁР. НУЖНО ПОЛОЖИТЕЛЬНОЕ ЧИСЛО.",
    "ВЫ СТАЛИ ПРЕКРАСНОЙ НЕПОДВИЖНОЙ МИШЕНЬЮ.",
    "БРАВО! ПАТРОНЫ КОНЧИЛИСЬ.",
    "БАРТ НЕ СТРЕЛЯЕТ, ПОКА ВЫ НЕ СТОЛКНЁТЕСЬ НОС К НОСУ. СКОРЕЕ БЕГИТЕ!",
    "ПЛОХОЙ ВЫСТРЕЛ.",
    "ВЫ СБИЛИ БАРТА С ТОЛКУ.",
    "СКОЛЬКО, ПО-ВАШЕМУ, НА ЭТОЙ УЛИЦЕ КОНСКИХ ПОИЛОК?",
    "БАРТ СОГЛАСЕН. УСЛОВИЕ ТАКОВО:",
    "ОН НЕ СТРЕЛЯЕТ, ЕСЛИ ВЫ УЕДЕТЕ ПЕРВЫМ ДИЛИЖАНСОМ И БОЛЬШЕ НЕ ВЕРНЁТЕСЬ.",
    "СОГЛАСНЫ? 1 ДА 0 НЕТ",
    "ОЧЕНЬ МУДРОЕ РЕШЕНИЕ.",
    "НУ ЧТО Ж, ВЕРНЁМСЯ К ДУЭЛИ.",
    "КАК ДАЛЕКО ВЫ УБЕЖАЛИ?",
    "ОН УДРАЛ ТАК БЫСТРО, ЧТО ДАЖЕ СОБАКИ ЕГО НЕ ДОГНАЛИ.",
    "ЧЁРНЫЙ БАРТ ВЫСТРЕЛИЛ",
    "ОН ПОПАЛ ВАМ ПРЯМО В СПИНУ. ТАК ВАМ И НАДО ЗА БЕГСТВО.",
    "ЧЁРНЫЙ БАРТ РАЗРЯДИЛ РЕВОЛЬВЕР:",
    "ОДИН РАЗ В СПИНУ И ЕЩЁ",
    "В ЗАД. ТЕПЕРЬ И ПОКОЯ НЕ ВИДАТЬ.",
    "ВАМ ПОВЕЗЛО: У БАРТА НЕТ ПАТРОНОВ.",
    "ОН МОЖЕТ ТОЛЬКО БРОСИТЬ В ВАС РЕВОЛЬВЕР.",
    "ВООБЩЕ-ТО ВЫ УЖЕ ДОЛЖНЫ БЫТЬ МЕРТВЫ.",
    "ВОТ ЭТО ВЫСТРЕЛ! ВЫ ПОПАЛИ БАРТУ ПРЯМО МЕЖДУ ГЛАЗ.",
    "ПУЛЯ ЗАДЕЛА БАРТА ЗА ПРАВУЮ РУКУ.",
    "ВЫ РАНИЛИ ЕГО В ЛЕВОЕ ПЛЕЧО. ТЕПЕРЬ ОН СТРЕЛЯЕТ ПРАВОЙ РУКОЙ.",
    "БАРТ ПРОШЁЛ",
    "ВАШ ШАНС: У БАРТА КОНЧИЛИСЬ ПАТРОНЫ.",
    "БАРТ СТРЕЛЯЕТ . . . . . .",
    "МИМО . . . .",
    "ВАМ ПОВЕЗЛО. ПУЛЯ ПРОЛЕТЕЛА В САНТИМЕТРЕ ОТ ВАШЕЙ ГОЛОВЫ.",
    "БАРТ ПРОСТРЕЛИЛ ВАМ СЕРДЦЕ. ВЫ УМЕРЛИ, ТАК И НЕ СНЯВ САПОГ.",
    "БАРТ ПОПАЛ ВАМ В ПРАВУЮ ГОЛЕНЬ.",
    "ЭТА УЛОВКА СПАСЛА ВАМ ЖИЗНЬ.",
    "ПУЛЮ БАРТА ОСТАНОВИЛА ДЕРЕВЯННАЯ СТЕНКА ПОИЛКИ.",
    "НО БАРТ ПОПАЛ ВАМ В ЛЕВУЮ СТОРОНУ ЧЕЛЮСТИ.",
    "ДОЛЖНО БЫТЬ, БАРТ ДЁРНУЛ ЗА СПУСК.",
    "БАРТ УДРАЛ ИЗ ГОРОДА, ЛИШЬ БЫ НЕ ВСТРЕЧАТЬСЯ С ВАМИ С ПУСТЫМ РЕВОЛЬВЕРОМ.",
    "БУДЬТЕ УВЕРЕНЫ: ОН БОЛЬШЕ НИКОГДА НЕ ПОКАЖЕТСЯ В ЭТОМ ГОРОДЕ.",
    "КАК МЭР ДОДЖ-СИТИ ОТ ИМЕНИ ВСЕХ ГОРОЖАН БЛАГОДАРЮ ВАС И ВРУЧАЮ",
    "НАГРАДУ ЗА УБИЙСТВО ЧЁРНОГО БАРТА: ЧЕК НА 20 000 ДОЛЛАРОВ.",
    "ЧЕК НОМЕР",
    "АВГУСТА 1889",
    "КВИТАНЦИЯ КАССИРА - БАНК ДОДЖ-СИТИ",
    "ВЫПЛАТИТЬ ПРЕДЪЯВИТЕЛЮ",
    "ДВАДЦАТЬ ТЫСЯЧ ДОЛЛАРОВ",
    "$20,000",
    "НЕ ТРАТЬТЕ ВСЁ СРАЗУ.",
    "КРИС ГАЙЛО, 1970",
)
payloads = [quoted_payload(path) for path in parts]
for phrase in required_text:
    needle = compact(phrase)
    require(any(needle in payload for payload in payloads),
            f"High Noon lost upstream text: {phrase}")

all_game_text = "\n".join(path.read_text(encoding="utf-8") for path in parts)
all_literals = "".join(
    literal
    for path in parts
    for literal in re.findall(r'"([^"]*)"', path.read_text(encoding="utf-8"))
)
require(not re.search(r"[A-Za-z]", all_literals),
        "High Noon runtime text must not require Latin glyphs")
supported_codepoints = (
    set(range(0x20, 0x40)) | {0x0401} | set(range(0x0410, 0x0430))
)
unsupported = sorted({ord(char) for char in all_literals}
                     - supported_codepoints)
require(not unsupported,
        "High Noon text is missing FMK glyph "
        + (f"U+{unsupported[0]:04X}" if unsupported else ""))

intro = (game / "intro.tbi").read_text(encoding="utf-8")
require("130 IF D=0 G.600" in intro,
        "High Noon answer 0 must skip every instruction page")
require("590 PAU." in intro and "610 .RE=1:E." in intro,
        "High Noon instruction pause must not delay the 0 branch")

reward = (game / "reward.tbi").read_text(encoding="utf-8")
require(reward.count("GOSUB 8000") == 2,
        "High Noon receipt must draw both borders through one width-aware routine")
require("8000 FOR I=1 TO COLS" in reward and '8010 P."*";' in reward,
        "High Noon receipt border must follow the active font viewport width")
require(not re.search(r'"\*{2,}"', reward),
        "High Noon receipt restored a hard-coded split border")
require("265 FOR I=1 TO COLS-34" in reward,
        "High Noon receipt amount line must fill the active viewport")
amount = "ДВАДЦАТЬ ТЫСЯЧ ДОЛЛАРОВ" + "-" * (47 - 34) + "$20,000"
amount_width = sum(font_advances[ord(char)] for char in amount)
require(amount_width <= 188,
        "High Noon receipt amount must fit the 188-pixel text viewport")
for stale in ("WALKM", "BETER", "RECEIT", "DODsGE", "THATS", "YOUT", "BURT"):
    require(stale not in all_game_text, f"High Noon restored misspelling: {stale}")
for path in parts:
    for line_number, source_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        for literal in re.findall(r'"([^"]*)"', source_line):
            require(len(literal) <= 47,
                    f"{path.name}:{line_number} exceeds the 47-cell High Noon viewport")

player = (game / "player.tbi").read_text(encoding="utf-8")
bart = (game / "bart.tbi").read_text(encoding="utf-8")
for fragment in (
    "G.1000+B*100",
    ".R0=X:.R2=C:.R3=P:.R4=T",
    "W>SGN(X)*INT(ABS(X)/10)",
    "IF P>4 N=3",
):
    require(fragment in player, f"High Noon player logic lost: {fragment}")
for fragment in (
    "X=.R0:B=.R1:C=.R2:P=.R3",
    "A=.RE:X=.R0:B=.R1:C=.R2:P=.R3",
    "IF A=3 G.1050",
    "R>SGN(X)*INT(ABS(X)/10)",
    ".R0=X:.R2=C:.R3=P",
):
    require(fragment in bart, f"High Noon Bart logic lost: {fragment}")

# These paths exist in the 1970 listing but cannot affect a game. Keep them in
# the archival FORTRAN port, not in the size-constrained executable port.
for dead in (
    'THAT WAS YOUR LAST SHOT, YOU MISSED',
    '1800 IF P=2 G.1940',
    '1810 IF P=3 G.1960',
    '1870 P."THAT WAS YOUR LAST SHOT, YOU MISSED"',
    '1880 N=2:G.7000',
):
    require(dead not in all_game_text, f"High Noon restored dead path: {dead}")
require("IF P>4 G.1070" not in bart,
        "High Noon restored the impossible P>4 branch inside P<=4 firing")
require(player.count("IF T>3") == 1,
        "High Noon must contain only one T>3 watering-trough check")
require("IF X<0 X=0" in player, "High Noon player distance can become negative")
require("IF Z>X Z=X" in bart, "High Noon Bart distance can become negative")

print("high_noon_package_self_test: ok")
