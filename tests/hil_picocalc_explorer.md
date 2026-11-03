# Native Explorer hardware qualification

`hil_picocalc_explorer.py` is a bounded test for one explicitly identified Pico H.
It does not install firmware. Its only SD writes are inside a fresh
`/MK61S-EXPLORER-<UTC timestamp>` directory. Installing the bundled icons into
existing `/games` folders is a separate step after this test passes.

The local build and fake-port tests do not establish which firmware is currently
installed. While the Pico is disconnected, its current fallback image, state and
RTC cannot be verified. Historical build IDs are not evidence of its current
contents. A future device session needs a fresh access window from the device
coordinator; this document does not reserve or open the device.

## Before installing a candidate

1. In the agreed observe window, identify the serial node and check its UID using
   `identity`. Save complete `status`, `identity`, `date`, `alarm`, `pwd`, `reg`,
   `stk` and `hout` replies to a new host directory. Record host UTC and monotonic
   time with the RTC reading. Require a valid resident CRC, the expected UID,
   `CRASH=NONE`, `DIRTY=0`, `USB_DISK=0`, `M61_ACTIVE=0`, `RUN=0 BUSY=0` and an
   idle calculator/menu. Capture `PHYSICAL_KEYS` before any navigation.
2. Validate exactly R0..RE (also RF in the 112-cell mode) and S0..S4, including
   LAST X, and a complete contiguous program dump. The unqualified Pico `hout`
   dumps the active 105/112-cell bank;
   its total length must match `STEPS` and the reported `MEMORY` mode. Unknown
   modes and short contiguous prefixes are rejected before navigation or writes.
   Preserve its exact text. For an expanded-memory mode, additionally read the
   absolute address space with `hout <decimal start> <count>`, in chunks of at
   most 112 bytes through address 9999; the last count is shortened. Check every
   returned address and byte count. Save these replies separately and never
   treat a truncated reply or empty match as an unchanged program.
3. Save IP, programming mode and the settings shown in `status`, including
   memory/step count, language, speed, random mode, calculator font, UI font
   family/size/key, USB Screen state, RTC_SET and RTC_PPM. If any public number
   cannot round-trip through the existing restore helper, stop before flashing.
4. Close the serial owner. In the separately agreed BOOTSEL/flash window, save
   and verify the *actual installed* flash before overwriting it. For example,
   using the UID observed above as the device selector:

   ```sh
   picotool save -a -v fallback-all.uf2 --ser <UID>
   picotool save -r 0x101FE000 0x10200000 -v settings.bin --ser <UID>
   ```

   The second range is the Pico H's 8192-byte settings journal, not RAM. Record
   the SHA-256 of both host files. Decode the saved UF2, verify the resident
   integrity footer, and match its build ID/CRC to the fresh observe replies.
   Also match the settings range against the same bytes in `fallback-all.uf2`.
   A manifest for an old local build alone is insufficient. Keep these backups
   outside the candidate output directory. No erase-all command is needed.
5. Verify the candidate UF2 against its own manifest and integrity footer. Its
   payload must end before the settings journal. Load only the candidate, using
   the same UID selector and verification, then re-observe the exact expected
   BUILD and valid resident CRC before restoring public calculator state.

## Restore and qualify

Restore through the established public helpers after a fresh physical-key and
safe-context check. The `restore` helper in `hil_picocalc_software.py` restores
LAST X, X/Y/Z/T, registers and the active program. Replay the separately saved
absolute `hin` lines as needed for expanded banks; `hin` addresses are decimal.
Re-read and compare every saved range. Restore the terminal directory with
`cd <saved absolute path>` if it changed.

Restore IP with the existing `restore_ip` helper in
`hil_picocalc_render_i2c_sd.py`: GOTO takes two digits, so cells above 99 use
program-mode STEP keys, then return to AUTO. It must run after restoring the
program and numbers. Confirm IP, programming mode and all public data again.
If the saved state needs a restoration route beyond the helper's supported
physical bank, stop before flashing and extend that route with a host test.

The candidate preserves the settings journal. Compare the settings fields after
boot; do not reset them to defaults. If rollback is needed, loading the verified
`fallback-all.uf2` restores both the original firmware and the exact settings
journal; public calculator state still needs the host snapshot. Restore its IP
and re-read all numbers/program bytes after rollback too.

Preserve an already configured RTC by advancing the captured local clock by
elapsed monotonic time. The CLOCK_SYNC packet (0x40) accepts mode 2 and
`<BH5B>`: mode, year, month, day, hour, minute, second; confirm the CLOCK_STATE
reply (0x41). Do not replace it with host time in another timezone. If RTC_SET
was zero, leave it unset. Check saved alarms and calibration after the test.
The RTC protocol and exclusive-port handling are in `tools/sync_picocalc_clock.py`.

Only after the restored baseline is validated, run:

```sh
python3 tests/hil_picocalc_explorer.py \
  --port <leased serial node> --uid <UID> --build-id <candidate BUILD> \
  --output <new host evidence directory>
```

The test saves native frames and compares their CRC with completed LCD output.
It checks icons, selection, folder-open bypass, paging, search, list mode and an
empty folder. Fresh safe-context/PHYSICAL_KEYS guards precede cleanup navigation,
restoration, removal and USB Screen cleanup. A changed counter, timeout or unsafe
context stops device mutations: only host logs and port closure remain. Leave
the private directory for a later agreed cleanup if that guard trips. Never
restore an old snapshot over new physical input.

`picocalc_explorer_hil_self_test.py` tests those failure paths with fake ports;
it neither enumerates devices nor opens a serial node. Keep
`hardware_verified=false` until the actual candidate passes hardware testing.
