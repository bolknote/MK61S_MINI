"""Exercise production input consumers on mini, Classic and 40TH layouts."""
import os
from pathlib import Path
import subprocess
import tempfile

from ui_contract_surface import body

ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT / "code"


def main():
    with tempfile.TemporaryDirectory(prefix="mk61-controls-") as temporary:
        work = Path(temporary)
        (work / "m61_keyboard_surface.inc").write_text(
            body(CODE / "keyboard.cpp", "void handoff(Event cause) {") +
            body(CODE / "keyboard.cpp", "isize scan_m61_controls(void) {"))
        (work / "m61_controls_surface.inc").write_text(
            body(CODE / "mk61s-M.ino", "static void service_m61_controls(void) {"))
        (work / "m61_viewer_surface.inc").write_text(
            body(CODE / "markdown_viewer.cpp", "static i32 scan_key(void) {"))
        flags = (["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
                 if os.environ.get("MK61_TEST_SANITIZERS") == "1" else [])
        for layout in ("MINI", "CLASSIC", "40TH"):
            exe = work / layout
            subprocess.run([
                "clang++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                *flags, f"-DMK61_KEYBOARD_{layout}",
                f"-I{CODE}", f"-I{work}",
                str(ROOT / "tests/m61_controls_self_test.cpp"), "-o", str(exe),
            ], check=True)
            subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()
