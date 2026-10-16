#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-arduino-dependencies.XXXXXX")"
trap 'rm -rf "$work"' EXIT
helper="$root/tests/check_arduino_build_dependencies.sh"
fake_cli="$work/fake arduino-cli"
export MK61_TEST_CLI_VERSION
export MK61_TEST_CORE_VERSION
MK61_TEST_CLI_VERSION="$(python3 "$root/tools/release_contract.py" toolchain --field arduino_cli)"
MK61_TEST_CORE_VERSION="$(python3 "$root/tools/release_contract.py" toolchain --field stm32_core)"
cat > "$fake_cli" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  version) printf 'arduino-cli Version: %s Commit: test\n' "$MK61_TEST_CLI_VERSION" ;;
  'core list') printf 'STMicroelectronics:stm32 %s pinned STM32\n' "$MK61_TEST_CORE_VERSION" ;;
  compile*) printf 'compatibility compile reached\n' >&2; exit 79 ;;
  *) exit 80 ;;
esac
EOF
chmod +x "$fake_cli"

export MK61_ARDUINO_CLI="$fake_cli"
export MK61_GCC_TOOLCHAIN="$work/missing-independent-gcc"
bash "$helper" > "$work/valid.log"
for variable in MK61_TEST_CLI_VERSION MK61_TEST_CORE_VERSION; do
  if env "$variable=0.0.0" bash "$helper" > "$work/wrong-version.log" 2>&1; then
    printf 'Arduino dependency check accepted an incorrect version: %s\n' "$variable" >&2
    exit 1
  fi
  grep -q 'is required' "$work/wrong-version.log"
done
if MK61_ARDUINO_CLI="$work/missing cli" bash "$helper" > "$work/missing.log" 2>&1; then
  printf 'Arduino dependency check accepted a missing CLI\n' >&2
  exit 1
fi
grep -q 'arduino-cli is not installed' "$work/missing.log"

# These are Arduino builds. Each must reach its compiler even when the
# independent SDK toolchain is absent, as in the optional CI job.
for script in run_f411_o3_compile_check.sh run_stock_linker_compile_check.sh \
    run_f401_uc1609_compile_check.sh; do
  if bash "$root/tests/$script" > "$work/$script.log" 2>&1; then
    printf 'Arduino compatibility check ignored the compiler failure: %s\n' "$script" >&2
    exit 1
  fi
  grep -q 'compatibility compile reached' "$work/$script.log" || {
    cat "$work/$script.log" >&2
    printf 'Arduino compatibility check required independent GCC: %s\n' "$script" >&2
    exit 1
  }
done
printf 'arduino_build_dependencies_tests: ok\n'
