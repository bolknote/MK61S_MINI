#include "bounded_string.hpp"

#include <assert.h>
#include <stdio.h>
#include <string.h>

static void test_exact_and_truncated_copy(void) {
  char exact[5] = {};
  assert(bounded_string::copy(exact, "abcd") == 4);
  assert(strcmp(exact, "abcd") == 0);

  struct Guarded {
    char before;
    char text[4];
    char after;
  } guarded = {'L', {}, 'R'};
  assert(bounded_string::copy(guarded.text, "abcdef") == 3);
  assert(strcmp(guarded.text, "abc") == 0);
  assert(guarded.before == 'L');
  assert(guarded.after == 'R');
}

static void test_empty_and_zero_capacity(void) {
  char text[4] = {'x', 'x', 'x', 0};
  assert(bounded_string::copy(text, (const char*) NULL) == 0);
  assert(text[0] == 0);

  text[0] = 'x';
  assert(bounded_string::copy(text, 0, "abc") == 0);
  assert(text[0] == 'x');
  assert(bounded_string::copy(NULL, 4, "abc") == 0);
}

static void test_overlapping_copy(void) {
  char left[8] = "abcdef";
  assert(bounded_string::copy(left, 5, left + 2) == 4);
  assert(strcmp(left, "cdef") == 0);

  char right[8] = "abcdef";
  assert(bounded_string::copy(right + 1, sizeof(right) - 1, right) == 6);
  assert(strcmp(right + 1, "abcdef") == 0);
}

int main(void) {
  test_exact_and_truncated_copy();
  test_empty_and_zero_capacity();
  test_overlapping_copy();
  printf("bounded_string_self_test: ok\n");
  return 0;
}
