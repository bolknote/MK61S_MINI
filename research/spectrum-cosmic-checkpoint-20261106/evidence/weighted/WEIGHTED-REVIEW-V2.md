# Exact weighted AY, HOST qualified, hardware speed unproved

The current candidate keeps the ordinary APP, Z80, MMU/peripherals, sample rate
25kHz, chip clock1.75MHz, quality1, both AY chips and sound event protocol.
No new allocation, firmware/ABI, PSRAM or clock change. The native observer is
the same v2 capture-before-DONE code as cosmic-display's matched pair.

For N successive internal ticks, the existing signed filter recurrence is
out[i+1]=floor((out[i]+mix[i])/2). Therefore
out[N]=floor((out[0]+sum(mix[i]*2^i))/2^N).
If channel amplitudes are constant, generate each channel's N-bit gated tone /
noise mask and use sum(amplitude[channel]*mask[channel]). This executes three
32-bit hardware multiplies per eligible output, with the same oscillator and
LFSR transitions and same last ch_out[]. The envelope advances through the
qualified counter/state routine, including inaudible state.

Eligibility is deliberately conservative: quality/base_increment as before,
1..16 internal ticks, out[-32768,32767], the two standard volume tables,
env_ptr<32 and no envelope transition within these ticks when any channel uses
the envelope. At most3*4080*65535+32767=802181167, so the signed32-bit weighted
sum is bounded. Custom volume tables, other rates requiring>16ticks and an
audible envelope edge use the original per-tick mixer/filter. Silent batching
is retained. The former constant-span optimization is superseded by this path;
fallback is the reference per-tick loop. The output-tick calculation is shared
between silent/weighted paths to avoid duplicated code. The struct/API is unchanged.

Four inactive error messages in main.c are shortened to fit the diagnostic APP
under48KiB (49152 bytes; diagnostic SRAM49148 leaves4 bytes): framebuffer, missing color service, required PSRAM and invalid
snapshot. No ordinary run or measured-window reporting changes. This is an
explicit additional source difference, not a hidden feature removal.

HOST evidence, final candidate revision:

-524280 exhaustive mask/tick/signed-start/max-amplitude filter identities.
-817792 output samples with full PSG state compared every sample to the
 per-tick reference, six rates/all16 envelopes/masks/divider/quality/signed
 filter starts. Weighted eligibility609152; remaining samples fallback/silent.
-Actual APP scheduler/Z80/AY, fixed timestamped IN input: all32CPU fields, full
 RAM/video/bothPSG states/ordered sound events/fullPCM at every captured frame
 equal the production per-tick AY+outer512 reference: Manic/Cosmic/Ianna each
3100frames, plus80-frame dense keyboard/noise/AY/beeper program. Cosmic1587202
 PCM samples;13846 sound events at its final captured checkpoint. Input shifted
1000T changes trajectory. ASan/UBSan and actual APP three ROM modes pass.
-Same v2 observer/queue guard/frozen image/lifetime HOST tests pass.
-GCC nonshipping stack audit max8384B plus776B wrapper, shipping untouched.

Os+LTO ARM builds: ordinary SPECTRUM.APP34198file/47528SRAM; full-paced diagnostic
SPPIPE.APP35468file/49148SRAM. Expanded per-sample timing observer does not fit
(512B excess) and is not selected. Complete API/CPU/SPWORK/SPSOUND counters remain.
Hardware throughput/late-event/busy improvement is still unproved. No deployment
or production install/commit has occurred. This candidate is separate from the
unchanged old-AY matched WAITv2/PIPEv2 experiment.

This v2 note corrects the SRAM limit wording only. The accepted original note
and its pins are preserved; binaries and source are unchanged.
