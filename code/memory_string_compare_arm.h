/* M4 byte strcmp selected on Classic. Keep the measured public entry local
 * to both resident and APPs; the existing runtime has no strcmp slot. */
#ifndef MK61_MEMORY_STRING_COMPARE_ARM_H
#define MK61_MEMORY_STRING_COMPARE_ARM_H
#if defined(__ARM_ARCH_7EM__) && defined(__GNUC__) && !defined(__clang__)
#define MK61_ARM_STRCMP 1
__attribute__((noipa, aligned(4)))
int strcmp(const char* left, const char* right) {
  const unsigned char* a = (const unsigned char*) left;
  const unsigned char* b = (const unsigned char*) right;
  for(;;) {
    const unsigned x = *a++, y = *b++;
    if(x != y || !x) return (int) x - (int) y;
  }
}
#endif
#endif
