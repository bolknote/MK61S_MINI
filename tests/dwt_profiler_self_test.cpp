#include <cassert>
#include <iostream>

#define MK61_ENABLE_DWT_PROFILER 0
#include "dwt_profiler.hpp"

static void test_point_layout(void) {
  using dwt_profiler::Point;
  assert((usize) Point::FLASH_READ + 1 == (usize) Point::FLASH_WRITE);
  assert((usize) Point::FLASH_WRITE + 1 == (usize) Point::FLASH_VERIFY);
  assert((usize) Point::FLASH_VERIFY + 1 == (usize) Point::FLASH_ERASE);
  assert(dwt_profiler::POINT_COUNT == 17);
}

static void test_empty_statistics(void) {
  dwt_profiler::Statistics stats;
  assert(stats.samples == 0);
  assert(stats.minimum_cycles == 0);
  assert(stats.maximum_cycles == 0);
  assert(stats.total_cycles == 0);
  assert(stats.average_cycles() == 0);
}

static void test_accumulation(void) {
  dwt_profiler::Statistics stats;
  stats.add(40);
  stats.add(10);
  stats.add(25);
  assert(stats.samples == 3);
  assert(stats.minimum_cycles == 10);
  assert(stats.maximum_cycles == 40);
  assert(stats.total_cycles == 75);
  assert(stats.average_cycles() == 25);

  stats.reset();
  assert(stats.samples == 0);
  assert(stats.total_cycles == 0);
}

static void test_disabled_backend(void) {
  dwt_profiler::initialize();
  assert(!dwt_profiler::available());
  assert(!dwt_profiler::running());
  assert(!dwt_profiler::start());
  assert(dwt_profiler::clock_hz() == 0);
  assert(dwt_profiler::overhead_cycles() == 0);
}

static void test_disabled_scopes(void) {
  dwt_profiler::Scope scope(dwt_profiler::Point::CORE_STEP);
  dwt_profiler::Accumulator accumulator(dwt_profiler::Point::CORE_FETCH);
  dwt_profiler::AccumulatingScope segment(accumulator);
  (void) scope;
  (void) segment;
}

int main(void) {
  test_point_layout();
  test_empty_statistics();
  test_accumulation();
  test_disabled_backend();
  test_disabled_scopes();
  std::cout << "dwt_profiler_self_test: ok\n";
  return 0;
}
