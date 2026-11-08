#!/usr/bin/env python3
"""Build a finite CHIP8 FPS diagnostic using the production System adapter.

Pass the ordinary portable builder's --output-dir/--arm-toolchain-bin/--packer.
The diagnostic is not a release System module or a replacement CHIP8 handler.
"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.apps.portable import build_portable_app as builder
builder.SYSTEM_MODULES["app"]=("C8FPS","APPLICATION",
    ["chip8.cpp","../tests/chip8_fps_bench_app.cpp"],None)
sys.argv[1:]=["--system","app",*sys.argv[1:]]
builder.main()
