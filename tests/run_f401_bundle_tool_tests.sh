#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
tool="$root/tools/build_f401_bundle.sh"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-f401-bundle-test.XXXXXX")"
trap 'rm -rf "$work"' EXIT

test -x "$tool"
bash -n "$tool"
"$tool" --help | grep -q -- '--profile ID'
"$tool" --help | grep -q 'MK61_ENABLE_WBMP_VIEWER'

set +e
"$tool" --profile unsupported > /dev/null 2>&1
status=$?
set -e
test "$status" -eq 2

set +e
MK61_ENABLE_FOCAL=2 "$tool" > /dev/null 2>&1
status=$?
set -e
test "$status" -eq 2

# При выключенных ключах сборщик не должен требовать overlay/toolchain и не
# должен оставлять старые MOD-файлы в комплекте. Arduino CLI здесь заменён
# минимальной моделью только resident-сборки.
fake_cli="$work/arduino-cli"
cat > "$fake_cli" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
build_path=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --build-path) build_path=$2; shift 2 ;;
    *) shift ;;
  esac
done
[ -n "$build_path" ]
mkdir -p "$build_path"
printf 'resident-elf' > "$build_path/mk61s-M.ino.elf"
printf 'resident-bin' > "$build_path/mk61s-M.ino.bin"
EOF
chmod +x "$fake_cli"

bundle="$work/output/mk61s-M-mini-v3-lcd1602-a00-f401"
mkdir -p "$bundle"
printf 'stale' > "$bundle/FOCAL.MOD"
printf 'stale' > "$bundle/BASIC.MOD"
printf 'stale' > "$bundle/WBMP.MOD"

MK61_ARDUINO_CLI="$fake_cli" \
MK61_F401_BUILD_ROOT="$work/build" \
MK61_OUTPUT_DIR="$work/output" \
MK61_ENABLE_FOCAL=0 \
MK61_ENABLE_TINYBASIC=0 \
MK61_ENABLE_WBMP_VIEWER=0 \
  "$tool" --profile mini-v3-a00 > "$work/output.log"

test -s "$bundle/mk61s-M-mini-v3-lcd1602-a00-f401.bin"
test -s "$bundle/build.flags"
test ! -e "$bundle/FOCAL.MOD"
test ! -e "$bundle/BASIC.MOD"
test ! -e "$bundle/WBMP.MOD"
grep -q -- '-DMK61_ENABLE_FOCAL=0' "$bundle/build.flags"
grep -q 'Built F401 bundle:' "$work/output.log"

printf 'f401_bundle_tool_tests: ok\n'
