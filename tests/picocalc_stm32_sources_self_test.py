#!/usr/bin/env python3
"""Run production CMake source selection; keep Pico AI out of STM32 resident."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
cmake = (ROOT / "tools/firmware/stm32/CMakeLists.txt").read_text()
start = cmake.index("file(GLOB _mk61_project_sources")
selection = cmake[start:cmake.index("configure_file(", start)]
with tempfile.TemporaryDirectory(prefix="mk61-stm32-sources-") as directory:
    work = Path(directory)
    (work / "CMakeLists.txt").write_text(
        'cmake_minimum_required(VERSION 3.21)\nproject(source_selection NONE)\n'
        f'set(MK61_PROJECT_ROOT "{ROOT.as_posix()}")\n' + selection +
        '\nfile(WRITE "${CMAKE_BINARY_DIR}/sources.txt" "${_mk61_project_sources}")\n')
    subprocess.run(["cmake", "-S", str(work), "-B", str(work / "build")],
                   check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    selected = {Path(p) for p in (work / "build/sources.txt").read_text().split(";")}
    all_sources = set((ROOT / "code").glob("*.c")) | set((ROOT / "code").glob("*.cpp"))
    pico_ai = {p for p in all_sources if p.name.startswith("mk61_ai_")}
    assert pico_ai and not selected.intersection(pico_ai), "Pico AI entered STM32 source/stack analysis"
    expected = all_sources - pico_ai - {ROOT / "code/ERM19264_graphics.cpp"}
    assert selected == expected, f"Unrelated STM32 sources removed: {expected - selected}"
    assert ROOT / "code/mk61emu_core.cpp" in selected
    assert ROOT / "code/language_vm.cpp" in selected
    print(f"STM32 production CMake: kept {len(selected)} resident units, excluded {len(pico_ai)} Pico AI units PASS")
