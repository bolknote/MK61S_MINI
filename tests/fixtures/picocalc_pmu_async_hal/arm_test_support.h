#ifndef MK61_PMU_ARM_TEST_SUPPORT_H
#define MK61_PMU_ARM_TEST_SUPPORT_H
__attribute__((noreturn)) void test_arm_fail(unsigned line,const char* expression);
#define assert(expression) ((expression)?(void)0:test_arm_fail(__LINE__,#expression))
int printf(const char*,...);
#endif
