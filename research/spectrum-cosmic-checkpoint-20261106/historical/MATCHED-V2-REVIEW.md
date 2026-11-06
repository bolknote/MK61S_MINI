# Matched WAIT/PIPE, observer v2, production2483

Next requested phase runs only WAIT (no prefetch) for100warmup+all10x300frames.
SPWAIT.APP35373 file bytes /48996 SRAM bytes. Its source tree is control/candidate.
PIPE v2 is separately built:35380 file /49140 SRAM bytes; no additional hardware
scope is implied. Both use identical old qualified AY batching, real Z80/MMU,
25kHz stereo callback and all peripherals. The only functional difference is
the removal of the prefetch block from WAIT. Ordinary SPECTRUM.APP is untouched.

The v2 observer samples final API return time and updates all counters first,
then emits SPPACING_DONE. No report occurs inside the full3001-API-endpoint /
3000-interval measurement. Positive C metrology tests verify records3001 and
final timestamp at report time. The old observer is rejected by the same test
(ordering-negative.json/log). Old v1 measured results, including its contaminated
last endpoint, are retained unchanged and are not an identical observer control.
All original ten windows and busy/repeat/skip/early/fault outcomes remain.
Accepted API return time is not physical LCD scanout.

Both variants will run on current2483E8A7/22F8ED32/1537040 production at125MHz,
using the new Math RELEASE-001. Eleven input/display/audio/ABI platform files
are byte-identical to717 (platform-2483-equivalence.json). Older717 outcomes
remain descriptive. The controller validates one clean free heap block with
at least104368 bytes before any upload; otherwise HOLD, close and separate
reset review. No implicit reset or image restoration. Same root/menu/snapshot
and p10 controller protocol as prior HIL. Individual guest input timestamps are
not recorded; the HOST replay input is separately declared and not an exact
HIL trace. Test times/frames are never trimmed to isolate the steady scene.

Consumer SPSOUND diagnostics remain, but the per-sample core1 timing observer
does not fit this full APP probe and is absent from both matched variants.
The new weighted AY algorithm is separate, HOST-only and not in this packet.

HOST native717 planner replay found no palette/border changes in Cosmic's
measured frames; palette-mask optimization saved zero bytes. Wire-only12.5Mbit/s
model predicts43busy first-window attempts/max81.92ms gap, no later busy; actual
v1 HIL had142busy/max307.37ms. Replay input differs from HIL input protocol;
CPU/DMA/I2C/IRQ times are not modeled. This is evidence to investigate native
transfer/CPU scheduling, not proof of a single cause or a physical scanout rate.
