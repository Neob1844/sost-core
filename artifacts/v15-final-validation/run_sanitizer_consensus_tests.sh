#!/usr/bin/env bash
# V15 gate #6/#7: ASan+UBSan over the V15 consensus arithmetic unit suites.
# Bounded (only the consensus test targets + their deps). Reusable on a clean box.
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
B=build-asan
cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Debug \
  -DCMAKE_CXX_FLAGS="-fsanitize=address,undefined -fno-omit-frame-pointer -g -O1" \
  -DCMAKE_EXE_LINKER_FLAGS="-fsanitize=address,undefined" >/"$B".cfg.log 2>&1 || cmake -S . -B "$B" \
  -DCMAKE_CXX_FLAGS="-fsanitize=address,undefined -fno-omit-frame-pointer -g -O1" \
  -DCMAKE_EXE_LINKER_FLAGS="-fsanitize=address,undefined"
TARGETS="test-jackpot test-lottery-rollover test-dtd-control test-lottery-eligibility test-lottery-frequency"
nice -n 19 ionice -c3 cmake --build "$B" --target $TARGETS -j2
export UBSAN_OPTIONS=print_stacktrace=1:halt_on_error=1
export ASAN_OPTIONS=detect_leaks=1:abort_on_error=0
rc=0
for t in $TARGETS; do
  echo "=== $t (ASan+UBSan) ==="
  if "$B/$t"; then echo "  [$t] clean"; else echo "  [$t] SANITIZER/FAIL rc=$?"; rc=1; fi
done
echo "SANITIZER RESULT rc=$rc"; exit $rc
