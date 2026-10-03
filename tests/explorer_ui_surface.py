#!/usr/bin/env python3
"""Extract the real resident/APP label and scrolling paths for host tests."""

from pathlib import Path
import sys

from ui_contract_surface import body


def declarations(path, prefixes):
    source = path.read_text()
    return "".join(source[source.index(prefix):source.index(";", source.index(prefix)) + 1] + "\n"
                   for prefix in prefixes)


def functions(path, names):
    return "".join(body(path, name) for name in names)


def main():
    root = Path(__file__).resolve().parents[1]
    out = Path(sys.argv[1])
    resident = root / "code/development.cpp"
    app = root / "code/explorer_module_ui.cpp"
    editor = root / "code/text_editor.hpp"
    (out / "explorer_editor.inc").write_text(
        "namespace text_editor {\n" + body(editor, "enum class Shift", True) +
        body(editor, "struct SmsState", True) +
        body(editor, "inline usize bounded_length(") + "}\n")
    (out / "explorer_extensions.inc").write_text(
        "namespace program_store {\n" +
        body(root / "code/program_store.cpp", "static const char* extension_for_type(") +
        "const char* file_extension(ProgramType type) { return extension_for_type(type); }\n}\n" +
        "namespace app_store { using program_store::ProgramType;\n" +
        body(root / "sdk/portable/system/system_compat.cpp", "const char* file_extension(") + "}\n")
    (out / "resident_explorer_ui.inc").write_text(
        declarations(resident, ["static constexpr u16 EXPLORER_SCROLL_START_MS",
            "static constexpr u16 EXPLORER_SCROLL_STEP_MS",
            "static constexpr u16 EXPLORER_SCROLL_EDGE_MS",
            "static constexpr u8 EXPLORER_NAME_COL"]) +
        body(resident, "struct ExplorerScroll", True) +
        body(resident, "enum class DialogItemKind", True) +
        body(resident, "struct DialogItem", True) +
        functions(resident, ["static bool explorer_time_reached(",
            "static void explorer_cursor_off(", "static void print_line(",
            "static void print_localized_line(", "static int explorer_count(",
            "static bool explorer_entry(", "static char ascii_upper(",
            "static bool search_active(", "static bool text_contains_case_insensitive(",
            "static bool entry_matches_search(", "static int matching_entry_count(",
            "static int matching_index_at(", "static int matching_position(",
            "static void explorer_scroll_reset(", "static u8 explorer_name_width(",
            "static u8 explorer_name_len(", "static bool explorer_name_overflows(",
            "static u8 explorer_scroll_max_offset(", "static void explorer_scroll_track(",
            "static u16 explorer_scroll_timeout(", "static void explorer_name_window(",
            "static void draw_explorer_name(", "static void draw_explorer_row(",
            "[[maybe_unused]] static u16 draw_explorer(", "static void dialog_item_name(",
            "static void draw_dialog_row("]))
    (out / "app_explorer_ui.inc").write_text(
        declarations(app, ["static constexpr u16 SCROLL_START_MS",
            "static constexpr u16 SCROLL_STEP_MS", "static constexpr u16 SCROLL_EDGE_MS",
            "static constexpr u8 MAX_LINES", "static constexpr usize LINE_BYTES"]) +
        body(app, "struct Search", True) + body(app, "struct Scroll", True) +
        body(app, "struct Line", True) +
        functions(app, ["static bool reached(", "static usize bounded_length(",
            "static void copy_text(", "static bool entry_at(", "static void cursor_off(",
            "static void clear_lines(", "static void render(", "static bool search_active(",
            "static char ascii_upper(", "static bool contains_ci(", "static bool matches(",
            "static int match_count(", "static int match_at(", "static int match_position(",
            "static void reset_scroll(", "static u16 name_width(", "static u8 max_offset(",
            "static void update_scroll(", "static u16 scroll_timeout(",
            "static u16 draw_browser("]))


if __name__ == "__main__":
    main()
