#include "eliza_engine.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

/*
 * Expected transcripts are CC0 test vectors from Anthony Hay's faithful
 * ELIZA recreation, revision 0d34ebc234090a417755afe8fe4a31f75e2e55bf.
 */
struct exchange {
  const char* prompt;
  const char* response;
};

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

static void run_transcript(const struct exchange* transcript, size_t count) {
  eliza_state state;
  uint8_t memory[ELIZA_MEMORY_WORKSPACE_BYTES];
  size_t index;
  eliza_init(&state, memory, sizeof(memory));
  for(index = 0; index < count; ++index)
    expect_reply(&state, transcript[index].prompt, transcript[index].response);
}

static const struct exchange CACM_CONVERSATION[] = {
    { "Men are all alike.",
      "IN WHAT WAY" },
    { "They're always bugging us about something or other.",
      "CAN YOU THINK OF A SPECIFIC EXAMPLE" },
    { "Well, my boyfriend made me come here.",
      "YOUR BOYFRIEND MADE YOU COME HERE" },
    { "He says I'm depressed much of the time.",
      "I AM SORRY TO HEAR YOU ARE DEPRESSED" },
    { "It's true. I am unhappy.",
      "DO YOU THINK COMING HERE WILL HELP YOU NOT TO BE UNHAPPY" },
    { "I need some help, that much seems certain.",
      "WHAT WOULD IT MEAN TO YOU IF YOU GOT SOME HELP" },
    { "Perhaps I could learn to get along with my mother.",
      "TELL ME MORE ABOUT YOUR FAMILY" },
    { "My mother takes care of me.",
      "WHO ELSE IN YOUR FAMILY TAKES CARE OF YOU" },
    { "My father.",
      "YOUR FATHER" },
    { "You are like my father in some ways.",
      "WHAT RESEMBLANCE DO YOU SEE" },
    { "You are not very aggressive but I think you don't want me to notice that.",
      "WHAT MAKES YOU THINK I AM NOT VERY AGGRESSIVE" },
    { "You don't argue with me.",
      "WHY DO YOU THINK I DON'T ARGUE WITH YOU" },
    { "You are afraid of me.",
      "DOES IT PLEASE YOU TO BELIEVE I AM AFRAID OF YOU" },
    { "My father is afraid of everybody.",
      "WHAT ELSE COMES TO MIND WHEN YOU THINK OF YOUR FATHER" },
    { "Bullies.",
      "DOES THAT HAVE ANYTHING TO DO WITH THE FACT THAT YOUR BOYFRIEND MADE YOU COME HERE" },
};

    static const struct exchange REFERENCE_COVERAGE[] = {
        { "Sorry, I'm a bit nervous.",
          "PLEASE DON'T APOLIGIZE" },
        { "I remember The house where I was born, The little window where the sun Came peeping in at morn.",
          "DO YOU OFTEN THINK OF THE HOUSE WHERE YOU WAS BORN" },
        { "Do you remember the Gulf of Mexico?",
          "DID YOU THINK I WOULD FORGET THE GULF OF MEXICO" },
        { "What if the moon is made of cheese?",
          "DO YOU THINK ITS LIKELY THAT THE MOON IS MADE OF CHEESE" },
        { "I dreamt that I dwelt in marble halls",
          "REALLY, THAT YOU DWELT IN MARBLE HALLS" },
        { "I dreamed of you.",
          "HAVE YOU EVER FANTASIED OF I WHILE YOU WERE AWAKE" },
        { "in my dream i was pregnant, but I'm male.",
          "WHAT DOES THAT DREAM SUGGEST TO YOU" },
        { "My dreams are weird.",
          "DO YOU DREAM OFTEN" },
        { "How do you do?",
          "WHY DO YOU ASK" },
        { "When am I going to be a grown-up?",
          "DOES THAT QUESTION INTEREST YOU" },
        { "he and I are so alike!",
          "IN WHAT WAY" },
        { "things are not the same between us as they once were",
          "WHAT RESEMBLANCE DO YOU SEE" },
        { "Certainly not!",
          "YOU SEEM QUITE POSITIVE" },
        { "Perhaps she'll die!",
          "YOU DON'T SEEM QUITE CERTAIN" },
        { "Maybe it's because I'm a Londoner",
          "WHY THE UNCERTAIN TONE" },
        { "A rose by any other name would smell as sweet",
          "I AM NOT INTERESTED IN NAMES" },
        { "Parlez-vous Italiano mademoiselle?",
          "I AM SORRY, I SPEAK ONLY ENGLISH" },
        { "Hello there!",
          "HOW DO YOU DO. PLEASE STATE YOUR PROBLEM" },
        { "what kind of computer flew to the moon",
          "DO COMPUTERS WORRY YOU" },
        { "You have the soul of a new machine.",
          "WHY DO YOU MENTION COMPUTERS" },
        { "Do you think we will find a cybernetic ecology where we are all watched over by machines of loving grace?",
          "WHAT DO YOU THINK MACHINES HAVE TO DO WITH YOUR PROBLEM" },
        { "Pablo Picasso said \"Computers are useless. They can only give you answers.\"",
          "DON'T YOU THINK COMPUTERS CAN HELP PEOPLE" },
        { "Am I a lost cause?",
          "DO YOU BELIEVE YOU ARE A LOST CAUSE" },
        { "Never am, no.",
          "WHY DO YOU SAY 'AM'" },
        { "Are you mad?",
          "WHY ARE YOU INTERESTED IN WHETHER I AM MAD OR NOT" },
        { "Humans eh? Are we nuts?",
          "DID YOU THINK THEY MIGHT NOT BE WE NUTS" },
        { "Your words are starting to annoy me.",
          "WHY ARE YOU CONCERNED OVER MY WORDS ARE STARTING TO ANNOY YOU" },
        { "Was I wrong to speak my mind?",
          "WHAT IF YOU WERE WRONG TO SPEAK YOUR MIND" },
        { "I was telling you about my crazy idea",
          "WERE YOU REALLY" },
        { "That was you trying to make me feel better?",
          "WOULD YOU LIKE TO BELIEVE I WAS TRYING TO MAKE YOU FEEL BETTER" },
        { "That was the problem we had to solve when we found out.",
          "WHAT IS IT YOU REALLY WANT TO KNOW" },
        { "Were you going to tell me how to feel better about myself?",
          "WHAT SUGGESTS THAT I WAS GOING TO TELL YOU HOW TO FEEL BETTER ABOUT YOURSELF" },
        { "You're mad at me",
          "WHAT MAKES YOU THINK I AM MAD AT YOU" },
        { "I'm a good girl, I am.",
          "IS IT BECAUSE YOU ARE A GOOD GIRL THAT YOU CAME TO ME" },
        { "I need to understand why I'm unhappy",
          "WHAT WOULD IT MEAN TO YOU IF YOU GOT TO UNDERSTAND WHY YOU'RE UNHAPPY" },
        { "I know I am sick in the head",
          "I AM SORRY TO HEAR YOU ARE SICK" },
        { "I am not a happy bunny",
          "HOW HAVE I HELPED YOU TO BE HAPPY" },
        { "I were flummoxed",
          "WHY DO YOU TELL ME YOU WERE FLUMMOXED NOW" },
        { "I think I should go.",
          "DO YOU REALLY THINK SO" },
        { "I feel you understand me.",
          "WHY DO YOU THINK I UNDERSTAND YOU" },
        { "I am so lonely now.",
          "HOW LONG HAVE YOU BEEN SO LONELY NOW" },
        { "I cannot believe he really loves me.",
          "HOW DO YOU KNOW YOU CAN'T BELIEVE HE REALLY LOVES YOU" },
        { "I don't get out much now I'm old.",
          "DON'T YOU REALLY GET OUT MUCH NOW YOU'RE OLD" },
        { "I feel lost",
          "TELL ME MORE ABOUT SUCH FEELINGS" },
        { "I hate you",
          "PERHAPS IN YOUR FANTASY WE HATE EACH OTHER" },
        { "I can talk the hind leg off a donkey.",
          "YOU SAY YOU CAN TALK THE HIND LEG OFF A DONKEY" },
        { "You remind me of the old days.",
          "WHAT DOES THAT SIMILARITY SUGGEST TO YOU" },
        { "You are wrong about that!",
          "DOES IT PLEASE YOU TO BELIEVE I AM WRONG ABOUT THAT" },
        { "Clearly you hate me.",
          "YOU LIKE TO THINK I HATE YOU - DON'T YOU" },
        { "You failed to grasp the nettle.",
          "WE WERE DISCUSSING YOU - NOT ME" },
        { "Yes, I think so.",
          "YOU ARE SURE" },
        { "No, I don't want to go out with you.",
          "ARE YOU SAYING 'NO' JUST TO BE NEGATIVE" },
        { "My brother ate my hamster.",
          "TELL ME MORE ABOUT YOUR FAMILY" },
        { "Oh my head hurts!",
          "YOUR HEAD HURTS" },
        { "Can you believe it!",
          "YOU BELIEVE I CAN BELIEVE IT DON'T YOU" },
        { "Can I have a glass of water?",
          "WHETHER OR NOT YOU CAN HAVE A GLASS OF WATER DEPENDS ON YOU MORE THAN ON ME" },
        { "What an idiot.",
          "ARE SUCH QUESTIONS MUCH ON YOUR MIND" },
        { "Because then she would know I loved her.",
          "IS THAT THE REAL REASON" },
        { "Why don't you just switch off your television set and go and do something less boring instead?",
          "DO YOU BELIEVE I DON'T JUST SWITCH OFF MY TELEVISION SET AND GO AND DO SOMETHING LESS BORING INSTEAD" },
        { "why cant i eat cookies in bed",
          "DO YOU THINK YOU SHOULD BE ABLE TO EAT COOKIES IN BED" },
        { "why can't people get along?",
          "WHAT ANSWER WOULD PLEASE YOU MOST" },
        { "Everyone can get lost!",
          "REALLY, EVERYONE" },
        { "Everybody hates me.",
          "SURELY NOT EVERYBODY" },
        { "Nobody loves me.",
          "CAN YOU THINK OF ANYONE IN PARTICULAR" },
        { "Noone cares",
          "WHO, FOR EXAMPLE" },
        { "The postman always rings twice.",
          "CAN YOU THINK OF A SPECIFIC EXAMPLE" },
        { "She was not like the others.",
          "WHAT OTHER CONNECTIONS DO YOU SEE" },
        { "she wasn't like you",
          "OH, I" }
    };

static void test_memory_hash_routes(void) {
  static const struct exchange memory_routes[][3] = {
    {
      {"MY BIKE ENDS TIME", "YOUR BIKE ENDS TIME"},
      {"ZQXV", "I AM NOT SURE I UNDERSTAND YOU FULLY"},
      {"QWER", "LETS DISCUSS FURTHER WHY YOUR BIKE ENDS TIME"}
    },
    {
      {"MY BIKE ENDS KIDS", "YOUR BIKE ENDS KIDS"},
      {"ZQXV", "I AM NOT SURE I UNDERSTAND YOU FULLY"},
      {"QWER", "EARLIER YOU SAID YOUR BIKE ENDS KIDS"}
    },
    {
      {"MY BIKE ENDS GLOUCESTERSHIRE", "YOUR BIKE ENDS GLOUCESTERSHIRE"},
      {"ZQXV", "I AM NOT SURE I UNDERSTAND YOU FULLY"},
      {"QWER", "BUT YOUR BIKE ENDS GLOUCESTERSHIRE"}
    },
    {
      {"MY BIKE ENDS HERE", "YOUR BIKE ENDS HERE"},
      {"ZQXV", "I AM NOT SURE I UNDERSTAND YOU FULLY"},
      {"QWER", "DOES THAT HAVE ANYTHING TO DO WITH THE FACT THAT YOUR BIKE ENDS HERE"}
    }
  };
  size_t index;
  for(index = 0; index < sizeof(memory_routes) / sizeof(memory_routes[0]);
      ++index)
    run_transcript(memory_routes[index],
                   sizeof(memory_routes[index]) /
                       sizeof(memory_routes[index][0]));
}

static void test_rotation(void) {
  static const struct exchange transcript[] = {
    {"SORRY", "PLEASE DON'T APOLIGIZE"},
    {"SORRY", "APOLOGIES ARE NOT NECESSARY"},
    {"SORRY", "WHAT FEELINGS DO YOU HAVE WHEN YOU APOLOGIZE"},
    {"SORRY", "I'VE TOLD YOU THAT APOLOGIES ARE NOT REQUIRED"},
    {"SORRY", "PLEASE DON'T APOLIGIZE"}
  };
  run_transcript(transcript, sizeof(transcript) / sizeof(transcript[0]));
}

static void test_memory_fifo_arena(void) {
  enum { MEMORY_COUNT = 256 };
  eliza_state state;
  uint8_t memory[ELIZA_MEMORY_WORKSPACE_BYTES];
  char input[ELIZA_INPUT_BYTES];
  char expected[ELIZA_REPLY_BYTES];
  char output[ELIZA_REPLY_BYTES];
  unsigned index;
  eliza_init(&state, memory, sizeof(memory));

  for(index = 0; index < MEMORY_COUNT; ++index) {
    snprintf(input, sizeof(input), "MY MEMORY NUMBER %u ENDS HERE", index);
    eliza_reply(&state, input, output, sizeof(output));
  }
  assert(state.memory_used != 0);

  for(index = 0; index < MEMORY_COUNT; ++index) {
    const size_t before = state.memory_used;
    unsigned attempts = 0;
    assert(before != 0);
    do {
      eliza_reply(&state, "ZQXV", output, sizeof(output));
      ++attempts;
    } while(state.memory_used == before && attempts < 4);
    assert(state.memory_used < before);
    snprintf(expected, sizeof(expected),
             "DOES THAT HAVE ANYTHING TO DO WITH THE FACT THAT YOUR "
             "MEMORY NUMBER %u ENDS HERE", index);
    assert(strcmp(output, expected) == 0);
  }
  assert(state.memory_used == 0);
}

static void test_long_input(void) {
  eliza_state state;
  uint8_t memory[ELIZA_MEMORY_WORKSPACE_BYTES];
  char input[ELIZA_INPUT_BYTES];
  char expected[ELIZA_REPLY_BYTES];
  char output[ELIZA_REPLY_BYTES];
  size_t index;

  strcpy(input, "I WANT");
  strcpy(expected, "WHAT WOULD IT MEAN TO YOU IF YOU GOT");
  for(index = 0; index < 252; ++index) {
    strcat(input, " I");
    strcat(expected, " YOU");
  }
  assert(strlen(input) > 95);
  assert(strlen(input) + 1 < sizeof(input));
  assert(strlen(expected) + 1 < sizeof(expected));
  eliza_init(&state, memory, sizeof(memory));
  eliza_reply(&state, input, output, sizeof(output));
  assert(strcmp(output, expected) == 0);

  input[0] = 0;
  for(index = 0; index < 240; ++index) strcat(input, "X,");
  strcat(input, "I WANT HELP");
  assert(strlen(input) + 1 < sizeof(input));
  eliza_init(&state, memory, sizeof(memory));
  eliza_reply(&state, input, output, sizeof(output));
  assert(strcmp(output, "WHAT WOULD IT MEAN TO YOU IF YOU GOT HELP") == 0);
}

static void test_goodbye_and_bounds(void) {
  eliza_state state;
  uint8_t memory[ELIZA_MEMORY_WORKSPACE_BYTES];
  struct {
    char output[12];
    unsigned char guard;
  } bounded = {{0}, 0xA5};

  assert(eliza_is_goodbye("bye"));
  assert(eliza_is_goodbye("  Good-bye! "));
  assert(eliza_is_goodbye("QUIT."));
  assert(!eliza_is_goodbye("goodbye for now"));

  eliza_init(&state, memory, sizeof(memory));
  eliza_reply(&state, "I want an extraordinarily long reply", bounded.output,
              sizeof(bounded.output));
  assert(bounded.output[sizeof(bounded.output) - 1] == 0);
  assert(bounded.guard == 0xA5);
}

int main(void) {
  run_transcript(CACM_CONVERSATION,
                 sizeof(CACM_CONVERSATION) / sizeof(CACM_CONVERSATION[0]));
  run_transcript(REFERENCE_COVERAGE,
                 sizeof(REFERENCE_COVERAGE) / sizeof(REFERENCE_COVERAGE[0]));
  test_memory_hash_routes();
  test_rotation();
  test_memory_fifo_arena();
  test_long_input();
  test_goodbye_and_bounds();
  puts("exact ELIZA/DOCTOR engine tests passed");
  return 0;
}
