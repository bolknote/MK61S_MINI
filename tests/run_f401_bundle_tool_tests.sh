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
"$tool" --help | grep -q 'MK61_ENABLE_MARKDOWN_VIEWER'
"$tool" --help | grep -q 'MK61_ENABLE_CHIP8'
"$tool" --help | grep -q -- '--app-manifest FILE'

app_dir="$work/app"
mkdir -p "$app_dir/include"
printf '%s\n' \
  'format 1' \
  'name DEMO' \
  'source demo.cpp' \
  'file include/demo.hpp' > "$app_dir/app.mk61"
printf '%s\n' '#include "include/demo.hpp"' > "$app_dir/demo.cpp"
printf '%s\n' '#pragma once' > "$app_dir/include/demo.hpp"
"$tool" --check-app-manifests \
  --app-manifest "$app_dir/app.mk61" > "$work/app-check.log"
grep -q '^Validated APP manifests: 1$' "$work/app-check.log"
grep -q '^Apps/DEMO.APP <- ' "$work/app-check.log"
MK61_APP_MANIFESTS="$app_dir/app.mk61" \
  "$tool" --check-app-manifests > "$work/app-env-check.log"
grep -q '^Validated APP manifests: 1$' "$work/app-env-check.log"
printf '%s\n' \
  'format 1' \
  'name EXTRA' \
  'source demo.cpp' > "$app_dir/extra.mk61"
MK61_APP_MANIFESTS="$app_dir/app.mk61;$app_dir/extra.mk61" \
  "$tool" --check-app-manifests > "$work/app-env-list-check.log"
grep -q '^Validated APP manifests: 2$' "$work/app-env-list-check.log"

printf '%s\n' \
  'format 1' \
  'name BROKEN' \
  'source ../escape.cpp' > "$app_dir/broken.mk61"
set +e
"$tool" --check-app-manifests \
  --app-manifest "$app_dir/broken.mk61" > /dev/null 2>&1
status=$?
set -e
test "$status" -ne 0

printf '%s\n' \
  'format 1' \
  'name CASEPATH' \
  'source demo.cpp' \
  'file DEMO.CPP' > "$app_dir/case-path.mk61"
set +e
"$tool" --check-app-manifests \
  --app-manifest "$app_dir/case-path.mk61" > /dev/null 2>&1
status=$?
set -e
test "$status" -ne 0

printf '%s\n' 'void helper(void) {}' > "$app_dir/helper.c"
printf '%s\n' \
  'format 1' \
  'name BADFILE' \
  'source demo.cpp' \
  'file helper.c' > "$app_dir/compiled-file.mk61"
set +e
"$tool" --check-app-manifests \
  --app-manifest "$app_dir/compiled-file.mk61" > /dev/null 2>&1
status=$?
set -e
test "$status" -ne 0

printf '%s\n' \
  'format 1' \
  'name CON' \
  'source demo.cpp' > "$app_dir/reserved-name.mk61"
set +e
"$tool" --check-app-manifests \
  --app-manifest "$app_dir/reserved-name.mk61" > /dev/null 2>&1
status=$?
set -e
test "$status" -ne 0

printf '%s\n' \
  'format 1' \
  'name demo' \
  'source demo.cpp' > "$app_dir/duplicate.mk61"
set +e
"$tool" --check-app-manifests \
  --app-manifest "$app_dir/app.mk61" \
  --app-manifest "$app_dir/duplicate.mk61" > /dev/null 2>&1
status=$?
set -e
test "$status" -ne 0

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

# Полная ARM-сборка проходит в release matrix. Здесь фиксируем политику
# общего ABI, не подменяя новый обязательный SETUP.APP старым «пустым» путём.
grep -Fq 'MK61_ENABLE_LOADABLE_MODULES=1' "$tool"
grep -Fq 'tools/build_system_app_bundle.py' "$tool"
grep -Fq 'tools/build_portable_app.py' "$tool"
grep -Fq 'MK61_APP_LOCAL_FLOAT_MATH' "$tool"
grep -Fq "printf 'abi 5" "$tool"
if grep -Fq 'MK61_ENABLE_USER_APPS' "$tool" ||
   grep -Fq 'MK61_ENABLE_PORTABLE_APPS' "$tool"; then
  echo 'F401 builder still contains a second/legacy APP runtime' >&2
  exit 1
fi

printf 'f401_bundle_tool_tests: ok\n'
