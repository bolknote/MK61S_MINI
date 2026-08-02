#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"

# GitHub's Ubuntu host job currently uses Clang 18. Newer Apple/upstream
# Clang versions accept a few constructs that Clang 18 rejects, so flags alone
# do not reproduce the release gate. Select the same frontend explicitly.
candidates=()
if [[ -n "${MK61_CI_CLANGXX:-}" ]]; then
  candidates+=("$MK61_CI_CLANGXX")
fi
if [[ "$(uname -s)" == "Darwin" ]]; then
  candidates+=(
    /opt/homebrew/opt/llvm@18/bin/clang++
    /usr/local/opt/llvm@18/bin/clang++
  )
fi
candidates+=(clang++-18 clang++)

strict_cxx=""
strict_version=""
for candidate in "${candidates[@]}"; do
  if [[ "$candidate" == */* ]]; then
    resolved="$candidate"
  else
    resolved="$(command -v "$candidate" 2>/dev/null || true)"
  fi
  [[ -n "$resolved" && -x "$resolved" ]] || continue
  version="$($resolved --version 2>/dev/null || true)"
  if [[ "$version" == *"clang version 18."* ]]; then
    strict_cxx="$resolved"
    strict_version="${version%%$'\n'*}"
    break
  fi
done

if [[ -z "$strict_cxx" ]]; then
  printf '%s\n' \
    'CI-strict tests require Clang 18.' \
    'macOS: brew install llvm@18' \
    'Linux: install clang-18, or set MK61_CI_CLANGXX to its clang++ path.' >&2
  exit 2
fi

shim_root="$(mktemp -d "${TMPDIR:-/tmp}/mk61-ci-clang.XXXXXX")"
cleanup() {
  rm -rf "$shim_root"
}
trap cleanup EXIT HUP INT TERM
original_path="$PATH"

run_suite() {
  local name="$1"
  local compiler="$2"
  local sanitizers="$3"
  local shim_dir="$shim_root/$name"
  mkdir "$shim_dir"
  ln -s "$compiler" "$shim_dir/clang++"
  PATH="$shim_dir:$original_path" \
    MK61_TEST_SANITIZERS="$sanitizers" \
    "$root/tests/run_all_tests.sh"
}

printf 'CI-strict frontend: %s\n' "$strict_version"
if [[ "$(uname -s)" == "Darwin" ]]; then
  # LLVM 18's Darwin ASan runtime predates current macOS shadow-memory changes
  # and hangs during initialization. Keep its exact frontend diagnostics, then
  # run the same suite again under the supported system sanitizer runtime.
  sanitizer_cxx="${MK61_SANITIZER_CLANGXX:-/usr/bin/clang++}"
  if [[ ! -x "$sanitizer_cxx" ]]; then
    printf 'Sanitizer compiler is not executable: %s\n' "$sanitizer_cxx" >&2
    exit 2
  fi
  printf 'Pass 1/2: Clang 18 portability checks\n'
  run_suite strict "$strict_cxx" 0
  printf 'Pass 2/2: %s with ASan + UBSan\n' \
    "$($sanitizer_cxx --version | sed -n '1p')"
  run_suite sanitizers "$sanitizer_cxx" 1
else
  printf 'Pass 1/1: Clang 18 with ASan + UBSan\n'
  run_suite strict "$strict_cxx" 1
fi
