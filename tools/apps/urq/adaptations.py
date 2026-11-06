"""Reviewed source adaptations of pinned licensed games; no JS interpreter.

Only the exact revisions in adaptations.json are accepted. Generated URQL is
also playable in UrqW, so both the port and the original game can be compared.
"""
import hashlib
import html
import json
from pathlib import Path
import re
import unicodedata

LOCK = json.loads(Path(__file__).with_name("adaptations.json").read_text())


def replace_once(text, before, after):
    if text.count(before) != 1:
        raise ValueError("Adaptation no longer matches the pinned source: " + before[:70])
    return text.replace(before, after, 1)


def house(texts):
    main = texts["_main.qst"]
    start = main.index(":main\n")
    finish = main.index(":buttons\n")
    choices = [
        "Самуил Маршак (1923)", "Самуил Маршак (1936)", "Геннадий Аминов",
        "Игорь Родин", "Светлана Сергеева", "Екатерина Зеленина",
    ]
    menu = ':main\npln Дом, который построил Джек\npln Выберите русский перевод:\n'
    menu += "\n".join(f"btn ru_v{i}_0, {caption}" for i, caption in enumerate(choices))
    main = main[:start] + menu + "\nend\n\n" + main[finish:]
    main = replace_once(main, '#insert_var$="#insert_val$"', '#insert_var$=insert_val')
    versions = []
    for index in range(6):
        text = texts[f"ru_v{index}.qst"]
        # URQL '=' compares Russian strings without case, including Ё/ё.
        # Keep the actual answer as data; never construct executable source.
        pattern = r'javascript="\x27" \+ ([^\n]+?) \+ "\x27\.toLowerCase\(\);"\n([^\n]+)'
        def answer(match):
            return match[2].replace("javascript", match[1])
        text, changes = re.subn(pattern, answer, text)
        words = int(re.search(r"(?m)^words=(\d+)$", text)[1])
        if changes != words:
            raise ValueError("House adaptation: answer count differs from words")
        # All inputs to percentageRatio are integers in 1..words. This exact
        # table implements Math.round(100*correct/words) over that domain.
        table = "\n".join(f"if correct = {n} then percentage = {(200*n+words)//(2*words)}"
                          for n in range(1, words))
        text = replace_once(text,
            'if correct > 0 then javascript="window.percentageRatio(" + correct + ", " + words + ");"', table)
        text = text.replace("#javascript$", "#percentage$")
        if index == 5:
            text = replace_once(text, 'insert_var=кот""', 'insert_var="кот"')
        text = re.sub(r'(?m)^image(?:_caption)?=.*\n', '', text)
        text = text.replace("pln Иллюстрация: Рэндольф Кальдекотт \n", "")
        versions.append(text)
    manifest = {
        "manifest_version": 1, "urq_mode": "urqw", "game_encoding": "UTF-8",
        "urqw_title": "Дом, который построил Джек", "urqw_game_lang": "ru",
        "urqw_game_ifid": "13E7A453-31A8-4EC9-8AAB-C8E98F2C8CBD",
    }
    return "\n".join([main, *versions]), manifest


def trapped(texts):
    text = texts["game.qst"]
    text = replace_once(text,
        'javascript = "JSON.stringify(shuffleArray([\x2711\x27, \x2748\x27, \x2752\x27, \x2762\x27, \x2770\x27]).concat(\x271\x27));"\n'
        'adventure_list = javascript\nadventure_queue = javascript',
        'adventure_list = "11,48,52,62,70"\ntokens adventure_list\n'
        'shuffle_i = 5\nproc mk_shuffle\n'
        'adventure_list = token1 + "," + token2 + "," + token3 + "," + token4 + "," + token5 + ",1"\n'
        'tokens adventure_list\nqueue_position = 1')
    start = text.index(":travel\n")
    finish = text.index(":about\n", start)
    text = text[:start] + '''\
:travel
if queue_position <= 6 then goto travel_next else goto travel_restart
end

:travel_next
adventure = token#queue_position$
queue_position += 1
goto #adventure$
end

:travel_restart
tokens adventure_list
shuffle_i = 6
proc mk_shuffle
if token1 <> adventure then goto mk_queue_ready
shuffle_i = 1
:mk_rotate
token#shuffle_i$ = token#(shuffle_i + 1)$
shuffle_i += 1
if shuffle_i < 6 then goto mk_rotate
token6 = adventure
:mk_queue_ready
queue_position = 1
goto travel_next
end

:mk_shuffle
if shuffle_i < 2 then end
shuffle_j = rnd#shuffle_i$
shuffle_tmp = token#shuffle_i$
token#shuffle_i$ = token#shuffle_j$
token#shuffle_j$ = shuffle_tmp
shuffle_i -= 1
goto mk_shuffle
end

''' + text[finish:]
    # A Danish title in the historical note; gameplay and Russian text are intact.
    text = text.replace("Nær og Fjern", "Naer og Fjern")
    manifest = {
        "manifest_version": 1, "urq_mode": "urqw", "game_encoding": "UTF-8",
        "urqw_title": "В ловушке времени", "urqw_game_lang": "ru",
        "urqw_game_ifid": "5CED8A6C-E644-419A-9A26-EFFF3B610BE9",
    }
    return text, manifest


def jim(texts):
    """Keep all story branches; static optional URQL notes replace JSON/DOM."""
    text = texts["main.qst"]
    first,last=text.index(":start\n"),text.index(":init\n")
    about=text[first:last].replace(":start\n",":mk_about\n",1)
    at=about.rfind("\nend")
    about=about[:at]+"\nbtn start, Назад"+about[at:]
    intro=(":start\nvarkill\npln Джим из Космоса\n"
           "pln Космический полицейский Джим получает задание перед концом смены.\n"
           "btn init, Начать игру\nbtn mk_about, Об игре и авторах\nend\n\n")
    text=text[:first]+intro+about+text[last:]
    start, end = text.index(":notes_section\n"), text.index(":1\n")
    text = text[:start] + text[end:]
    notes = []

    def note(match):
        # URQL source escapes the JSON backslashes once for its string value.
        raw = "".join(line.removeprefix("_") for line in match[1].splitlines())
        values = json.loads(raw.replace("\\\\", "\\"))
        index = len(notes) + 1
        notes.append(f":mk_note_{index}\npln Примечания переводчика\n" +
                     "\n".join("pln " + value for value in values) + "\nend\n")
        return f"btn proc mk_note_{index}, Примечания переводчика\n"

    text, count = re.subn(r"(?m)^notes_text = '(\[[\s\S]*?\n_\])'\n(?:proc notes_section\n)?", note, text)
    if count != 33:
        raise ValueError(f"Jim: unexpected note section count {count}")
    # Keep plot choices first, optional notes last. A procedure command keeps
    # the original buttons, current_loc, previous_loc and return links intact.
    blocks = re.split(r"(?m)(?=^:)", text)
    for i, block in enumerate(blocks):
        match = re.search(r"(?m)^btn proc mk_note_\d+[^\n]*\n", block)
        if match:
            button = match[0]
            block = block[:match.start()] + block[match.end():]
            at = block.rfind("\nend")
            if at < 0:
                raise ValueError("Jim: note outside a location")
            blocks[i] = block[:at] + "\n" + button.rstrip() + block[at:]
    text = "".join(blocks) + "\n" + "\n".join(notes)
    # Browser-only media never conveys an otherwise missing plot clue.
    text = re.sub(r"(?m)^(?:image(?:_caption)?\s.*|music\s.*|play\s.*)\n", "", text)
    text = re.sub(r"<[^>]*>", "", text)
    text = html.unescape(text)
    replacements = {"猛龍過江": "Meng long guo jiang", "アニメ80日間世界一周": "Anime 80 nichikan sekai isshu",
                    "⏪": "←", "😉": ";)", "™": "(TM)", "⁴": "[4]", "¹": "[1]", "²": "[2]", "³": "[3]",
                    "ŋ": "ng", "¡": "", "\u0301": "", "\u202f": " ", "\u00a0": " "}
    for before, after in replacements.items():
        text = text.replace(before, after)
    # Only Latin accents are transliterated; Russian Ё and Й stay intact.
    text = "".join("".join(c for c in unicodedata.normalize("NFD", ch) if not unicodedata.combining(c))
                   if "LATIN" in unicodedata.name(ch, "") else ch for ch in text)
    # Split long narrative paragraphs without changing their printed content.
    lines = []
    for line in text.splitlines():
        if line.startswith("pln ") and len(line) > 480:
            value = line[4:]
            while len(value) > 480:
                at = value.rfind(" ", 0, 480)
                if at < 1:
                    raise ValueError("Jim: unbreakable narrative word")
                lines.append("p " + value[:at + 1])
                value = value[at + 1:]
            lines.append("pln " + value)
        else:
            lines.append(line)
    manifest = {"manifest_version": 1, "urq_mode": "urqw", "game_encoding": "UTF-8",
                "mk61_zx0_parser": "optimal",
                "urqw_title": "Джим из Космоса", "urqw_game_lang": "ru",
                "urqw_game_ifid": "C2AF99B7-84E9-4C89-9CA1-F60FE853A7D7"}
    return "\n".join(lines) + "\n", manifest


def adapt(key, folder):
    if key not in LOCK:
        return None
    entry = LOCK[key]
    texts = {}
    for name, expected in entry["files"].items():
        data = (folder / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("Unreviewed adaptation source: " + key + "/" + name)
        if name.endswith(".qst"):
            texts[Path(name).name] = data.decode("utf-8-sig")
    text, manifest = {"house_that_jack_built": house, "trapped_in_time_ru": trapped,
                      "jim_from_outer_space_ru": jim}[key](texts)
    return text, manifest, {"version": 1, "repository": entry["repository"],
        "revision": entry["revision"], "files": entry["files"], "changes": entry["changes"],
        "verification": "tests/urq_library_self_test.py"}
