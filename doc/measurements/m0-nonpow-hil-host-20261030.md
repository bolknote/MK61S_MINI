# Non-pow: SDK/HIL HOST checkpoint, 2026-10-30

Исторический отчёт отдельного этапа. Итог физических замеров и возврата
устройства: [nonpow 31 октября](m0-nonpow-20261031.md).

SDK source: immutable main eaaff37349149f86ebe7c25275a09da3f6ae906d; NEXT overlays exactly12qualifiedmathpaths. M4 controls remain exact. HOST andSDKparentpackages reverified. No device access in this checkpoint; pow development deferred.

| Actual SDK ARM matrix | BASE | NEXT |
|---|---:|---:|
| Unique inputs |21699|21699|
| Wrong owned results |0|0|
| Correct Qfplib refs |19882|19882|
| Faster / equal / slower vs correct Qfplib, instructions |18921 /629 /332|19251 /631 /0|
| Former170points: faster / equal / slower |0 /0 /170|160 /10 /0|

Raw1817wrongreferencecases retained. Compared withourSDKBASE, NEXT is faster3542/equal16278/slower1879. These adverse rows are retained in SDK-ADVERSE-ALL.json. They cover sin/cos/ln/tan and are a real tradeoff, despite0correctQfplibinstructionlosses. New SDK extra162loss points plus former170 become332singleton physical tests.34adverse representatives include actualSDKmaxdelta/maxratio for allfourfunctions.

Both production-preserving diagnostic images append exactly6364B Qfplib at0x10180000. Allownedmath addresses/bytes, originalprogramheaders andRAMinitializers remain exact. Only2nonmath image-bound literals and the40Bfooter are patched; actualARMboot/recheck CRC accepts the wholeimage and rejectsbadextent/referencecorruption. Diagnostic BASE CRC E8E2D2E8, NEXT540DEFD8, size1579228B each. Production SDK deltas remain +224text/+48BIN/0staticRAM; hot4096/4096, no newtables.

Bounded timingAPP:1709B, ABI6,10720B loaded. Source-level typedinvoke/control/timedmeasure bodies preserved;12balancedrounds withmatchedcontrols/TIMERAWL/XIPcounters. Warmup lasts1s withatmost32768own/refpairs; actualpaircount is returned inwirev5. All13typedpaths, cap saturation andfailure detection passed onbothARMELFs. Perrole13badinputformats caused0mathcalls,11badreports rejected. Physicaldecoder separately enforces>=1000000us/exactcap32768 and frozeninputs/referencebits/mask; its offlinewiretests are synthetic, notphysicaltimings. DirectFMA is outside this13-kind caller; existing fullFMA HOSTqualification remains separate.

Physical proposal perrole:139corpuschunks +170formerloss +34adverse +162newSDKloss =505APPopens.66batches ofatmost8APPopens/180s; eachAPPdeadline120s. Upperbound perrole56441722publicmathcalls bothlibraries +23301912calibrationcalls; actualwarmupcalls recorded. Proposed overallwindow3600s, noautomaticextension/retry. This is a proposal, nothardwareauthority.

Only first readonly capture is ready for Rootreview. capture-wake/ is a separatefrozen successor to preserved/unexecuted capture/v1. KnownCLOSED SET1 COMMAND sleep1 is admitted only by unchanged qualified US+exactidentity; postidentity SLEEP0 required, baseline records1→0.17actualfunction HOSTfixtures passed, includingrequirednegativecases. No RAWswitch,APP,SD,Flash,reset,ROM,DATEsetter,physicalkeys ornewwakemechanism. Livegrant/canonicalroute is notpresent.

Currentresident, calculator/clock/SDstate,2matching fresh2MiBcopies andreturnimage are deliberatelyunbound. Historical D6FABB43/EFBF5584 is lineage only. Later Flash/SD/APP/math/returnoperators are notready and require freshcapture-derived binding, qualification and separateRootGo. OriginalRTCtrajectory and freshfullFlash/SD/calculator/IP/settings/alarms mustbeverified onreturn. Unexpectedstate givesHOLD, noimplicitreset/recovery. Existingstartup2powcalls remain standardboot behavior; benchmarkpowcalls0.

Preparation failures retained: missingcallerheader, packerexecutablemode andstrictIP00format. These were isolatedsnapshot/diagnosticoperator fixes; noproduct/mathchange. Allproducers ended. Full plan, rawperinputSDKrecords, adverse rows, inputs, source deltas, qualifiedoperators andterminalreceipts are frozen withthischeckpoint. FiniteHOSTtests do notproveuniversal allinputcorrectrounding or physicalspeed.
