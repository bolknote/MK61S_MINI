/*
 * ZX0 format:
 * Copyright (c) 2021, Einar Saukas. All rights reserved.
 *
 * The bounded parser and streaming writer in this file are project-specific.
 * The emitted stream is compatible with the original ZX0 v2 decoder.
 */

#include "zx0.hpp"

#include <stdint.h>

namespace zx0 {
namespace {

static constexpr u16 MAX_OFFSET = 256;
// C5 currently feeds at most 3584 bytes, while the RAM-only workspace swap
// may encode a complete 8-KiB arena. Indices are u16, so both remain bounded.
static constexpr u32 MAX_INPUT_SIZE = 8192;
static constexpr u16 INFINITE_COST = 0xFFFFU;
static constexpr u16 END_COST = 18;

struct Costs {
  u16 literal;
  u16 match;
};

struct Token {
  u16 length;
  u16 offset; // 0 means a literal block.
};

static_assert(sizeof(Costs) == 4, "ZX0 cost entry must remain compact");
static_assert(sizeof(Token) == 4, "ZX0 token must remain compact");

struct Plan {
  const Token* tokens;
  u16 count;
  EncodeMode mode;
};

static u16 gamma_cost(u32 value) {
  u16 bits = 1;
  while(value > 1) {
    bits = (u16) (bits + 2);
    value >>= 1;
  }
  return bits;
}

static u16 add_cost(u16 left, u32 right) {
  if(left == INFINITE_COST || right >= INFINITE_COST ||
     (u32) left + right >= INFINITE_COST) return INFINITE_COST;
  return (u16) ((u32) left + right);
}

static u16 match_length(const u8* input, u16 size,
                        u16 position, u16 offset) {
  const u8* current = input + position;
  const u8* source = current - offset;
  const u8* const begin = current;
  const u8* const end = input + size;
  while(current < end && *current == *source) {
    current++;
    source++;
  }
  return (u16) (current - begin);
}

static bool matching_offset(const u8* input, u16 size, u16 position,
                            u16 offset, u16 length) {
  if(offset == 0 || offset > position ||
     (u32) position + length > size) return false;
  const u8* current = input + position;
  const u8* source = current - offset;
  while(length-- != 0) {
    if(*current++ != *source++) return false;
  }
  return true;
}

static u16 new_match_cost(u16 offset, u16 length) {
  const u16 high = (u16) (((offset - 1U) / 128U) + 1U);
  return (u16) (8U + gamma_cost(high) + gamma_cost(length - 1U));
}

static bool append_token(Token* tokens, usize capacity, u16& count,
                         u16 length, u16 offset) {
  if(length == 0 || count >= capacity) return false;
  tokens[count].length = length;
  tokens[count].offset = offset;
  count++;
  return true;
}

static Token find_match_choice(const u8* input, u16 size, u16 position,
                               const Costs* costs, u16 target,
                               u16 preferred_offset) {
  const u16 maximum_offset =
    position < MAX_OFFSET ? position : MAX_OFFSET;

  // Сначала пробуем прежнее смещение: при записи оно превратится в более
  // короткий last-offset блок, хотя DP намеренно не хранит offset в состоянии.
  if(preferred_offset != 0 && preferred_offset <= maximum_offset) {
    const u16 maximum =
      match_length(input, size, position, preferred_offset);
    if(maximum >= 2) {
      u16 cost = new_match_cost(preferred_offset, maximum);
      for(u16 length = maximum;; length--) {
        const u16 tail = costs[position + length].literal;
        if(add_cost(tail, cost) == target) {
          return {length, preferred_offset};
        }
        if(length == 2) break;
        const u16 next_value = (u16) (length - 1U);
        if((next_value & (next_value - 1U)) == 0) {
          cost = (u16) (cost - 2U);
        }
      }
    }
  }

  // На одинаковой стоимости выбираем более длинное совпадение, затем меньшее
  // смещение. Это делает результат стабильным и обычно сокращает число блоков.
  u16 best_length = 0;
  u16 best_offset = 0;
  for(u16 offset = 1; offset <= maximum_offset; offset++) {
    if(offset == preferred_offset) continue;
    const u16 maximum = match_length(input, size, position, offset);
    if(maximum < 2) continue;
    u16 cost = new_match_cost(offset, maximum);
    for(u16 length = maximum;; length--) {
      const u16 tail = costs[position + length].literal;
      if(add_cost(tail, cost) == target) {
        if(length > best_length ||
           (length == best_length &&
            (best_offset == 0 || offset < best_offset))) {
          best_length = length;
          best_offset = offset;
        }
        break;
      }
      if(length == 2) break;
      const u16 next_value = (u16) (length - 1U);
      if((next_value & (next_value - 1U)) == 0) {
        cost = (u16) (cost - 2U);
      }
    }
  }
  return {best_length, best_offset};
}

static bool build_bounded_optimal_plan(const u8* input, u16 size,
                                       u8* workspace, usize workspace_size,
                                       Plan& plan) {
  const usize required = ((usize) size + 1U) * sizeof(Costs);
  if(workspace_size < required) return false;

  Costs* const costs = (Costs*) workspace;
  u16 lcp[MAX_OFFSET + 1] = {};
  costs[size].literal = END_COST;
  costs[size].match = END_COST;

  for(u32 cursor = size; cursor-- != 0;) {
    const u16 position = (u16) cursor;
    const u16 maximum_offset =
      position < MAX_OFFSET ? position : MAX_OFFSET;
    u16 near_length = 0;
    u16 far_length = 0;

    for(u16 offset = 1; offset <= MAX_OFFSET; offset++) {
      if(offset <= maximum_offset &&
         input[position] == input[position - offset]) {
        lcp[offset] = (u16) (lcp[offset] + 1U);
      } else {
        lcp[offset] = 0;
      }
      if(offset <= 128) {
        if(lcp[offset] > near_length) near_length = lcp[offset];
      } else if(lcp[offset] > far_length) {
        far_length = lcp[offset];
      }
    }

    u16 best_match = INFINITE_COST;
    u16 match_cost = 10;
    for(u16 length = 2; length <= near_length; length++) {
      const u16 candidate =
        add_cost(costs[position + length].literal, match_cost);
      if(candidate < best_match) best_match = candidate;
      if((length & (length - 1U)) == 0) {
        match_cost = (u16) (match_cost + 2U);
      }
    }
    match_cost = 12;
    for(u16 length = 2; length <= far_length; length++) {
      const u16 candidate =
        add_cost(costs[position + length].literal, match_cost);
      if(candidate < best_match) best_match = candidate;
      if((length & (length - 1U)) == 0) {
        match_cost = (u16) (match_cost + 2U);
      }
    }
    costs[position].match = best_match;

    u16 best_literal = INFINITE_COST;
    const u16 remaining = (u16) (size - position);
    u16 block_cost = 10;
    for(u16 length = 1; length <= remaining; length++) {
      const u16 candidate =
        add_cost(costs[position + length].match, block_cost);
      if(candidate < best_literal) best_literal = candidate;
      const u16 next_length = (u16) (length + 1U);
      block_cost = (u16) (block_cost + 8U);
      if((next_length & (next_length - 1U)) == 0) {
        block_cost = (u16) (block_cost + 2U);
      }
    }
    // После match формат разрешает как literal (selector 0), так и ещё один
    // new-offset match (selector 1). Это существенно для данных с несколькими
    // соседними словарными фрагментами.
    costs[position].literal =
      best_match < best_literal ? best_match : best_literal;
  }

  Token* const tokens = (Token*) workspace;
  const usize token_capacity = workspace_size / sizeof(Token);
  u16 token_count = 0;
  u16 position = 0;
  u16 last_offset = 1;
  bool need_literal = true;

  while(position < size) {
    if(need_literal) {
      const u16 target = costs[position].literal;
      const u16 maximum = (u16) (size - position);
      u16 chosen = 0;
      u16 block_cost = (u16) (
          1U + gamma_cost(maximum) + (u32) maximum * 8U);
      for(u16 length = maximum;; length--) {
        if(add_cost(costs[position + length].match, block_cost) == target) {
          chosen = length;
          break;
        }
        if(length == 1) break;
        block_cost = (u16) (block_cost - 8U);
        if((length & (length - 1U)) == 0) {
          block_cost = (u16) (block_cost - 2U);
        }
      }
      if(chosen != 0) {
        if(!append_token(tokens, token_capacity, token_count, chosen, 0)) {
          return false;
        }
        position = (u16) (position + chosen);
        need_literal = false;
        continue;
      }

      // Literal не является лучшим продолжением: остаёмся в состоянии
      // "после match" и записываем соседний new-offset match.
      const Token choice =
          find_match_choice(input, size, position, costs, target, last_offset);
      if(choice.offset == 0 ||
         !append_token(tokens, token_capacity, token_count,
                       choice.length, choice.offset)) {
        return false;
      }
      position = (u16) (position + choice.length);
      last_offset = choice.offset;
      need_literal = true;
    } else {
      const u16 target = costs[position].match;
      const Token choice =
          find_match_choice(input, size, position, costs, target, last_offset);
      if(choice.offset == 0 ||
         !append_token(tokens, token_capacity, token_count,
                       choice.length, choice.offset)) {
        return false;
      }
      position = (u16) (position + choice.length);
      last_offset = choice.offset;
      need_literal = true;
    }
  }

  plan.tokens = tokens;
  plan.count = token_count;
  plan.mode = EncodeMode::BOUNDED_OPTIMAL;
  return token_count != 0 && tokens[0].offset == 0;
}

static bool build_greedy_plan(const u8* input, u16 size,
                              u8* workspace, usize workspace_size,
                              Plan& plan) {
  Token* const tokens = (Token*) workspace;
  const usize token_capacity = workspace_size / sizeof(Token);
  u16 token_count = 0;
  u16 literal_start = 0;
  u16 position = 1;
  u16 last_offset = 1;

  while((u32) position + 1U < size) {
    const u16 maximum_offset =
      position < MAX_OFFSET ? position : MAX_OFFSET;
    u16 best_length = 0;
    u16 best_offset = 0;
    for(u16 offset = 1; offset <= maximum_offset; offset++) {
      const u16 length = match_length(input, size, position, offset);
      if(length > best_length ||
         (length == best_length && length >= 2 &&
          (offset == last_offset ||
           (best_offset != last_offset && offset < best_offset)))) {
        best_length = length;
        best_offset = offset;
      }
    }
    if(best_length < 2) {
      position++;
      continue;
    }

    if(!append_token(tokens, token_capacity, token_count,
                     (u16) (position - literal_start), 0) ||
       !append_token(tokens, token_capacity, token_count,
                     best_length, best_offset)) return false;
    last_offset = best_offset;
    literal_start = (u16) (position + best_length);
    if(literal_start >= size) {
      position = size;
      break;
    }
    position = (u16) (literal_start + 1U);
  }

  if(literal_start < size &&
     !append_token(tokens, token_capacity, token_count,
                   (u16) (size - literal_start), 0)) return false;
  plan.tokens = tokens;
  plan.count = token_count;
  plan.mode = EncodeMode::GREEDY;
  return token_count != 0 && tokens[0].offset == 0;
}

template<typename Writer>
static bool write_gamma(Writer& writer, u32 value, bool inverted,
                        bool skip_first = false) {
  if(value == 0) return false;
  u32 top = 1;
  while((top << 1) <= value) top <<= 1;
  bool first = true;
  while((top >>= 1) != 0) {
    const bool data = (value & top) != 0;
    const bool bits[2] = {false, data != inverted};
    for(u8 index = 0; index < 2; index++) {
      if(skip_first && first) first = false;
      else if(!writer.bit(bits[index])) return false;
    }
  }
  if(skip_first && first) return true;
  return writer.bit(true);
}

template<bool validate_matches, typename Writer>
static bool write_stream(const u8* input, u16 input_size,
                         const Plan& plan, Writer& writer) {
  u16 position = 0;
  u16 last_offset = 1;
  bool previous_literal = false;

  for(u16 index = 0; index < plan.count; index++) {
    const Token& token = plan.tokens[index];
    if(token.length == 0 ||
       (u32) position + token.length > input_size) return false;

    if(token.offset == 0) {
      if(index != 0 && !writer.bit(false)) return false;
      if(!write_gamma(writer, token.length, false)) return false;
      for(u16 byte_index = 0; byte_index < token.length; byte_index++) {
        if(!writer.byte(input[position + byte_index])) return false;
      }
      previous_literal = true;
    } else {
      if(token.offset > MAX_OFFSET || token.offset > position ||
         (validate_matches &&
          !matching_offset(input, input_size, position,
                           token.offset, token.length))) return false;
      if(previous_literal && token.offset == last_offset) {
        if(!writer.bit(false) ||
           !write_gamma(writer, token.length, false)) return false;
      } else {
        if(!writer.bit(true)) return false;
        const u16 high =
          (u16) (((token.offset - 1U) / 128U) + 1U);
        if(!write_gamma(writer, high, true)) return false;
        const u8 first_length_bit = token.length == 2 ? 1U : 0U;
        const u8 low =
          (u8) (127U - ((token.offset - 1U) % 128U));
        if(!writer.byte((u8) ((low << 1) | first_length_bit)) ||
           !write_gamma(writer, token.length - 1U, false, true)) {
          return false;
        }
        last_offset = token.offset;
      }
      previous_literal = false;
    }
    position = (u16) (position + token.length);
  }

  return position == input_size &&
         writer.bit(true) && write_gamma(writer, 256, true);
}

class LayoutWriter {
  public:
    LayoutWriter(u8* controls, usize capacity)
      : controls_(controls), capacity_(capacity), count_(0),
        output_size_(0), mask_(0) {}

    bool bit(bool value) {
      if(mask_ == 0) {
        if(count_ >= capacity_) return false;
        controls_[count_++] = 0;
        output_size_++;
        mask_ = 0x80;
      }
      if(value) controls_[count_ - 1U] |= mask_;
      mask_ >>= 1;
      return true;
    }

    bool byte(u8) {
      output_size_++;
      return true;
    }

    usize control_count(void) const { return count_; }
    u32 output_size(void) const { return output_size_; }

  private:
    u8* controls_;
    usize capacity_;
    usize count_;
    u32 output_size_;
    u8 mask_;
};

class OutputWriter {
  public:
    OutputWriter(const Output& output, const u8* controls, usize count)
      : output_(output), controls_(controls), count_(count), index_(0),
        output_size_(0), mask_(0), current_(0) {}

    bool bit(bool value) {
      if(mask_ == 0) {
        if(index_ >= count_) return false;
        current_ = controls_[index_++];
        if(!output_.next(output_.context, current_)) return false;
        output_size_++;
        mask_ = 0x80;
      }
      if(((current_ & mask_) != 0) != value) return false;
      mask_ >>= 1;
      return true;
    }

    bool byte(u8 value) {
      if(!output_.next(output_.context, value)) return false;
      output_size_++;
      return true;
    }

    bool complete(void) const { return index_ == count_; }
    u32 output_size(void) const { return output_size_; }

  private:
    Output output_;
    const u8* controls_;
    usize count_;
    usize index_;
    u32 output_size_;
    u8 mask_;
    u8 current_;
};

} // namespace

bool prepare(const u8* input, u32 input_size,
             u8* workspace, usize workspace_size,
             Prepared& prepared) {
  prepared = {};
  prepared.mode = EncodeMode::GREEDY;
  if(input == nullptr || input_size == 0 || input_size > MAX_INPUT_SIZE ||
     workspace == nullptr || workspace_size < sizeof(Token)) return false;

  const uintptr_t input_begin = (uintptr_t) input;
  const uintptr_t workspace_begin = (uintptr_t) workspace;
  if(input_size > UINTPTR_MAX - input_begin ||
     workspace_size > UINTPTR_MAX - workspace_begin) return false;
  const uintptr_t input_end = input_begin + input_size;
  const uintptr_t workspace_end = workspace_begin + workspace_size;
  if(input_begin < workspace_end && workspace_begin < input_end) return false;

  const uintptr_t address = (uintptr_t) workspace;
  const usize alignment_skip =
    (usize) ((alignof(Token) - (address % alignof(Token))) % alignof(Token));
  if(alignment_skip >= workspace_size) return false;
  workspace += alignment_skip;
  workspace_size -= alignment_skip;

  Plan plan = {};
  const u16 size = (u16) input_size;
  if(!build_bounded_optimal_plan(input, size, workspace,
                                 workspace_size, plan) &&
     !build_greedy_plan(input, size, workspace, workspace_size, plan)) {
    return false;
  }

  const usize token_bytes = (usize) plan.count * sizeof(Token);
  if(token_bytes >= workspace_size || token_bytes > 0xFFFFU) return false;
  u8* const controls = workspace + token_bytes;
  const usize control_capacity = workspace_size - token_bytes;
  LayoutWriter layout(controls, control_capacity);
  if(!write_stream<true>(input, size, plan, layout) ||
     layout.control_count() == 0 ||
     layout.control_count() > 0xFFFFU) return false;

  prepared.input = input;
  prepared.workspace = workspace;
  prepared.output_size = layout.output_size();
  prepared.input_size = size;
  prepared.token_count = plan.count;
  prepared.control_offset = (u16) token_bytes;
  prepared.control_count = (u16) layout.control_count();
  prepared.mode = plan.mode;
  return true;
}

bool emit(const Prepared& prepared, const Output& output) {
  if(prepared.input == nullptr || prepared.workspace == nullptr ||
     prepared.input_size == 0 || prepared.input_size > MAX_INPUT_SIZE ||
     prepared.token_count == 0 ||
     prepared.token_count > prepared.input_size ||
     prepared.control_offset !=
         (usize) prepared.token_count * sizeof(Token) ||
     prepared.control_count == 0 || prepared.output_size == 0 ||
     output.next == nullptr) {
    return false;
  }

  const Plan plan = {
    (const Token*) prepared.workspace,
    prepared.token_count,
    prepared.mode
  };
  const u8* const controls =
      prepared.workspace + prepared.control_offset;
  OutputWriter writer(output, controls, prepared.control_count);
  return write_stream<false>(
             prepared.input, prepared.input_size, plan, writer) &&
         writer.complete() &&
         writer.output_size() == prepared.output_size;
}

bool encode(const u8* input, u32 input_size,
            u8* workspace, usize workspace_size,
            const Output& output, EncodeResult& result) {
  result.output_size = 0;
  result.mode = EncodeMode::GREEDY;
  Prepared prepared = {};
  if(!prepare(input, input_size, workspace, workspace_size, prepared) ||
     !emit(prepared, output)) return false;

  result.output_size = prepared.output_size;
  result.mode = prepared.mode;
  return true;
}

} // namespace zx0
