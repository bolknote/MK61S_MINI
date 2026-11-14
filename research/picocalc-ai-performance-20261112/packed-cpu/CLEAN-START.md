# Clean-start inference admission

The firmware is unchanged: **1BDB4385 / 161FEF7E**. No rebuild or device
operation was performed for this controller update.

Use `run_inference_clean.py` and
`.build/mk61ai/packed-cpu-20261112/INFERENCE-CLEAN-PACKAGE.json`, SHA256
`9656d7fbc59b14821ab19f79d080bd7d15cda5f7f97862209ff8b092a0a74ed8`.
The previous f276 package and all its pinned files remain unchanged solely as
build provenance. Its old state-restoring controller is not the active plan.

Admission requires a fresh coordinator handoff after the combined installation
and **four successful Spectrum short tests**:

- BOOTS24, CRASH=NONE, and `firmware_admission_clean=true`;
- `spectrum_short_passes=4`, matching package SHA and an unexpired device window;
- the exact installed combined build/CRC and an idle, released device.

Spectrum owns the one ordinary crash-clear operation before DFU. The AI
controller neither reads old crash payloads nor issues crash commands.
It does not back up or restore old device/PERF state, firmware or user files.
The three private experiment files are overwritten without reading their old
contents and removed after retrieving the fresh measurement. MODEL.MKA remains
unchanged. Existing source packages are retained until the full test cycle
finishes, as requested by the coordinator.

The fresh handoff template is
`.build/mk61ai/packed-cpu-20261112/INFERENCE-CLEAN-HANDOFF-TEMPLATE.json`.
It deliberately has no authorization, no deadline and no successful admission;
it cannot start a test. The coordinator must issue a new actual handoff.

Host qualification passed: all846 pins validated; eight invalid grants
(retained crash, old boot, three shorts, unclean admission, template, missing
handoff, expiry and wrong package) were rejected before opening a device.
Evidence: `.build/mk61ai/packed-cpu-20261112/CLEAN-ADMISSION-HOST.json`.

On 13 November 2026 Spectrum stopped its short tests on an NRZ error. The
coordinator gave the installed firmware a separate two-core window. The
measurement ran through `run_inference_dual_core.py`, which checked the
installed image, the released device status, and the live PSRAM and I²C
counters. See [the measured results](README.md#picocalc-measurement-on-13-november-2026).
