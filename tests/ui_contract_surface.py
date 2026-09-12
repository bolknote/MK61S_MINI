#!/usr/bin/env python3
"""Compile selected production UI bodies against a recording host surface.

No renderer or copy of menu algorithms lives in tests. Selection fails closed
on a removed/renamed function; #line diagnostics point to the production file.
The generated .inc files live only in the test temp directory.
"""
import re
import sys
from pathlib import Path

TOKENS = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*[\s\S]*?\*/|[{}]')


def body(path: Path, marker: str, semicolon: bool = False) -> str:
    source = path.read_text()
    start = source.index(marker)
    opening = source.index("{", start)
    depth = 0
    for match in TOKENS.finditer(source, opening):
        if match[0] == "{":
            depth += 1
        elif match[0] == "}":
            depth -= 1
            if depth == 0:
                end = match.end() + int(semicolon)
                line = source[:start].count("\n") + 1
                return f'#line {line} "{path}"\n' + source[start:end] + "\n"
    raise ValueError(f"unterminated production body: {path}: {marker}")


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "code"
    out = Path(sys.argv[1])
    (out / "ui_geometry.inc").write_text(
        body(root / "display.hpp", "namespace lcd_display {") +
        body(root / "display_profile.hpp", "namespace lcd_display {") +
        body(root / "display.hpp", "namespace lcd_display {\n\n#if defined(MK61_DISPLAY_LCD1602)"))
    menu = root / "setup_ui.cpp"
    pieces = ["namespace library_mk61 {\n"]
    for marker in ["static bool sameTextProfile(", "static const char* fontPresetName(", "static lcd_display::TextProfile nextFontPreset("]:
        pieces.append(body(menu, marker))
    pieces += ["}\nusing library_mk61::sameTextProfile;\nusing library_mk61::fontPresetName;\n", body(menu, "enum class FontSetupPhase", True)]
    pieces.append("u32 service(u32 op, u32 a = 0, u32 b = 0, void* p = nullptr);\n")
    pieces.append(body(root / "setup_service.cpp", "static u32 apply_font_profile("))
    pieces.append("""u32 service(u32 op, u32 a, u32 b, void* p) {
      if(op == MK61_SETUP_FONT_APPLY) return apply_font_profile(p);
      if(op == MK61_SETUP_FEATURES) return MK61_SETUP_FEATURE_TEXT_PROFILE |
          (MK61_ENABLE_EXTENDED_FONT_SETTINGS ? MK61_SETUP_FEATURE_EXTENDED_TEXT_PROFILE : 0) |
          (ui_fonts_available ? MK61_SETUP_FEATURE_UI_FONT : 0) |
          (ui_text_mode_available ? MK61_SETUP_FEATURE_UI_TEXT_MODE : 0) |
          (ui_font_catalog_available ? MK61_SETUP_FEATURE_UI_FONT_CATALOG : 0);
      if(op == MK61_SETUP_UI_FONT_READ) {
        if(!p || !ui_fonts_available) return 0;
        *(mk61_setup_ui_font*) p = surface.ui_font;
        return 1;
      }
      if(op == MK61_SETUP_UI_FONT_APPLY) {
        if(!p || !ui_fonts_available) return 0;
        const mk61_setup_ui_font next = *(const mk61_setup_ui_font*) p;
        if(next.family > 3 || (next.size != 12 && next.size != 14 && next.size != 16)) return 0;
        surface.ui_font = next;
        selected_ui_font_key = 0;
        return 1;
      }
      if(op == MK61_SETUP_UI_FONT_COUNT)
        return ui_font_catalog_available ? (u32) ui_font_catalog.size() : 0;
      if(op == MK61_SETUP_UI_FONT_ITEM) {
        if(!p || !ui_font_catalog_available || a >= ui_font_catalog.size()) return 0;
        *(mk61_setup_ui_font_item*) p = ui_font_catalog[a];
        return 1;
      }
      if(op == MK61_SETUP_UI_FONT_CURRENT) {
        if(!p || !ui_font_catalog_available || surface.ui_font.family != 3) return 0;
        for(const auto& item : ui_font_catalog) {
          if(item.key == selected_ui_font_key) {
            *(mk61_setup_ui_font_item*) p = item;
            return 1;
          }
        }
        return 0;
      }
      if(op == MK61_SETUP_UI_FONT_APPLY_ITEM) {
        if(!ui_font_catalog_available) return 0;
        for(const auto& item : ui_font_catalog) {
          if(item.key == a) {
            surface.ui_font = {3, item.size};
            selected_ui_font_key = item.key;
            return 1;
          }
        }
        return 0;
      }
      if(op == MK61_SETUP_UI_FONT_STEP) {
        if(!p || !ui_font_catalog_available ||
           (b != 1U && b != 0xFFFFFFFFUL) || ui_font_catalog.empty()) return 0;
        isize index = b == 1U ? 0 : (isize) ui_font_catalog.size() - 1;
        if(a != 0) {
          index = -1;
          for(usize current = 0; current < ui_font_catalog.size(); ++current) {
            if(ui_font_catalog[current].key == a) {
              index = (isize) current + (b == 1U ? 1 : -1);
              break;
            }
          }
        }
        if(index < 0 || (usize) index >= ui_font_catalog.size()) return 0;
        *(mk61_setup_ui_font_item*) p = ui_font_catalog[(usize) index];
        return 1;
      }
      if(op == MK61_SETUP_TEXT_MODE) {
        if(!ui_text_mode_available || a > 1) return 0;
        surface.ui_text_context = a != 0;
        calls.emplace_back(a ? "text-mode-ui" : "text-mode-mono");
        return 1;
      }
      if(op == MK61_SETUP_TEXT) {
        if(!p || a >= surface.rows()) return 0;
        surface.recordLine((u8) a, (b & 0x100U) ? (char) b : 0, (const char*) p);
        calls.emplace_back("text");
        return 1;
      }
      if(op == MK61_SETUP_PHASE) { crash_dump::update_runtime(crash_dump::RUNTIME_MENU, 0x464E0000UL | a, millis()); return 1; }
      assert(false); return 0;
    }""")
    pieces.append(body(menu, "struct UiFontChoice", True))
    for marker in ["static void noteFontSetupPhase(", "static u8 calculatorFontFieldCount(", "static bool uiFontSettingsAvailable(", "static bool uiFontCatalogAvailable(", "static mk61_setup_ui_font readUiFont(", "static UiFontChoice readUiFontChoice(", "static void formatUiFontLine(", "static void formatFontSetupLine(", "static void printFontSetupLine(", "static void drawCalculatorFontSetup(", "static u8 uiFontFieldCount(", "static u8 stepLegacyUiFontFamily(", "static u8 stepUiFontSize(", "static bool uiFontCatalogStep(", "static bool applyBuiltinUiFont(", "static bool applyCatalogUiFont(", "static bool stepUiFontChoice(", "static void drawUiFontSetup(", "static void applyFontSetupProfile("]:
        pieces.append(body(menu, marker))
    pieces.append(body(root / "development.cpp", "static u16 ui_editor_window_start("))
    settings_source = (root / "menu.cpp").read_text()
    settings_start = settings_source.index("static constexpr int SETTINGS_VOLUME")
    settings_end = settings_source.index("static u8 sound_volume_state", settings_start)
    pieces.append("namespace library_mk61 {\n" +
                  settings_source[settings_start:settings_end] + "}\n")
    (out / "ui_menu.inc").write_text("\n".join(pieces))
    (out / "ui_settings_adjustment.inc").write_text(
        body(root / "menu.cpp", "bool class_menu::handle_settings_adjustment("))



if __name__ == "__main__":
    main()
