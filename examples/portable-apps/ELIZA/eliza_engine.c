#include "eliza_engine.h"

/*
 * Compact interpreter for Joseph Weizenbaum's 1966 CACM DOCTOR script.
 *
 * The script is compiled by tools/generate_eliza_doctor.py. Runtime rule
 * semantics follow the recovered MAD-SLIP ELIZA: ranked keyword stacks,
 * word substitution, decomposition/reassembly, =KEY, NEWKEY, PRE, DLIST,
 * rotating responses, the LIMIT counter, and the Hollerith memory hash.
 */

#define ELIZA_NO_ID 255U
#define ELIZA_MAX_WORDS 256U
#define ELIZA_MAX_PATTERN_TERMS 9U
#define ELIZA_MEMORY_HEADER_BYTES 3U

enum pattern_opcode {
  PATTERN_COUNT = 1,
  PATTERN_WORD = 2,
  PATTERN_ANY = 3,
  PATTERN_TAG = 4
};

enum reassembly_opcode {
  REASSEMBLY_TEXT = 0,
  REASSEMBLY_LINK = 1,
  REASSEMBLY_NEWKEY = 2,
  REASSEMBLY_PRE = 3
};

enum action {
  ACTION_INAPPLICABLE,
  ACTION_COMPLETE,
  ACTION_NEWKEY,
  ACTION_LINK
};

enum token_id {
  TOKEN_DELIMITER = 254,
  TOKEN_UNKNOWN = 255
};

typedef struct ElizaRuleData {
  uint8_t substitute;
  uint8_t rank;
  uint8_t first_transform;
  uint8_t transform_count;
  uint8_t link;
} ElizaRuleData;

typedef struct ElizaTransformData {
  uint16_t pattern_offset;
  uint16_t first_reassembly;
  uint8_t pattern_size;
  uint8_t reassembly_count;
} ElizaTransformData;

typedef struct ElizaToken {
  uint8_t word;
  uint16_t offset;
  uint16_t length;
} ElizaToken;

typedef struct ElizaCapture {
  uint16_t start;
  uint16_t count;
} ElizaCapture;

#include "eliza_doctor_data.inc"

typedef char transform_slot_count_must_match[
    ELIZA_SCRIPT_TRANSFORM_COUNT == ELIZA_TRANSFORM_SLOTS ? 1 : -1];
typedef char word_ids_must_not_overlap_special_tokens[
    ELIZA_SCRIPT_WORD_COUNT < TOKEN_DELIMITER ? 1 : -1];

static int rule_has_transformation(const ElizaRuleData* rule) {
  return rule->transform_count != 0 || rule->link != ELIZA_NO_ID;
}

static int word_triggers_rule(uint8_t word) {
  const uint8_t rule_id = word < ELIZA_SCRIPT_WORD_COUNT ?
      eliza_script_word_rules[word] : ELIZA_NO_ID;
  return rule_id != ELIZA_NO_ID &&
      rule_has_transformation(&eliza_script_rules[rule_id]);
}

static size_t string_length(const char* text) {
  size_t length = 0;
  if(text != NULL) while(text[length] != 0) ++length;
  return length;
}

static void copy_text(char* output, size_t capacity, const char* input) {
  size_t used = 0;
  if(output == NULL || capacity == 0) return;
  if(input != NULL) {
    while(used + 1 < capacity && input[used] != 0) {
      output[used] = input[used];
      ++used;
    }
  }
  output[used] = 0;
}

static const char* word_text(uint8_t word) {
  return &eliza_script_word_pool[eliza_script_word_offsets[word]];
}

static uint8_t find_word(const char* text, size_t length) {
  uint8_t word;
  for(word = 0; word < ELIZA_SCRIPT_WORD_COUNT; ++word) {
    size_t index;
    if(eliza_script_word_lengths[word] != length) continue;
    for(index = 0; index < length; ++index)
      if(word_text(word)[index] != text[index]) break;
    if(index == length) return word;
  }
  return TOKEN_UNKNOWN;
}

static int word_character(unsigned char value) {
  return (value >= 'A' && value <= 'Z') ||
         (value >= '0' && value <= '9') || value == '\'' || value == '-' ||
         value == '+' || value == '$' || value == '/' || value == '=' ||
         value == '*' || value == '(' || value == ')';
}

static int finish_input_word(ElizaToken* words, uint16_t* word_count,
                             const char* normalized, uint16_t start,
                             uint16_t length) {
  ElizaToken* token;
  if(length == 0 || *word_count >= ELIZA_MAX_WORDS) return -1;
  token = &words[(*word_count)++];
  token->word = find_word(normalized + start, length);
  token->offset = start;
  token->length = length;
  return token->word;
}

static uint16_t parse_input(const char* input, char* normalized,
                            ElizaToken* words, int select_clause) {
  const unsigned char* cursor =
      (const unsigned char*) (input != NULL ? input : "");
  uint16_t word_count = 0;
  uint16_t used = 0;
  uint16_t word_start = 0;
  uint16_t word_length = 0;
  int clause_has_keyword = 0;

  while(*cursor != 0 && word_count < ELIZA_MAX_WORDS) {
    unsigned char value = *cursor++;

    /* Accept the typographic apostrophe commonly pasted in I'M/DON'T. */
    if(value == 0xe2U && cursor[0] == 0x80U && cursor[1] == 0x99U) {
      value = '\'';
      cursor += 2;
    }
    if(value >= 'a' && value <= 'z')
      value = (unsigned char) (value - 'a' + 'A');
    if(value == '?' || value == '!') value = '.';
    else if(value == ':' || value == ';') value = ',';

    if(word_character(value)) {
      if(word_length == 0) word_start = used;
      if(used + 1U < ELIZA_INPUT_BYTES) {
        normalized[used++] = (char) value;
        ++word_length;
      }
      continue;
    }

    {
      const int finished = finish_input_word(
          words, &word_count, normalized, word_start, word_length);
      if(select_clause && finished >= 0) {
        if((uint8_t) finished == ELIZA_SCRIPT_BUT_WORD) {
          --word_count;
          if(clause_has_keyword) {
            word_length = 0;
            break;
          }
          word_count = 0;
        } else if(word_triggers_rule((uint8_t) finished)) {
          clause_has_keyword = 1;
        }
      }
    }
    word_length = 0;
    if(value == ',' || value == '.') {
      if(select_clause) {
        if(clause_has_keyword) break;
        word_count = 0;
      } else if(word_count < ELIZA_MAX_WORDS) {
        words[word_count].word = TOKEN_DELIMITER;
        words[word_count].offset = 0;
        words[word_count].length = 0;
        ++word_count;
      }
    }
  }
  if(word_length != 0) {
    const int finished = finish_input_word(
        words, &word_count, normalized, word_start, word_length);
    if(select_clause && finished >= 0) {
      if((uint8_t) finished == ELIZA_SCRIPT_BUT_WORD) {
        --word_count;
        if(!clause_has_keyword) word_count = 0;
      }
    }
  }
  normalized[used] = 0;
  return word_count;
}

static void token_bytes(const ElizaToken* token, const char* normalized,
                        const char** text, uint16_t* length) {
  if(token->word < ELIZA_SCRIPT_WORD_COUNT) {
    *text = word_text(token->word);
    *length = eliza_script_word_lengths[token->word];
  } else {
    *text = normalized + token->offset;
    *length = token->length;
  }
}

static int token_equals(const ElizaToken* token, const char* normalized,
                        const char* expected) {
  const char* text;
  uint16_t length;
  size_t index;
  const size_t expected_length = string_length(expected);
  if(token->word == TOKEN_DELIMITER) return 0;
  token_bytes(token, normalized, &text, &length);
  if(length != expected_length) return 0;
  for(index = 0; index < expected_length; ++index)
    if(text[index] != expected[index]) return 0;
  return 1;
}

static void remove_word_prefix(ElizaToken* words, uint16_t* count,
                               uint16_t remove_count) {
  uint16_t index;
  if(remove_count >= *count) {
    *count = 0;
    return;
  }
  for(index = remove_count; index < *count; ++index)
    words[index - remove_count] = words[index];
  *count = (uint16_t) (*count - remove_count);
}

static void stack_push_front(uint8_t* stack, uint16_t* count, uint8_t value) {
  uint16_t index;
  if(*count >= ELIZA_MAX_WORDS) return;
  for(index = *count; index != 0; --index) stack[index] = stack[index - 1U];
  stack[0] = value;
  ++*count;
}

static void stack_push_back(uint8_t* stack, uint16_t* count, uint8_t value) {
  if(*count < ELIZA_MAX_WORDS) stack[(*count)++] = value;
}

static uint8_t stack_pop_front(uint8_t* stack, uint16_t* count) {
  uint16_t index;
  const uint8_t value = stack[0];
  for(index = 1; index < *count; ++index) stack[index - 1U] = stack[index];
  --*count;
  return value;
}

static void scan_keywords(ElizaToken* words, uint16_t* word_count,
                          uint8_t* stack, uint16_t* stack_count) {
  uint8_t top_rank = 0;
  uint16_t index = 0;

  *stack_count = 0;
  while(index < *word_count) {
    ElizaToken* token = &words[index];
    if(token->word == TOKEN_DELIMITER ||
       token->word == ELIZA_SCRIPT_BUT_WORD) {
      if(*stack_count == 0) {
        remove_word_prefix(words, word_count, (uint16_t) (index + 1U));
        index = 0;
        continue;
      }
      *word_count = index;
      break;
    }

    if(token->word < ELIZA_SCRIPT_WORD_COUNT) {
      const uint8_t rule_id = eliza_script_word_rules[token->word];
      if(rule_id != ELIZA_NO_ID) {
        const ElizaRuleData* rule = &eliza_script_rules[rule_id];
        if(rule_has_transformation(rule)) {
          if(rule->rank > top_rank) {
            stack_push_front(stack, stack_count, rule_id);
            top_rank = rule->rank;
          } else {
            stack_push_back(stack, stack_count, rule_id);
          }
        }
        if(rule->substitute != ELIZA_NO_ID) {
          token->word = rule->substitute;
          token->offset = 0;
          token->length = eliza_script_word_lengths[rule->substitute];
        }
      }
    }
    ++index;
  }
}

static int pattern_any_matches(const uint8_t* choices, uint8_t choice_count,
                               const ElizaToken* token) {
  uint8_t index;
  for(index = 0; index < choice_count; ++index)
    if(token->word == choices[index]) return 1;
  return 0;
}

static int match_pattern_from(const uint8_t* pattern, const uint8_t* end,
                              const ElizaToken* words, uint16_t word_count,
                              uint16_t word_index, uint8_t term_index,
                              ElizaCapture* captures) {
  const uint8_t* next;
  uint8_t opcode;
  uint8_t value;

  if(pattern == end) return word_index == word_count;
  if(pattern > end || term_index >= ELIZA_MAX_PATTERN_TERMS) return 0;
  opcode = *pattern++;
  if(pattern >= end) return 0;
  value = *pattern++;
  next = pattern;

  if(opcode == PATTERN_COUNT) {
    if(value == 0) {
      uint16_t length;
      for(length = 0; word_index + length <= word_count; ++length) {
        captures[term_index].start = word_index;
        captures[term_index].count = length;
        if(match_pattern_from(next, end, words, word_count,
                              (uint16_t) (word_index + length),
                              (uint8_t) (term_index + 1U), captures)) return 1;
      }
      return 0;
    }
    if(word_index + value > word_count) return 0;
    captures[term_index].start = word_index;
    captures[term_index].count = value;
    return match_pattern_from(next, end, words, word_count,
                              (uint16_t) (word_index + value),
                              (uint8_t) (term_index + 1U), captures);
  }

  if(word_index >= word_count) return 0;
  if(opcode == PATTERN_WORD) {
    if(words[word_index].word != value) return 0;
  } else if(opcode == PATTERN_ANY) {
    if((size_t) (end - pattern) < value ||
       !pattern_any_matches(pattern, value, &words[word_index])) return 0;
    next = pattern + value;
  } else if(opcode == PATTERN_TAG) {
    if(words[word_index].word >= ELIZA_SCRIPT_WORD_COUNT ||
       (eliza_script_word_tags[words[word_index].word] & value) == 0) return 0;
  } else {
    return 0;
  }

  captures[term_index].start = word_index;
  captures[term_index].count = 1;
  return match_pattern_from(next, end, words, word_count,
                            (uint16_t) (word_index + 1U),
                            (uint8_t) (term_index + 1U), captures);
}

static int match_transform(const ElizaTransformData* transform,
                           const ElizaToken* words, uint16_t word_count,
                           ElizaCapture* captures) {
  const uint8_t* pattern = eliza_script_patterns + transform->pattern_offset;
  return match_pattern_from(pattern, pattern + transform->pattern_size,
                            words, word_count, 0, 0, captures);
}

static void append_item(char* output, size_t capacity, size_t* used,
                        const char* text, size_t length) {
  size_t index;
  if(length == 0 || output == NULL || capacity == 0) return;
  if(*used != 0 && *used + 1U < capacity) output[(*used)++] = ' ';
  for(index = 0; index < length && *used + 1U < capacity; ++index)
    output[(*used)++] = text[index];
  output[*used] = 0;
}

static void append_token(char* output, size_t capacity, size_t* used,
                         const ElizaToken* token, const char* normalized) {
  const char* text;
  uint16_t length;
  if(token->word == TOKEN_DELIMITER) return;
  token_bytes(token, normalized, &text, &length);
  append_item(output, capacity, used, text, length);
}

static void assemble_template(const unsigned char* template_text,
                              const ElizaToken* words,
                              const char* normalized,
                              const ElizaCapture* captures,
                              char* output, size_t capacity) {
  size_t used = 0;
  const unsigned char* cursor = template_text;
  if(output == NULL || capacity == 0) return;
  output[0] = 0;

  while(*cursor != 0) {
    const unsigned char* start;
    size_t length;
    while(*cursor == ' ') ++cursor;
    if(*cursor == 0) break;
    start = cursor;
    while(*cursor != 0 && *cursor != ' ') ++cursor;
    length = (size_t) (cursor - start);
    if(length == 1 && start[0] >= 1 &&
       start[0] <= ELIZA_MAX_PATTERN_TERMS) {
      const ElizaCapture* capture = &captures[start[0] - 1U];
      uint16_t index;
      for(index = 0; index < capture->count; ++index)
        append_token(output, capacity, &used,
                     &words[capture->start + index], normalized);
    } else {
      append_item(output, capacity, &used, (const char*) start, length);
    }
  }
}

static size_t copy_capture(const ElizaToken* words, const char* normalized,
                           const ElizaCapture* capture,
                           char* output, size_t capacity) {
  size_t used = 0;
  uint16_t index;
  if(output == NULL || capacity == 0) return 0;
  output[0] = 0;
  for(index = 0; index < capture->count; ++index)
    append_token(output, capacity, &used,
                 &words[capture->start + index], normalized);
  return used;
}

static void assemble_memory(const unsigned char* template_text,
                            const char* capture, size_t capture_length,
                            char* output, size_t capacity) {
  size_t used = 0;
  const unsigned char* cursor = template_text;
  if(output == NULL || capacity == 0) return;
  output[0] = 0;
  while(*cursor != 0) {
    const unsigned char* start;
    size_t length;
    while(*cursor == ' ') ++cursor;
    if(*cursor == 0) break;
    start = cursor;
    while(*cursor != 0 && *cursor != ' ') ++cursor;
    length = (size_t) (cursor - start);
    if(length == 1 && start[0] == 3)
      append_item(output, capacity, &used, capture, capture_length);
    else
      append_item(output, capacity, &used, (const char*) start, length);
  }
}

static int build_pre_sentence(const unsigned char* template_text,
                              ElizaToken* words,
                              const ElizaCapture* captures,
                              uint16_t* word_count) {
  const unsigned char* cursor = template_text;
  ElizaToken prefix[ELIZA_MAX_PATTERN_TERMS];
  const ElizaCapture* tail = NULL;
  uint16_t prefix_count = 0;
  while(*cursor != 0) {
    const unsigned char* start;
    size_t length;
    while(*cursor == ' ') ++cursor;
    if(*cursor == 0) break;
    start = cursor;
    while(*cursor != 0 && *cursor != ' ') ++cursor;
    length = (size_t) (cursor - start);
    if(length == 1 && start[0] >= 1 &&
       start[0] <= ELIZA_MAX_PATTERN_TERMS) {
      if(tail != NULL) return 0;
      tail = &captures[start[0] - 1U];
    } else {
      const uint8_t word = find_word((const char*) start, length);
      if(tail != NULL || word == TOKEN_UNKNOWN ||
         prefix_count >= ELIZA_MAX_PATTERN_TERMS) return 0;
      prefix[prefix_count].word = word;
      prefix[prefix_count].offset = 0;
      prefix[prefix_count].length = eliza_script_word_lengths[word];
      ++prefix_count;
    }
  }
  if(tail != NULL) {
    uint16_t index;
    if(prefix_count + tail->count > ELIZA_MAX_WORDS) return 0;
    if(prefix_count > tail->start) {
      for(index = tail->count; index != 0; --index)
        words[prefix_count + index - 1U] =
            words[tail->start + index - 1U];
    } else {
      for(index = 0; index < tail->count; ++index)
        words[prefix_count + index] = words[tail->start + index];
    }
    *word_count = (uint16_t) (prefix_count + tail->count);
  } else {
    *word_count = prefix_count;
  }
  {
    uint16_t index;
    for(index = 0; index < prefix_count; ++index) words[index] = prefix[index];
  }
  return 1;
}

static enum action select_reassembly(eliza_state* state, uint8_t transform_id,
                                     ElizaToken* words, uint16_t* word_count,
                                     const char* normalized,
                                     const ElizaCapture* captures,
                                     char* output, size_t output_size,
                                     uint8_t* link_rule) {
  const ElizaTransformData* transform = &eliza_script_transforms[transform_id];
  uint8_t cursor = state->next_reassembly[transform_id];
  uint16_t offset;
  const unsigned char* data;
  uint8_t kind;

  if(cursor >= transform->reassembly_count) cursor = 0;
  state->next_reassembly[transform_id] =
      (uint8_t) (cursor + 1U == transform->reassembly_count ? 0 : cursor + 1U);
  offset =
      eliza_script_reassembly_offsets[transform->first_reassembly + cursor];
  data = eliza_script_reassemblies + offset;
  kind = *data++;

  if(kind == REASSEMBLY_TEXT) {
    assemble_template(data, words, normalized, captures, output, output_size);
    return ACTION_COMPLETE;
  }
  if(kind == REASSEMBLY_LINK) {
    *link_rule = *data;
    return ACTION_LINK;
  }
  if(kind == REASSEMBLY_NEWKEY) return ACTION_NEWKEY;
  if(kind == REASSEMBLY_PRE) {
    *link_rule = *data++;
    if(!build_pre_sentence(data, words, captures, word_count))
      return ACTION_INAPPLICABLE;
    return ACTION_LINK;
  }
  return ACTION_INAPPLICABLE;
}

static enum action apply_rule(eliza_state* state, uint8_t rule_id,
                              ElizaToken* words, uint16_t* word_count,
                              const char* normalized, char* output,
                              size_t output_size, uint8_t* link_rule) {
  const ElizaRuleData* rule;
  uint8_t index;
  if(rule_id >= ELIZA_SCRIPT_RULE_COUNT) return ACTION_INAPPLICABLE;
  rule = &eliza_script_rules[rule_id];
  for(index = 0; index < rule->transform_count; ++index) {
    const uint8_t transform_id =
        (uint8_t) (rule->first_transform + index);
    ElizaCapture captures[ELIZA_MAX_PATTERN_TERMS] = {{0, 0}};
    if(match_transform(&eliza_script_transforms[transform_id],
                       words, *word_count, captures))
      return select_reassembly(state, transform_id, words, word_count,
                               normalized, captures, output, output_size,
                               link_rule);
  }
  if(rule->link != ELIZA_NO_ID) {
    *link_rule = rule->link;
    return ACTION_LINK;
  }
  return ACTION_INAPPLICABLE;
}

static uint8_t hollerith_code(unsigned char value) {
  if(value >= '0' && value <= '9') return (uint8_t) (value - '0');
  if(value >= 'A' && value <= 'I') return (uint8_t) (17U + value - 'A');
  if(value >= 'J' && value <= 'R') return (uint8_t) (33U + value - 'J');
  if(value >= 'S' && value <= 'Z') return (uint8_t) (50U + value - 'S');
  switch(value) {
    case '=': return 11;
    case '\'': return 12;
    case '+': return 16;
    case '.': return 27;
    case ')': return 28;
    case '-': return 32;
    case '$': return 43;
    case '*': return 44;
    case ' ': return 48;
    case '/': return 49;
    case ',': return 59;
    case '(': return 60;
    default: return (uint8_t) (value & 0x3fU);
  }
}

static uint8_t memory_hash(const ElizaToken* token, const char* normalized) {
  const char* text;
  uint16_t length;
  uint16_t chunk_start = 0;
  uint8_t count = 0;
  uint64_t datum = 0;
  token_bytes(token, normalized, &text, &length);
  if(length != 0) chunk_start = (uint16_t) (((length - 1U) / 6U) * 6U);
  while(chunk_start + count < length && count < 6U) {
    datum = (datum << 6U) |
            hollerith_code((unsigned char) text[chunk_start + count]);
    ++count;
  }
  while(count < 6U) {
    datum = (datum << 6U) | hollerith_code(' ');
    ++count;
  }
  datum &= 0x7ffffffffULL;
  datum *= datum;
  return (uint8_t) ((datum >> 34U) & 3U);
}

static size_t capture_text_length(const ElizaToken* words,
                                  const char* normalized,
                                  const ElizaCapture* capture) {
  size_t length = 0;
  uint16_t index;
  for(index = 0; index < capture->count; ++index) {
    const ElizaToken* token = &words[capture->start + index];
    const char* text;
    uint16_t token_length;
    if(token->word == TOKEN_DELIMITER) continue;
    token_bytes(token, normalized, &text, &token_length);
    (void) text;
    if(token_length != 0) length += token_length + (length != 0 ? 1U : 0U);
  }
  return length;
}

static void create_memory(eliza_state* state, const ElizaToken* words,
                          uint16_t word_count, const char* normalized) {
  const uint8_t kind = word_count == 0 ? ELIZA_NO_ID :
      memory_hash(&words[word_count - 1U], normalized);
  const uint8_t transform_id = kind == ELIZA_NO_ID ? ELIZA_NO_ID :
      eliza_script_memory_transforms[kind];
  const ElizaTransformData* transform;
  ElizaCapture captures[ELIZA_MAX_PATTERN_TERMS] = {{0, 0}};
  size_t capture_length;
  size_t record_size;
  uint8_t* record;

  if(transform_id == ELIZA_NO_ID || state->memory == NULL ||
     state->memory_used > state->memory_capacity) return;
  transform = &eliza_script_transforms[transform_id];
  if(!match_transform(transform, words, word_count, captures)) return;
  capture_length = capture_text_length(words, normalized, &captures[2]);
  record_size = ELIZA_MEMORY_HEADER_BYTES + capture_length + 1U;
  if(record_size > state->memory_capacity - state->memory_used) return;
  record = state->memory + state->memory_used;
  record[0] = kind;
  record[1] = (uint8_t) capture_length;
  record[2] = (uint8_t) (capture_length >> 8U);
  copy_capture(words, normalized, &captures[2],
               (char*) record + ELIZA_MEMORY_HEADER_BYTES,
               capture_length + 1U);
  state->memory_used += record_size;
}

static void recall_memory(eliza_state* state, char* output,
                          size_t output_size) {
  size_t index;
  size_t capture_length;
  size_t record_size;
  uint8_t transform_id;
  const ElizaTransformData* transform;
  uint16_t offset;
  const unsigned char* data;
  if(state->memory == NULL || state->memory_used > state->memory_capacity ||
     state->memory_used < ELIZA_MEMORY_HEADER_BYTES + 1U ||
     state->memory[0] >= sizeof(eliza_script_memory_transforms)) {
    state->memory_used = 0;
    output[0] = 0;
    return;
  }
  capture_length =
      (size_t) state->memory[1] | ((size_t) state->memory[2] << 8U);
  record_size = ELIZA_MEMORY_HEADER_BYTES + capture_length + 1U;
  if(record_size > state->memory_used) {
    state->memory_used = 0;
    output[0] = 0;
    return;
  }
  transform_id = eliza_script_memory_transforms[state->memory[0]];
  if(transform_id == ELIZA_NO_ID ||
     transform_id >= ELIZA_SCRIPT_TRANSFORM_COUNT) {
    state->memory_used = 0;
    output[0] = 0;
    return;
  }
  transform = &eliza_script_transforms[transform_id];
  offset = eliza_script_reassembly_offsets[transform->first_reassembly];
  data = eliza_script_reassemblies + offset;
  if(*data++ == REASSEMBLY_TEXT)
    assemble_memory(data,
                    (const char*) state->memory + ELIZA_MEMORY_HEADER_BYTES,
                    capture_length, output, output_size);
  else
    output[0] = 0;
  for(index = record_size; index < state->memory_used; ++index)
    state->memory[index - record_size] = state->memory[index];
  state->memory_used -= record_size;
}

static const char* nomatch_message(uint8_t limit) {
  switch(limit) {
    case 1: return "PLEASE CONTINUE";
    case 2: return "HMMM";
    case 3: return "GO ON , PLEASE";
    default: return "I SEE";
  }
}

void eliza_init(eliza_state* state, uint8_t* memory,
                size_t memory_capacity) {
  size_t index;
  if(state == NULL) return;
  for(index = 0; index < sizeof(*state); ++index)
    ((uint8_t*) state)[index] = 0;
  state->limit = 1;
  state->memory = memory;
  state->memory_capacity = memory != NULL ? memory_capacity : 0;
}

int eliza_is_goodbye(const char* input) {
  char normalized[ELIZA_INPUT_BYTES];
  ElizaToken words[ELIZA_MAX_WORDS];
  ElizaToken compact[2];
  uint16_t count = parse_input(input, normalized, words, 0);
  uint8_t used = 0;
  uint16_t index;
  for(index = 0; index < count && used < 2; ++index)
    if(words[index].word != TOKEN_DELIMITER) compact[used++] = words[index];
  for(; index < count; ++index)
    if(words[index].word != TOKEN_DELIMITER) return 0;
  if(used == 1)
    return token_equals(&compact[0], normalized, "BYE") ||
           token_equals(&compact[0], normalized, "GOODBYE") ||
           token_equals(&compact[0], normalized, "GOOD-BYE") ||
           token_equals(&compact[0], normalized, "QUIT") ||
           token_equals(&compact[0], normalized, "EXIT");
  return used == 2 && token_equals(&compact[0], normalized, "GOOD") &&
         token_equals(&compact[1], normalized, "BYE");
}

void eliza_reply(eliza_state* state, const char* input,
                 char* output, size_t output_size) {
  char normalized[ELIZA_INPUT_BYTES];
  ElizaToken words[ELIZA_MAX_WORDS];
  uint8_t stack[ELIZA_MAX_WORDS];
  uint16_t word_count;
  uint16_t stack_count;

  if(output == NULL || output_size == 0) return;
  output[0] = 0;
  if(state == NULL) return;

  word_count = parse_input(input, normalized, words, 1);
  state->limit = (uint8_t) (state->limit % 4U + 1U);
  scan_keywords(words, &word_count, stack, &stack_count);

  if(stack_count == 0 && state->limit == 4 &&
     state->memory_used != 0) {
    recall_memory(state, output, output_size);
    return;
  }

  while(stack_count != 0) {
    const uint8_t rule_id = stack_pop_front(stack, &stack_count);
    uint8_t link_rule = ELIZA_NO_ID;
    enum action result;
    if(rule_id == ELIZA_SCRIPT_MEMORY_RULE)
      create_memory(state, words, word_count, normalized);
    result = apply_rule(state, rule_id, words, &word_count, normalized,
                        output, output_size, &link_rule);
    if(result == ACTION_COMPLETE) return;
    if(result == ACTION_INAPPLICABLE) {
      copy_text(output, output_size, nomatch_message(state->limit));
      return;
    }
    if(result == ACTION_LINK)
      stack_push_front(stack, &stack_count, link_rule);
    /* NEWKEY exposes the next rule already in the stack. */
  }

  {
    uint8_t discard = ELIZA_NO_ID;
    if(apply_rule(state, ELIZA_SCRIPT_NONE_RULE, words, &word_count,
                  normalized, output, output_size,
                  &discard) == ACTION_COMPLETE) return;
  }
  copy_text(output, output_size, nomatch_message(state->limit));
}
