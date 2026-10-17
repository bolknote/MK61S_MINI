/* Keep the SDK string routines reachable in the ARM bounds/ABI fixture. */
#include <string.h>
static volatile const char* input = "abc";
int main(void) {
  const char* text = (const char*)input;
  return strcmp(text, "abcd") + (memchr(text, 0, 4) != 0);
}
