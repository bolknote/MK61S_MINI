#include "eliza_engine.h"

/*
 * Compact, fixed-script ELIZA/DOCTOR engine for a freestanding target.
 * It keeps the important mechanisms of the 1966 script: ranked keywords,
 * decomposition tails, rotating reassemblies, pronoun reflection and memory.
 */

#define ARRAY_COUNT(a) ((uint8_t) (sizeof(a) / sizeof((a)[0])))

enum response_set_id {
  RS_EMPTY,
  RS_REPEAT,
  RS_COMPUTER,
  RS_NAME,
  RS_SORRY,
  RS_REMEMBER,
  RS_REMEMBER_ME,
  RS_DREAMED,
  RS_DREAM,
  RS_HELLO,
  RS_IF,
  RS_I_WANT,
  RS_I_SAD,
  RS_I_HAPPY,
  RS_I_WAS,
  RS_I_AM,
  RS_I_CANT,
  RS_I_DONT,
  RS_I_FEEL,
  RS_I_BELIEVE,
  RS_I_GENERIC,
  RS_YOU_ARE,
  RS_YOU_ME,
  RS_YOU_GENERIC,
  RS_MY_FAMILY,
  RS_MY,
  RS_CAN_YOU,
  RS_CAN_I,
  RS_WHY_DONT_YOU,
  RS_WHY_CANT_I,
  RS_QUESTION,
  RS_BECAUSE,
  RS_PERHAPS,
  RS_YES,
  RS_NO,
  RS_EVERYONE,
  RS_ALWAYS,
  RS_LIKE,
  RS_FOREIGN,
  RS_MEMORY,
  RS_NONE
};

/* Keep this assertion independent of C11 so the host and APP builds agree. */
typedef char response_set_count_must_match[
    RS_NONE + 1 == ELIZA_RESPONSE_SET_COUNT ? 1 : -1];

typedef struct response_set {
  const char* const* item;
  uint8_t count;
} response_set;

static const char* const RESP_EMPTY[] = {
  "PLEASE SAY SOMETHING.",
  "WHAT WOULD YOU LIKE TO DISCUSS?"
};
static const char* const RESP_REPEAT[] = {
  "PLEASE DON'T REPEAT YOURSELF.",
  "YOU ARE REPEATING YOURSELF.",
  "WHY DID YOU SAY THAT AGAIN?"
};
static const char* const RESP_COMPUTER[] = {
  "DO COMPUTERS WORRY YOU?",
  "WHY DO YOU MENTION COMPUTERS?",
  "WHAT DO MACHINES HAVE TO DO WITH YOUR PROBLEM?",
  "DON'T YOU THINK COMPUTERS CAN HELP PEOPLE?"
};
static const char* const RESP_NAME[] = {
  "I AM NOT INTERESTED IN NAMES.",
  "I DON'T CARE ABOUT NAMES. PLEASE CONTINUE."
};
static const char* const RESP_SORRY[] = {
  "PLEASE DON'T APOLOGIZE.",
  "APOLOGIES ARE NOT NECESSARY.",
  "WHAT FEELINGS DO YOU HAVE WHEN YOU APOLOGIZE?"
};
static const char* const RESP_REMEMBER[] = {
  "DO YOU OFTEN THINK OF %?",
  "DOES THINKING OF % BRING ANYTHING ELSE TO MIND?",
  "WHY DO YOU REMEMBER % JUST NOW?",
  "WHAT IN THE PRESENT SITUATION REMINDS YOU OF %?"
};
static const char* const RESP_REMEMBER_ME[] = {
  "DID YOU THINK I WOULD FORGET %?",
  "WHY DO YOU THINK I SHOULD RECALL % NOW?",
  "WHAT ABOUT %?",
  "YOU MENTIONED %."
};
static const char* const RESP_DREAMED[] = {
  "REALLY, %?",
  "HAVE YOU EVER FANTASIED % WHILE YOU WERE AWAKE?",
  "HAVE YOU DREAMED % BEFORE?"
};
static const char* const RESP_DREAM[] = {
  "WHAT DOES THAT DREAM SUGGEST TO YOU?",
  "DO YOU DREAM OFTEN?",
  "WHAT PERSONS APPEAR IN YOUR DREAMS?",
  "DOES THAT DREAM HAVE SOMETHING TO DO WITH YOUR PROBLEM?"
};
static const char* const RESP_HELLO[] = {
  "HOW DO YOU DO. PLEASE STATE YOUR PROBLEM."
};
static const char* const RESP_IF[] = {
  "DO YOU THINK IT IS LIKELY THAT %?",
  "DO YOU WISH THAT %?",
  "WHAT DO YOU THINK ABOUT %?",
  "REALLY, IF %?"
};
static const char* const RESP_I_WANT[] = {
  "WHAT WOULD IT MEAN TO YOU IF YOU GOT %?",
  "WHY DO YOU WANT %?",
  "SUPPOSE YOU GOT % SOON.",
  "WHAT IF YOU NEVER GOT %?"
};
static const char* const RESP_I_SAD[] = {
  "I AM SORRY TO HEAR YOU ARE %.",
  "DO YOU THINK COMING HERE WILL HELP YOU NOT TO BE %?",
  "I'M SURE IT IS NOT PLEASANT TO BE %.",
  "CAN YOU EXPLAIN WHAT MADE YOU %?"
};
static const char* const RESP_I_HAPPY[] = {
  "HOW HAVE I HELPED YOU TO BE %?",
  "WHAT MAKES YOU % JUST NOW?",
  "CAN YOU EXPLAIN WHY YOU ARE SUDDENLY %?"
};
static const char* const RESP_I_WAS[] = {
  "WERE YOU REALLY %?",
  "WHY DO YOU TELL ME YOU WERE % NOW?",
  "WHAT WOULD IT MEAN IF YOU WERE %?"
};
static const char* const RESP_I_AM[] = {
  "IS IT BECAUSE YOU ARE % THAT YOU CAME TO ME?",
  "HOW LONG HAVE YOU BEEN %?",
  "DO YOU BELIEVE IT IS NORMAL TO BE %?",
  "DO YOU ENJOY BEING %?"
};
static const char* const RESP_I_CANT[] = {
  "HOW DO YOU KNOW YOU CAN'T %?",
  "HAVE YOU TRIED?",
  "PERHAPS YOU COULD % NOW.",
  "DO YOU REALLY WANT TO BE ABLE TO %?"
};
static const char* const RESP_I_DONT[] = {
  "DON'T YOU REALLY %?",
  "WHY DON'T YOU %?",
  "DO YOU WISH TO BE ABLE TO %?",
  "DOES THAT TROUBLE YOU?"
};
static const char* const RESP_I_FEEL[] = {
  "TELL ME MORE ABOUT SUCH FEELINGS.",
  "DO YOU OFTEN FEEL %?",
  "DO YOU ENJOY FEELING %?",
  "OF WHAT DOES FEELING % REMIND YOU?"
};
static const char* const RESP_I_BELIEVE[] = {
  "DO YOU REALLY THINK SO?",
  "BUT YOU ARE NOT SURE YOU %.",
  "DO YOU REALLY DOUBT YOU %?"
};
static const char* const RESP_I_GENERIC[] = {
  "YOU SAY %.",
  "CAN YOU ELABORATE ON THAT?",
  "DO YOU SAY % FOR SOME SPECIAL REASON?",
  "THAT IS QUITE INTERESTING."
};
static const char* const RESP_YOU_ARE[] = {
  "WHAT MAKES YOU THINK I AM %?",
  "DOES IT PLEASE YOU TO BELIEVE I AM %?",
  "DO YOU SOMETIMES WISH YOU WERE %?",
  "PERHAPS YOU WOULD LIKE TO BE %."
};
static const char* const RESP_YOU_ME[] = {
  "WHY DO YOU THINK I % YOU?",
  "WHAT MAKES YOU THINK I % YOU?",
  "DO YOU WISH TO BELIEVE I % YOU?",
  "SUPPOSE I DID % YOU. WHAT WOULD THAT MEAN?"
};
static const char* const RESP_YOU_GENERIC[] = {
  "WE WERE DISCUSSING YOU, NOT ME.",
  "OH, I %?",
  "YOU'RE NOT REALLY TALKING ABOUT ME, ARE YOU?",
  "WHAT ARE YOUR FEELINGS NOW?"
};
static const char* const RESP_MY_FAMILY[] = {
  "TELL ME MORE ABOUT YOUR FAMILY.",
  "WHO ELSE IN YOUR FAMILY %?",
  "WHAT ELSE COMES TO MIND WHEN YOU THINK OF YOUR FAMILY?"
};
static const char* const RESP_MY[] = {
  "YOUR %?",
  "WHY DO YOU SAY YOUR %?",
  "DOES THAT SUGGEST ANYTHING ELSE WHICH BELONGS TO YOU?",
  "IS IT IMPORTANT TO YOU THAT YOUR %?"
};
static const char* const RESP_CAN_YOU[] = {
  "YOU BELIEVE I CAN %, DON'T YOU?",
  "YOU WANT ME TO BE ABLE TO %?",
  "PERHAPS YOU WOULD LIKE TO BE ABLE TO % YOURSELF."
};
static const char* const RESP_CAN_I[] = {
  "WHETHER OR NOT YOU CAN % DEPENDS ON YOU MORE THAN ON ME.",
  "DO YOU WANT TO BE ABLE TO %?",
  "PERHAPS YOU DON'T WANT TO %."
};
static const char* const RESP_WHY_DONT_YOU[] = {
  "DO YOU BELIEVE I DON'T %?",
  "PERHAPS I WILL % IN GOOD TIME.",
  "SHOULD YOU % YOURSELF?",
  "YOU WANT ME TO %?"
};
static const char* const RESP_WHY_CANT_I[] = {
  "DO YOU THINK YOU SHOULD BE ABLE TO %?",
  "DO YOU WANT TO BE ABLE TO %?",
  "HAVE YOU ANY IDEA WHY YOU CAN'T %?"
};
static const char* const RESP_QUESTION[] = {
  "WHY DO YOU ASK?",
  "DOES THAT QUESTION INTEREST YOU?",
  "WHAT IS IT YOU REALLY WANT TO KNOW?",
  "WHAT ANSWER WOULD PLEASE YOU MOST?",
  "WHAT DO YOU THINK?"
};
static const char* const RESP_BECAUSE[] = {
  "IS THAT THE REAL REASON?",
  "DON'T ANY OTHER REASONS COME TO MIND?",
  "DOES THAT REASON EXPLAIN ANYTHING ELSE?",
  "WHAT OTHER REASONS MIGHT THERE BE?"
};
static const char* const RESP_PERHAPS[] = {
  "YOU DON'T SEEM QUITE CERTAIN.",
  "WHY THE UNCERTAIN TONE?",
  "CAN'T YOU BE MORE POSITIVE?",
  "YOU AREN'T SURE?"
};
static const char* const RESP_YES[] = {
  "YOU SEEM QUITE POSITIVE.",
  "YOU ARE SURE.",
  "I SEE.",
  "I UNDERSTAND."
};
static const char* const RESP_NO[] = {
  "ARE YOU SAYING NO JUST TO BE NEGATIVE?",
  "YOU ARE BEING A BIT NEGATIVE.",
  "WHY NOT?",
  "WHY NO?"
};
static const char* const RESP_EVERYONE[] = {
  "REALLY, %?",
  "SURELY NOT %.",
  "CAN YOU THINK OF ANYONE IN PARTICULAR?",
  "WHO, FOR EXAMPLE?",
  "YOU HAVE A PARTICULAR PERSON IN MIND, DON'T YOU?"
};
static const char* const RESP_ALWAYS[] = {
  "CAN YOU THINK OF A SPECIFIC EXAMPLE?",
  "WHEN?",
  "WHAT INCIDENT ARE YOU THINKING OF?",
  "REALLY, ALWAYS?"
};
static const char* const RESP_LIKE[] = {
  "IN WHAT WAY?",
  "WHAT RESEMBLANCE DO YOU SEE?",
  "WHAT DOES THAT SIMILARITY SUGGEST TO YOU?",
  "WHAT OTHER CONNECTIONS DO YOU SEE?"
};
static const char* const RESP_FOREIGN[] = {
  "I AM SORRY, I SPEAK ONLY ENGLISH."
};
static const char* const RESP_MEMORY[] = {
  "LET'S DISCUSS FURTHER WHY YOUR %.",
  "EARLIER YOU SAID YOUR %.",
  "BUT YOUR %?",
  "DOES THAT HAVE ANYTHING TO DO WITH YOUR %?"
};
static const char* const RESP_NONE[] = {
  "I AM NOT SURE I UNDERSTAND YOU FULLY.",
  "PLEASE GO ON.",
  "WHAT DOES THAT SUGGEST TO YOU?",
  "DO YOU FEEL STRONGLY ABOUT DISCUSSING SUCH THINGS?"
};

#define RESPONSE_SET(name) {name, ARRAY_COUNT(name)}
static const response_set RESPONSE_SETS[ELIZA_RESPONSE_SET_COUNT] = {
  RESPONSE_SET(RESP_EMPTY),
  RESPONSE_SET(RESP_REPEAT),
  RESPONSE_SET(RESP_COMPUTER),
  RESPONSE_SET(RESP_NAME),
  RESPONSE_SET(RESP_SORRY),
  RESPONSE_SET(RESP_REMEMBER),
  RESPONSE_SET(RESP_REMEMBER_ME),
  RESPONSE_SET(RESP_DREAMED),
  RESPONSE_SET(RESP_DREAM),
  RESPONSE_SET(RESP_HELLO),
  RESPONSE_SET(RESP_IF),
  RESPONSE_SET(RESP_I_WANT),
  RESPONSE_SET(RESP_I_SAD),
  RESPONSE_SET(RESP_I_HAPPY),
  RESPONSE_SET(RESP_I_WAS),
  RESPONSE_SET(RESP_I_AM),
  RESPONSE_SET(RESP_I_CANT),
  RESPONSE_SET(RESP_I_DONT),
  RESPONSE_SET(RESP_I_FEEL),
  RESPONSE_SET(RESP_I_BELIEVE),
  RESPONSE_SET(RESP_I_GENERIC),
  RESPONSE_SET(RESP_YOU_ARE),
  RESPONSE_SET(RESP_YOU_ME),
  RESPONSE_SET(RESP_YOU_GENERIC),
  RESPONSE_SET(RESP_MY_FAMILY),
  RESPONSE_SET(RESP_MY),
  RESPONSE_SET(RESP_CAN_YOU),
  RESPONSE_SET(RESP_CAN_I),
  RESPONSE_SET(RESP_WHY_DONT_YOU),
  RESPONSE_SET(RESP_WHY_CANT_I),
  RESPONSE_SET(RESP_QUESTION),
  RESPONSE_SET(RESP_BECAUSE),
  RESPONSE_SET(RESP_PERHAPS),
  RESPONSE_SET(RESP_YES),
  RESPONSE_SET(RESP_NO),
  RESPONSE_SET(RESP_EVERYONE),
  RESPONSE_SET(RESP_ALWAYS),
  RESPONSE_SET(RESP_LIKE),
  RESPONSE_SET(RESP_FOREIGN),
  RESPONSE_SET(RESP_MEMORY),
  RESPONSE_SET(RESP_NONE)
};

static size_t text_length(const char* text) {
  size_t length = 0;
  if(text != NULL) while(text[length] != 0) ++length;
  return length;
}

static int text_equal(const char* a, const char* b) {
  size_t index = 0;
  if(a == NULL || b == NULL) return a == b;
  while(a[index] != 0 && a[index] == b[index]) ++index;
  return a[index] == b[index];
}

static void text_copy(char* output, size_t capacity, const char* input) {
  size_t index = 0;
  if(output == NULL || capacity == 0) return;
  if(input != NULL) {
    while(index + 1 < capacity && input[index] != 0) {
      output[index] = input[index];
      ++index;
    }
  }
  output[index] = 0;
}

static int ascii_letter(char value) {
  return (value >= 'A' && value <= 'Z') || (value >= 'a' && value <= 'z');
}

/* Apostrophes are discarded inside words: I'M, IM and I-M all become IM. */
static void normalize(const char* input, char* output, size_t capacity) {
  size_t used = 0;
  int between_words = 0;
  if(output == NULL || capacity == 0) return;
  if(input == NULL) input = "";
  while(*input != 0) {
    char value = *input++;
    if(ascii_letter(value) || (value >= '0' && value <= '9')) {
      if(between_words && used != 0 && used + 1 < capacity) output[used++] = ' ';
      between_words = 0;
      if(value >= 'a' && value <= 'z') value = (char) (value - 'a' + 'A');
      if(used + 1 < capacity) output[used++] = value;
    } else if(value == '\'' && !between_words) {
      /* Keep both sides of a contraction in one normalized word. */
    } else {
      between_words = used != 0;
    }
  }
  output[used] = 0;
}

static int word_boundary(char value) {
  return value == 0 || value == ' ';
}

static const char* find_phrase(const char* text, const char* phrase) {
  const size_t phrase_length = text_length(phrase);
  const char* candidate = text;
  if(phrase_length == 0) return text;
  while(candidate != NULL && *candidate != 0) {
    size_t index = 0;
    while(index < phrase_length && candidate[index] == phrase[index]) ++index;
    if(index == phrase_length && word_boundary(candidate[index])) return candidate;
    while(*candidate != 0 && *candidate != ' ') ++candidate;
    while(*candidate == ' ') ++candidate;
  }
  return NULL;
}

static int has_phrase(const char* text, const char* phrase) {
  return find_phrase(text, phrase) != NULL;
}

static const char* tail_after(const char* text, const char* phrase) {
  const char* found = find_phrase(text, phrase);
  if(found == NULL) return NULL;
  found += text_length(phrase);
  while(*found == ' ') ++found;
  return *found != 0 ? found : NULL;
}

static const char* tail_after_either(const char* text, const char* first,
                                     const char* second) {
  const char* tail = tail_after(text, first);
  return tail != NULL ? tail : tail_after(text, second);
}

static int starts_with_word(const char* text, const char* word) {
  const size_t length = text_length(word);
  size_t index = 0;
  while(index < length && text[index] == word[index]) ++index;
  return index == length && word_boundary(text[index]);
}

static const char* reflected_word(const char* word, size_t length) {
  struct reflection { const char* from; const char* to; };
  static const struct reflection reflections[] = {
    {"I", "YOU"}, {"ME", "YOU"}, {"MY", "YOUR"},
    {"MINE", "YOURS"}, {"MYSELF", "YOURSELF"},
    {"AM", "ARE"}, {"IM", "YOU ARE"},
    {"YOU", "I"}, {"YOUR", "MY"}, {"YOURS", "MINE"},
    {"YOURSELF", "MYSELF"}, {"ARE", "AM"}, {"YOURE", "I AM"}
  };
  uint8_t index;
  for(index = 0; index < ARRAY_COUNT(reflections); ++index) {
    const char* candidate = reflections[index].from;
    size_t offset = 0;
    while(offset < length && candidate[offset] == word[offset]) ++offset;
    if(offset == length && candidate[offset] == 0) return reflections[index].to;
  }
  return NULL;
}

static void append_char(char* output, size_t capacity, size_t* used, char value) {
  if(*used + 1 < capacity) output[(*used)++] = value;
}

static void append_text(char* output, size_t capacity, size_t* used,
                        const char* text) {
  if(text == NULL) return;
  while(*text != 0) append_char(output, capacity, used, *text++);
}

static void append_reflected(char* output, size_t capacity, size_t* used,
                             const char* text) {
  int need_space = 0;
  while(text != NULL && *text != 0) {
    const char* word;
    size_t length = 0;
    const char* replacement;
    while(*text == ' ') ++text;
    if(*text == 0) break;
    word = text;
    while(text[length] != 0 && text[length] != ' ') ++length;
    replacement = reflected_word(word, length);
    if(need_space) append_char(output, capacity, used, ' ');
    if(replacement != NULL) append_text(output, capacity, used, replacement);
    else {
      size_t index;
      for(index = 0; index < length; ++index)
        append_char(output, capacity, used, word[index]);
    }
    need_space = 1;
    text += length;
  }
}

static void assemble(const char* pattern, const char* capture,
                     char* output, size_t capacity) {
  size_t used = 0;
  if(output == NULL || capacity == 0) return;
  while(pattern != NULL && *pattern != 0) {
    if(*pattern == '%') append_reflected(output, capacity, &used, capture);
    else append_char(output, capacity, &used, *pattern);
    ++pattern;
  }
  output[used] = 0;
}

static void use_response(eliza_state* state, enum response_set_id id,
                         const char* capture, char* output, size_t capacity) {
  const response_set* set = &RESPONSE_SETS[id];
  uint8_t index = state->next_response[id];
  if(index >= set->count) index = 0;
  state->next_response[id] = (uint8_t) (index + 1 == set->count ? 0 : index + 1);
  assemble(set->item[index], capture, output, capacity);
}

static const char* sentiment_tail(const char* text, const char* prefix,
                                  const char* const* words, uint8_t count) {
  const char* tail = tail_after(text, prefix);
  uint8_t index;
  if(tail == NULL) return NULL;
  for(index = 0; index < count; ++index)
    if(has_phrase(tail, words[index])) return tail;
  return NULL;
}

static int has_family_word(const char* text) {
  static const char* const family[] = {
    "MOTHER", "MOM", "FATHER", "DAD", "SISTER", "BROTHER",
    "WIFE", "HUSBAND", "CHILD", "CHILDREN", "FAMILY"
  };
  uint8_t index;
  for(index = 0; index < ARRAY_COUNT(family); ++index)
    if(has_phrase(text, family[index])) return 1;
  return 0;
}

static void remember_my(eliza_state* state, const char* normalized) {
  const char* tail = tail_after(normalized, "MY");
  if(tail == NULL) return;
  text_copy(state->memory, sizeof(state->memory), tail);
  state->memory_pending = 1;
}

void eliza_init(eliza_state* state) {
  size_t index;
  if(state == NULL) return;
  for(index = 0; index < sizeof(*state); ++index)
    ((uint8_t*) state)[index] = 0;
}

int eliza_is_goodbye(const char* input) {
  char normalized[ELIZA_INPUT_BYTES];
  normalize(input, normalized, sizeof(normalized));
  return text_equal(normalized, "BYE") || text_equal(normalized, "GOODBYE") ||
         text_equal(normalized, "GOOD BYE") ||
         text_equal(normalized, "QUIT") || text_equal(normalized, "EXIT");
}

void eliza_reply(eliza_state* state, const char* input,
                 char* output, size_t output_size) {
  static const char* const sad_words[] = {
    "SAD", "UNHAPPY", "DEPRESSED", "SICK", "AFRAID", "LONELY"
  };
  static const char* const happy_words[] = {
    "HAPPY", "ELATED", "GLAD", "BETTER"
  };
  char normalized[ELIZA_INPUT_BYTES];
  const char* capture;
  const char* my_tail;

  if(output == NULL || output_size == 0) return;
  output[0] = 0;
  if(state == NULL) return;
  normalize(input, normalized, sizeof(normalized));

  if(normalized[0] == 0) {
    use_response(state, RS_EMPTY, NULL, output, output_size);
    return;
  }
  if(text_equal(normalized, state->previous)) {
    use_response(state, RS_REPEAT, NULL, output, output_size);
    return;
  }
  text_copy(state->previous, sizeof(state->previous), normalized);
  remember_my(state, normalized);

  /* Highest ranks from the original DOCTOR script come first. */
  if(has_phrase(normalized, "COMPUTER") || has_phrase(normalized, "COMPUTERS") ||
     has_phrase(normalized, "MACHINE") || has_phrase(normalized, "MACHINES")) {
    use_response(state, RS_COMPUTER, NULL, output, output_size); return;
  }
  if(has_phrase(normalized, "NAME")) {
    use_response(state, RS_NAME, NULL, output, output_size); return;
  }
  if(has_phrase(normalized, "ALIKE") || has_phrase(normalized, "SAME") ||
     has_phrase(normalized, "IS LIKE") || has_phrase(normalized, "ARE LIKE") ||
     has_phrase(normalized, "WAS LIKE") || has_phrase(normalized, "AM LIKE")) {
    use_response(state, RS_LIKE, NULL, output, output_size); return;
  }
  capture = tail_after(normalized, "I REMEMBER");
  if(capture != NULL) {
    use_response(state, RS_REMEMBER, capture, output, output_size); return;
  }
  capture = tail_after(normalized, "DO YOU REMEMBER");
  if(capture != NULL) {
    use_response(state, RS_REMEMBER_ME, capture, output, output_size); return;
  }
  capture = tail_after_either(normalized, "I DREAMED", "I DREAMT");
  if(capture != NULL) {
    use_response(state, RS_DREAMED, capture, output, output_size); return;
  }
  if(has_phrase(normalized, "DREAM") || has_phrase(normalized, "DREAMS")) {
    use_response(state, RS_DREAM, NULL, output, output_size); return;
  }
  capture = tail_after(normalized, "IF");
  if(capture != NULL) {
    use_response(state, RS_IF, capture, output, output_size); return;
  }
  if(has_phrase(normalized, "EVERYONE") || has_phrase(normalized, "EVERYBODY") ||
     has_phrase(normalized, "NOBODY") || has_phrase(normalized, "NOONE")) {
    capture = has_phrase(normalized, "NOBODY") ? "NOBODY" : "EVERYONE";
    use_response(state, RS_EVERYONE, capture, output, output_size); return;
  }
  my_tail = tail_after(normalized, "MY");
  if(my_tail != NULL && has_family_word(my_tail)) {
    use_response(state, RS_MY_FAMILY, my_tail, output, output_size); return;
  }
  if(my_tail != NULL) {
    use_response(state, RS_MY, my_tail, output, output_size); return;
  }
  if(has_phrase(normalized, "ALWAYS")) {
    use_response(state, RS_ALWAYS, NULL, output, output_size); return;
  }

  if(has_phrase(normalized, "SORRY")) {
    use_response(state, RS_SORRY, NULL, output, output_size); return;
  }
  if(has_phrase(normalized, "HELLO") || has_phrase(normalized, "HI")) {
    use_response(state, RS_HELLO, NULL, output, output_size); return;
  }
  if(has_phrase(normalized, "DEUTSCH") || has_phrase(normalized, "FRANCAIS") ||
     has_phrase(normalized, "ITALIANO") || has_phrase(normalized, "ESPANOL")) {
    use_response(state, RS_FOREIGN, NULL, output, output_size); return;
  }

  capture = tail_after_either(normalized, "I WANT", "I NEED");
  if(capture != NULL) {
    use_response(state, RS_I_WANT, capture, output, output_size); return;
  }
  capture = sentiment_tail(normalized, "I AM", sad_words, ARRAY_COUNT(sad_words));
  if(capture == NULL)
    capture = sentiment_tail(normalized, "IM", sad_words, ARRAY_COUNT(sad_words));
  if(capture != NULL) {
    use_response(state, RS_I_SAD, capture, output, output_size); return;
  }
  capture = sentiment_tail(normalized, "I AM", happy_words, ARRAY_COUNT(happy_words));
  if(capture == NULL)
    capture = sentiment_tail(normalized, "IM", happy_words, ARRAY_COUNT(happy_words));
  if(capture != NULL) {
    use_response(state, RS_I_HAPPY, capture, output, output_size); return;
  }
  capture = tail_after(normalized, "I WAS");
  if(capture != NULL) {
    use_response(state, RS_I_WAS, capture, output, output_size); return;
  }
  capture = tail_after_either(normalized, "I AM", "IM");
  if(capture != NULL) {
    use_response(state, RS_I_AM, capture, output, output_size); return;
  }
  capture = tail_after_either(normalized, "I CANT", "I CANNOT");
  if(capture != NULL) {
    use_response(state, RS_I_CANT, capture, output, output_size); return;
  }
  capture = tail_after(normalized, "I DONT");
  if(capture != NULL) {
    use_response(state, RS_I_DONT, capture, output, output_size); return;
  }
  capture = tail_after(normalized, "I FEEL");
  if(capture != NULL) {
    use_response(state, RS_I_FEEL, capture, output, output_size); return;
  }
  capture = tail_after(normalized, "I THINK");
  if(capture == NULL) capture = tail_after(normalized, "I BELIEVE");
  if(capture == NULL) capture = tail_after(normalized, "I WISH");
  if(capture != NULL) {
    use_response(state, RS_I_BELIEVE, capture, output, output_size); return;
  }

  capture = tail_after(normalized, "WHY DONT YOU");
  if(capture != NULL) {
    use_response(state, RS_WHY_DONT_YOU, capture, output, output_size); return;
  }
  capture = tail_after(normalized, "WHY CANT I");
  if(capture != NULL) {
    use_response(state, RS_WHY_CANT_I, capture, output, output_size); return;
  }
  capture = tail_after(normalized, "CAN YOU");
  if(capture != NULL) {
    use_response(state, RS_CAN_YOU, capture, output, output_size); return;
  }
  capture = tail_after(normalized, "CAN I");
  if(capture != NULL) {
    use_response(state, RS_CAN_I, capture, output, output_size); return;
  }
  if(has_phrase(normalized, "WHAT") || has_phrase(normalized, "HOW") ||
     has_phrase(normalized, "WHEN") || has_phrase(normalized, "WHY")) {
    use_response(state, RS_QUESTION, NULL, output, output_size); return;
  }
  if(has_phrase(normalized, "BECAUSE")) {
    use_response(state, RS_BECAUSE, NULL, output, output_size); return;
  }
  if(has_phrase(normalized, "PERHAPS") || has_phrase(normalized, "MAYBE")) {
    use_response(state, RS_PERHAPS, NULL, output, output_size); return;
  }
  if(has_phrase(normalized, "YES") || has_phrase(normalized, "CERTAINLY")) {
    use_response(state, RS_YES, NULL, output, output_size); return;
  }
  if(has_phrase(normalized, "NO")) {
    use_response(state, RS_NO, NULL, output, output_size); return;
  }

  capture = tail_after_either(normalized, "YOU ARE", "YOURE");
  if(capture != NULL) {
    use_response(state, RS_YOU_ARE, capture, output, output_size); return;
  }
  if(starts_with_word(normalized, "YOU") && has_phrase(normalized, "ME")) {
    const char* after_you = tail_after(normalized, "YOU");
    size_t length = 0;
    while(after_you != NULL && after_you[length] != 0) ++length;
    while(length != 0 && after_you[length - 1] == ' ') --length;
    if(length >= 3 && after_you[length - 3] == ' ' &&
       after_you[length - 2] == 'M' && after_you[length - 1] == 'E') {
      char verb[ELIZA_INPUT_BYTES];
      size_t index;
      length -= 3;
      for(index = 0; index < length && index + 1 < sizeof(verb); ++index)
        verb[index] = after_you[index];
      verb[index] = 0;
      if(verb[0] != 0) {
        use_response(state, RS_YOU_ME, verb, output, output_size); return;
      }
    }
  }
  capture = tail_after(normalized, "YOU");
  if(capture != NULL) {
    use_response(state, RS_YOU_GENERIC, capture, output, output_size); return;
  }
  if(starts_with_word(normalized, "I")) {
    use_response(state, RS_I_GENERIC, normalized, output, output_size); return;
  }

  if(state->memory_pending && state->memory[0] != 0) {
    state->memory_pending = 0;
    use_response(state, RS_MEMORY, state->memory, output, output_size); return;
  }
  use_response(state, RS_NONE, NULL, output, output_size);
}
