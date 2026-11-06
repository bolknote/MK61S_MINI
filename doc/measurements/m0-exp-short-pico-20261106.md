# RP2040 exp short paths: Pico measurements, 2026-11-06

Four targeted short exp cases now beat direct Qfplib on the Pico H at125MHz.
Each of their six opposite-order pair differences is negative. The remaining
short case and both expensive refinement controls remain slower and are
retained in the table and raw records.

| Случай | Было845, мкс | Стало717, мкс | Qfplib, мкс | Теперь против Qfplib |
|---|---:|---:|---:|---:|
| exp: короткий1 | 5.727 | 5.511 | 5.663 | -2.7% |
| exp: короткий2 | 5.727 | 5.510 | 5.663 | -2.7% |
| exp: короткий3 | 5.727 | 5.511 | 5.663 | -2.7% |
| exp: прежде почти равный | 5.702 | 5.486 | 5.687 | -3.5% |
| exp: оставшийся короткий | 6.536 | 6.425 | 6.165 | +4.2% |

12 раундов с обоими порядками вызова и вычетом контроля; «−» означает быстрее. BASE — предыдущий полный аппаратный прогон845, сравнение NEXT/Qfplib сделано попарно в новом прогоне. Все ответы совпали с MPFR.

The two measured refinement controls are still slower:

| Input bits | NEXT717, us | Qfplib, us | Time difference |
|---|---:|---:|---:|
| C012F11092627388 | 25.053345 | 6.887207 | +263.766% |
| 40855D07F8ABAA72 | 24.713867 | 6.464233 | +282.317% |

All16 groups/1244 cases pass exact directed-MPFR checks for both libraries;
1240 unique operation/input pairs and2488 captured return values are
independently re-decoded. Twelve rounds use a typed matching control, both
call orders, bounded one-second warmup and XIP hit/access counters. The
empirical range of the six paired deltas is not a confidence interval.

The baseline column is the previous full845 hardware session with the
same frozen inputs. NEXT717 and Qfplib were measured together in the new
session; BASE and NEXT are separate sessions. Wide exp averages improve
from6.102783 to5.914795us (random8) and5.957153 to5.779663us (random700).
Sin/cos controls, including the old cache outlier, pass. Their code and
addresses are byte-identical to qualified845. M4/generic control objects
remain byte-identical; pow and table algorithms are unchanged.

Final working production is7172507E/638CEB66,1537048 bytes, staticRAM125004
bytes. New tables/RAM:0. The test namespace was removed; native checks,
all descriptor closes and named holder checks pass. The hardware process
exited0 and the Pico was explicitly released to Coordinator. No previous
state was captured/restored and no RTC setter ran. Two early postboot KBD
HOLDs retain immutable write/readback evidence and are completed by fresh
native validation receipts; no repeat flash was performed.

Evidence: [group measurements](m0-exp-short-pico-20261106/hardware-groups.csv),
[raw v5 records](m0-exp-short-pico-20261106/hardware-records.jsonl.gz),
[summary](m0-exp-short-pico-20261106/hardware-summary.json).

Raw SHA256: `6ff67a29305daa8f6445c8ae5d135a8c3b378b5399c9e46992a17919f2dd35e7`.
