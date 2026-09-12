#include "eliza_engine.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

static void expect_reply(eliza_state* state, const char* input,
                         const char* expected) {
  char output[ELIZA_REPLY_BYTES];
  eliza_reply(state, input, output, sizeof(output));
  if(strcmp(output, expected) != 0) {
    fprintf(stderr, "input:    %s\nexpected: %s\nactual:   %s\n",
            input, expected, output);
    assert(0);
  }
}

static void test_classic_rules(void) {
  eliza_state state;
  eliza_init(&state);

  expect_reply(&state, "I want a quiet room",
               "WHAT WOULD IT MEAN TO YOU IF YOU GOT A QUIET ROOM?");
  expect_reply(&state, "I'm very sad",
               "I AM SORRY TO HEAR YOU ARE VERY SAD.");
  expect_reply(&state, "My mother dislikes me",
               "TELL ME MORE ABOUT YOUR FAMILY.");
  expect_reply(&state, "Can you help me",
               "YOU BELIEVE I CAN HELP YOU, DON'T YOU?");
  expect_reply(&state, "You hate me",
               "WHY DO YOU THINK I HATE YOU?");
}

static void test_ranking_rotation_and_repeat(void) {
  eliza_state state;
  eliza_init(&state);

  expect_reply(&state, "I am afraid of computers", "DO COMPUTERS WORRY YOU?");
  expect_reply(&state, "Computers are everywhere", "WHY DO YOU MENTION COMPUTERS?");
  expect_reply(&state, "computers are everywhere", "PLEASE DON'T REPEAT YOURSELF.");
  expect_reply(&state, "computer", "WHAT DO MACHINES HAVE TO DO WITH YOUR PROBLEM?");
}

static void test_memory(void) {
  eliza_state state;
  eliza_init(&state);

  expect_reply(&state, "My bicycle is broken", "YOUR BICYCLE IS BROKEN?");
  expect_reply(&state, "Zqxv", "LET'S DISCUSS FURTHER WHY YOUR BICYCLE IS BROKEN.");
  expect_reply(&state, "Another unrelated sentence",
               "I AM NOT SURE I UNDERSTAND YOU FULLY.");
}

static void test_goodbye_and_bounds(void) {
  eliza_state state;
  struct {
    char output[12];
    unsigned char guard;
  } bounded = {{0}, 0xA5};

  assert(eliza_is_goodbye("bye"));
  assert(eliza_is_goodbye("  Good-bye! "));
  assert(eliza_is_goodbye("QUIT."));
  assert(!eliza_is_goodbye("goodbye for now"));

  eliza_init(&state);
  eliza_reply(&state, "I want an extraordinarily long reply", bounded.output,
              sizeof(bounded.output));
  assert(bounded.output[sizeof(bounded.output) - 1] == 0);
  assert(bounded.guard == 0xA5);
}

int main(void) {
  test_classic_rules();
  test_ranking_rotation_and_repeat();
  test_memory();
  test_goodbye_and_bounds();
  puts("eliza engine tests passed");
  return 0;
}
