#!/usr/bin/env python3
"""Extract the single Explorer UI and the independent file-choice dialog."""

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
    app = root / "code/explorer_ui.cpp"
    editor = root / "code/text_editor.hpp"
    editor_source = editor.read_text()
    # Keep real SMS/search editing primitives; omit only display/editor UI.
    editor_start = editor_source.index("namespace text_editor {")
    editor_end = editor_source.index("inline u8 visible_rows(")
    (out / "explorer_editor.inc").write_text(
        editor_source[editor_start:editor_end] +
        functions(editor, ["inline bool replace_range(char* source, u16& len, u16& cursor, u16 capacity, u16 start,",
                          "inline bool insert_text(", "inline bool backspace(",
                          "inline bool sms_tap("]) + "}\n")
    (out / "explorer_extensions.inc").write_text(
        "namespace program_store {\n" +
        body(root / "code/program_store.cpp", "static const char* extension_for_type(") +
        "const char* file_extension(ProgramType type) { return extension_for_type(type); }\n}\n" +
        "namespace app_store { using program_store::ProgramType;\n" +
        body(root / "sdk/portable/system/system_compat.cpp", "const char* file_extension(") + "}\n")
    (out / "resident_explorer_ui.inc").write_text(
        declarations(resident, ["static constexpr u16 FILE_DIALOG_SCROLL_START_MS",
            "static constexpr u16 FILE_DIALOG_SCROLL_STEP_MS",
            "static constexpr u16 FILE_DIALOG_SCROLL_EDGE_MS",
            "static constexpr u8 FILE_DIALOG_NAME_COL"]) +
        body(resident, "struct FileDialogScroll", True) +
        body(resident, "enum class DialogItemKind", True) +
        body(resident, "struct DialogItem", True) +
        functions(resident, ["static u8 file_dialog_name_width(",
            "static u8 file_dialog_name_len(",
            "static u8 file_dialog_scroll_max_offset(", "static void file_dialog_name_window(",
            "static void draw_file_dialog_name(", "static void dialog_item_name(",
            "static void draw_dialog_row("]))
    (out / "app_explorer_ui.inc").write_text(
        "using loadable_module::ExplorerAction;\nusing loadable_module::ExplorerSession;\n" +
        declarations(app, ["static constexpr u32 LONG_OK_MS",
            "static constexpr i32 KEY_UP", "static constexpr i32 KEY_DOWN",
            "static constexpr i32 KEY_OK_SHORT", "static constexpr i32 KEY_OK_LONG",
            "static constexpr i32 KEY_ESCAPE", "static constexpr i32 KEY_TICK",
            "static constexpr i32 KEY_REDRAW", "static constexpr u16 SCROLL_START_MS",
            "static constexpr u16 SCROLL_STEP_MS", "static constexpr u16 SCROLL_EDGE_MS",
            "static constexpr u8 MAX_LINES", "static constexpr usize LINE_BYTES"]) +
        body(app, "struct Search", True) + body(app, "struct Scroll", True) +
        body(app, "struct Line", True) +
        functions(app, ["static bool reached(", "static usize bounded_length(",
            "static void copy_text(", "static bool entry_at(", "static void cursor_off(",
            "static i32 wait_key(", "static bool wait_ok_release(", "static void wait_handoff(",
            "static void clear_lines(", "static void render(", "static bool search_active(",
            "static char ascii_upper(", "static bool contains_ci(", "static bool matches(",
            "static int match_count(", "static int match_at(", "static int match_position(",
            "static int first_match(", "static int next_match(", "static int previous_match(",
            "static void reset_scroll(", "static u16 name_width(", "static u8 max_offset(",
            "static void update_scroll(", "static u16 scroll_timeout(",
            "static void search_reset(", "static bool search_insert(",
            "static bool handle_search_key(", "static u16 search_window_start(",
            "static void draw_search_cursor(", "static u16 draw_browser(",
            "static int make_actions(", "static const char* action_text(",
            "static void draw_action_menu(", "static ExplorerAction choose_action(",
            "static bool autoexec(", "static void set_result(", "bool select(",
            "uint32_t flow_step("]))

    resident_source = resident.read_text()
    assert "draw_explorer(" not in resident_source
    assert "draw_explorer_row(" not in resident_source
    assert "explorer_search_handle_key(" not in resident_source
    assert "static bool wait_ok_release(" not in resident_source
    assert "loadable_module::run_flow(" in resident_source
    assert "app_flow::run(" in resident_source
    assert "explorer_ui::flow_step(" in (root / "code/explorer_module_entry.cpp").read_text()


if __name__ == "__main__":
    main()
