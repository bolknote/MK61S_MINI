#include <assert.h>
#include <stddef.h>

size_t mk61_test_strlen(const char* text);
int mk61_test_strcmp(const char* left, const char* right);
char* mk61_test_strchr(const char* text, int character);

int main(void) {
  const char m8[] = {'A', (char) 0xE0, 'B', 0};

  assert(mk61_test_strlen("") == 0);
  assert(mk61_test_strlen(m8) == 3);
  assert(mk61_test_strcmp("", "") == 0);
  assert(mk61_test_strcmp("AB", "AB") == 0);
  assert(mk61_test_strcmp("A", "AB") < 0);
  assert(mk61_test_strcmp("AB", "A") > 0);
  assert(mk61_test_strcmp(m8, "AZ") > 0); /* unsigned M8 bytes */
  assert(mk61_test_strchr(m8, 'A') == m8);
  assert(mk61_test_strchr(m8, 0xE0) == m8 + 1);
  assert(mk61_test_strchr(m8, 0) == m8 + 3);
  assert(mk61_test_strchr(m8, 'Z') == NULL);
  return 0;
}
