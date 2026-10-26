# Exact midpoint boundary: author qualification complete, independent review pending

Parent `.build/m0-pow-square128-r2-20261025`, FROZEN31de9242, now has independent square
TECH_GO `eaa55a85a694bb33517f01db27355edb8b39e3a529768c150bc5fc5c161bfd24`. That verdict is limited to the
square kernel and is not acceptance of this new caller. Candidate ELF
`63a80f08c546e7bd07db6056eb1f64aa0de573c7296e5572b090e9d9f6edbfa9`, source CPP `f5f6428bd0a5c964af095d987b794548d1143f9603147eeb178cef8dd3e38795`.

The old inline128-bit midpoint square is replaced by a loop using the accepted
scheduled square kernel. All24 midpoint bytes and radius16/comparison rules
are identical. No precision reduction. The complete120980-pair/241960-state/
279522-reference-variant corpus freshly executes the candidate. Every one of454
changed states also freshly executes the parent, matching all24 midpoint bytes
and saved parent costs.454states save4–169instructions,0increases/0wrong/0new.
Loss pairs remain11434; original153 deficits remain34,119strict. This reduces
the gap but adds no new Qfplib victories. Author separate507 remains437=431strict
+6equal with70remaining(pow34/sin22/cos14); reviewed507 remains422 per ROOT.

Fresh5127-pair controls execute parent/control/candidate/all3Qfplib compositions:
61524ARM calls,5051 directedMPFR inputs plus76sNaN shortcuts. All10254state rows
match the full saved corpus. Wrong77106reference variants/costs retained with
strictquietNaN policy, no nominal filtering. Qualified309938freshARM=
241960candidate+454changed-path parent+61524freshcontrols+6000bare. Pilot1836,
failed preflight0, all rejected80trial calls and inherited oracle/reference
calls are not pooled into those totals.

Bare3000cases/6000actualARM use only actual code, no firmware/ROM/math models.
All16NZCV/noisyR3R12, ordinary PCS/SP/PC, bounded writes and exact dyadic interval
endpoints pass. Every side and midpoint byte matches old. Observed bare peak
212→156B. Overall candidate corpus peak2284unchanged; changed-path parent716
is a subset and is not a comparator for that full peak. Fresh control peaks
parent/control/candidate2148equal. Seventeen full objects/ELFs rebuilt byteexact.

Only the532B front slot changes; its two-instruction8B tail entry preserves
R0-R2/LR/SP/stack cell. New diagnostic body+literal228B, no new table/globalRAM/
libgcc/ROM-math dependency. Others' resident code, addresses, veneers, scratch
and tables unchanged. GenericM0/M4soft/M4hard selected assembly is equal;
guarded extraCPP is empty outsideRP2040. This is not a whole M4 firmware build.

The80bit filter remains explicitly rejected: all56public checks declined,
adding262–904instructions. Exact gaps require97–108 relative bits; an ideal96bit
filter also declined. Its19221bare+1836pilot ARM and153pilotMPFR are excluded.

No canonical source, Git, USB/device/Flash, hardware lease or release changes.
Near-one exp remains a separate accepted sibling. Generalpowtotality, remaining
math, source merge/relink, actual integrated R12/loader/layout guards, physical
cycles and release are open. Overall goal incomplete. Next investigation:
measure the actual1/hint double-division and32bitseed costs in READY/DIRTY before
designing a certified specialized reciprocal path; preserve correctly rounded
hint bits or all original boundary-selection invariants.
