# Preserved experiment sources

These scripts and candidate sources belong to chat
`01a17a32-c316-7880-86b9-969da392543c`. They were preserved byte for byte from
its `strlen-m4-m0-research` worktree on 2026-10-31. `SOURCE-PINS.json` records
their original hashes. The experiment source base was
`92be3a44c784238ebf76429c9e9230059dbdc910`; the integration checkpoint is based
on main `ed2ac8e892ff1c018345eb5781e00331b33f1f8e`.

The completed M4 selection used 424 physical APP runs and retained 370,944 raw
durations. Its evidence and limitations are in the existing `RESULTS-M4.json`:
`M4_HARDWARE_SELECTION_HOST_INTEGRATION_VERIFIED_FINAL_HIL_AND_M0_PENDING`.
The integrated native/runtime/standalone hardware check and the M0 matrix
remain pending. Short-string regressions and the original producer HOLD
remain recorded. This checkpoint adds no physical result or production
default, changes no status to a full hardware PASS, and grants no device I/O.

Main already contains the M4 production integration as `e2ac532a6`, including
the F401 graphics DSP8 budget handling. The protected historical `6e814dd7b`
head is preserved. Its separate ancestry does not mean its DSP32 selection
must be applied to main again. The current README and RESULTS-M4 are kept;
the older untracked README, which preceded the M4 measurements, is not used
as a replacement for them.

The tools describe the historical experiment and remain passive unless a
qualified parent supplies their finite workload. `adapter.py` opens no port,
creates no lease and performs no firmware or cleanup operation. A new
physical run requires the coordinator's fresh exact binding, qualified
timer/state/RTC and return suppliers, accepted argv and lease. The historical
`.build` packets and raw hardware evidence remain in place. No former grant
or snapshot is reactivated by committing these sources.
