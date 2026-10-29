#include "mk61emu_core.h"
#include "terminal_script.hpp"
#if !defined(MK61_CORE_STANDALONE)
#include "config.h"
#include "dwt_profiler.hpp"
#endif
#include "m61_text.hpp"
#include "mk61_ref.hpp"
#include "mk61_register_init.hpp"
#include "program_load.hpp"
#include "terminal_catalog.hpp"
#include "terminal_core.hpp"
#include "terminal_key_sequence.hpp"
#include "terminal_mnemonics.hpp"
#include "terminal_script_backend.hpp"
#include <cstring>

namespace terminal_script {
namespace {
isize assembly_address = 0;
constexpr char symbols[16] = {'0', '1', '2', '3', '4', '5',        '6', '7',
                              '8', '9', '-', 'L', 'C', (char)0xC3, 'E', ' '};
using Result = terminal_protocol::Result;
using Kind = terminal_protocol::ResultKind;
Result fail(const char *message) {
  terminal_script_backend::error(message);
  return Result::error();
}
bool delimiter(char c) {
  return terminal_core::is_end(c) || terminal_core::is_space(c) || c == '<' ||
         c == '>' || c == '=' || c == '!';
}
u8 reference(const char *&p) {
  p = terminal_core::skip_spaces(p);
  const char c = *p | 32;
  if (c == 'r') {
    const int digit = terminal_core::digit_value(p[1], 16);
    if (digit >= 0 && delimiter(p[2])) {
      p += 2;
      return (u8)(digit + 1);
    }
    return 0;
  }
  const u8 ref = c == 'x'   ? 18
                 : c == 'y' ? 19
                 : c == 'z' ? 20
                 : c == 't' ? 21
                            : 0;
  if (!ref)
    return 0;
  const bool x1 = c == 'x' && p[1] == '1';
  const unsigned n = x1 ? 2 : 1;
  if (!delimiter(p[n]))
    return 0;
  p += n;
  return x1 ? 17 : ref;
}
bool read_reference(u8 ref, double &number) {
  if (!ref || ref > 21)
    return false;
  char text[15]{};
  if (ref <= 16) {
    if (!mk61_ref::register_available(ref - 1))
      return false;
    if (mk61_ref::try_read_register_number(ref - 1, number))
      return true;
    MK61Emu_ReadRegister(ref - 1, text, symbols);
  } else {
    const stack reg = ref == 17   ? X1
                      : ref == 18 ? X
                      : ref == 19 ? Y
                      : ref == 20 ? Z
                                  : T;
    if (mk61_ref::try_read_stack_number(reg, number))
      return true;
    read_stack_register(reg, text, symbols);
  }
  return terminal_core::parse_mk_display_value(text, number);
}
bool operand(const char *&p, double &number) {
#if !defined(MK61_CORE_STANDALONE)
  MK61_RUNTIME_PROFILE_SCOPE(dwt_profiler::Point::M61_OPERAND);
#endif
  const char *before = p;
  const u8 ref = reference(p);
  if (!ref)
    return terminal_core::parse_decimal(p, number);
  if (ref == 16 && !core_61::expanded_program_is_on()) {
    p = before;
    return false;
  }
  return read_reference(ref, number);
}
u8 operation(const char *&p) {
  p = terminal_core::skip_spaces(p);
  const char first = *p;
  if (first != '>' && first != '<' && first != '=' && first != '!')
    return 0;
  ++p;
  const bool equal = *p == '=';
  if (equal)
    ++p;
  return first == '>'            ? (equal ? 2 : 1)
         : first == '<'          ? (equal ? 4 : 3)
         : first == '=' && equal ? 5
         : first == '!' && equal ? 6
                                 : 0;
}
bool compare(u8 op, double a, double b) {
  switch (op) {
  case 1:
    return a > b;
  case 2:
    return a >= b;
  case 3:
    return a < b;
  case 4:
    return a <= b;
  case 5:
    return a == b;
  case 6:
    return a != b;
  default:
    return false;
  }
}
bool condition(const char *&tail, bool &truth) {
  double a = 0, b = 0;
  if (!operand(tail, a))
    return false;
  const u8 op = operation(tail);
  if (!op || !operand(tail, b))
    return false;
  tail = terminal_core::skip_spaces(tail);
  if (!*tail)
    return false;
  truth = compare(op, a, b);
  return true;
}
bool fits(double number) {
  char sign, mantissa[8];
  isize exponent;
  return mk61_ref::double_to_parts(number, sign, mantissa, exponent);
}
bool hin(const char *args) {
  args = terminal_core::skip_spaces(args);
  if (!args || std::strlen(args) < 5)
    return false;
  unsigned address = 0;
  for (unsigned i = 0; i < 4; ++i) {
    if (args[i] < '0' || args[i] > '9')
      return false;
    address = address * 10 + args[i] - '0';
  }
  if (!terminal_core::is_space(args[4]) ||
      address >= terminal_script_backend::program_limit())
    return false;
  const char *p = terminal_core::skip_spaces(args + 4);
  u8 bytes[core_61::MAX_PROGRAM_STEP];
  unsigned count = 0;
  while (!terminal_core::is_end(*p) && !terminal_core::is_space(*p)) {
    const int high = terminal_core::digit_value(p[0], 16),
              low = terminal_core::digit_value(p[1], 16);
    if (high < 0 || low < 0 || count == sizeof(bytes) ||
        address + count >= terminal_script_backend::program_limit())
      return false;
    bytes[count++] = (u8)((high << 4) | low);
    p += 2;
  }
  return count && terminal_core::at_end(p) &&
         terminal_script_backend::write_program((u16)address, bytes,
                                                (u16)count);
}
} // namespace
void reset() {
  assembly_address = 0;
  terminal_script_backend::reset();
}
bool prepare_if(const char *line, PreparedIf &out, u8 &tail_offset) {
  const char *p = terminal_catalog::conditional_arguments(line);
  if (!p || std::strlen(line) > terminal_core::MAX_INPUT_TEXT)
    return false;
  const u8 ref = reference(p);
  if (!ref)
    return false;
  const u8 op = operation(p);
  double number = 0;
  if (!op || !terminal_core::parse_decimal(p, number) ||
      !(number >= -32768 && number <= 32767))
    return false;
  const i16 integer = (i16)number;
  if ((double)integer != number)
    return false;
  p = terminal_core::skip_spaces(p);
  if (!*p)
    return false;
  out = {integer, ref, op};
  tail_offset = (u8)(p - line);
  return true;
}
IfResult evaluate_if(const PreparedIf &prepared, bool trap) {
  trap = trap || m61_text::trap_handler_active();
  if (!terminal_command_allowed_in_script(CMD_IF) ||
      (trap && !terminal_command_allowed_in_trap(CMD_IF)))
    return IfResult::FALLBACK;
  double number = 0;
  if (!read_reference(prepared.reference, number)) {
    terminal_script_backend::error("Invalid IF reference");
    return IfResult::ERROR;
  }
  return compare(prepared.operation, number, prepared.literal)
             ? IfResult::TRUE
             : IfResult::FALSE;
}
bool assemble(const char *args, isize &next, const char *mnemonics) {
  const auto parsed = terminal_core::parse_assembly(
      args, next, mnemonics, terminal_script_backend::program_limit(),
      terminal_mnemonics::find);
  if (parsed.error != terminal_core::AssemblyError::NONE ||
      !terminal_script_backend::write_program(
          (u16)parsed.address, parsed.opcodes, (u16)parsed.count))
    return false;
  next = (isize)(parsed.address + parsed.count);
  return true;
}
bool command_supported(u8 id) {
  switch (id) {
  case CMD_VERSION:
  case CMD_LIST:
  case CMD_ISA:
  case CMD_ASM:
  case CMD_LASM:
  case CMD_REG_DUMP:
  case CMD_REG_SET:
  case CMD_LOAD:
  case CMD_1302:
  case CMD_HIN:
  case CMD_HOUT:
  case CMD_SET_CODE:
  case CMD_POKE:
  case CMD_DUMP:
  case CMD_PUB:
  case CMD_STACK:
  case CMD_KBD:
  case CMD_CMD:
  case CMD_RING:
  case CMD_RUN:
  case CMD_OPEN:
  case CMD_INS:
  case CMD_LED:
  case CMD_BEEP:
  case CMD_IF:
  case CMD_PRINT:
  case CMD_WAIT:
  case CMD_RET:
  case CMD_REINIT:
#if defined(MK61_CORE_STANDALONE)
  case CMD_DATE:
  case CMD_ALARM:
#endif
    return true;
  default:
    return false;
  }
}
Result execute(const char *line, bool trap) {
  if (!line)
    return Result::error();
  usize size = 0;
  while (line[size]) {
    if (!terminal_core::input_can_append(size++))
      return fail("M61 command is too long");
  }
  trap = trap || m61_text::trap_handler_active();
  while (const char *tail = terminal_catalog::conditional_arguments(line)) {
    bool truth = false;
    if (!condition(tail, truth))
      return fail("Invalid IF condition");
    if (!truth)
      return Result::ok();
    line = tail;
  }
  const u8 id = terminal_catalog::lookup((const u8 *)line);
  if (!terminal_command_allowed_in_script(id) ||
      (trap && !terminal_command_allowed_in_trap(id)))
    return fail("Command is not allowed in this M61 context");
  const char *args = line;
  while (!terminal_core::is_end(*args) && !terminal_core::is_space(*args))
    ++args;
  args = terminal_core::skip_spaces(args);
  if (program_load::blocked() &&
      (id == CMD_HIN || id == CMD_SET_CODE || id == CMD_ASM || id == CMD_INS ||
       id == CMD_KBD || id == CMD_CMD))
    return fail(program_load::error());
  switch (id) {
  case CMD_RUN: {
    if (*args == ':')
      return Result::action(Kind::GOTO_LABEL, args + 1);
    if (trap)
      return fail("Only run :label is allowed in a trap handler");
    u8 address = 0;
    const auto parsed = terminal_core::parse_run_address(
        args, core_61::program_steps(), address);
    if (parsed == terminal_core::RunAddressParse::INVALID)
      return fail("Invalid run address");
    if (*args && parsed == terminal_core::RunAddressParse::NOT_ADDRESS)
      return Result::action(Kind::OPEN_FILE, args);
    if (program_load::blocked())
      return fail(program_load::error());
    return Result::run_program(address);
  }
  case CMD_OPEN:
    return terminal_core::at_end(args) ? fail("OPEN needs a path")
                                       : Result::action(Kind::OPEN_FILE, args);
  case CMD_LOAD: {
    program_load::Request request{};
    if (program_load::parse(args, request) != program_load::Syntax::LEGACY)
      return Result::action(Kind::LOAD_BINARY, args);
    usize slot = 0;
    return Result::action(
        terminal_core::parse_single_unsigned(args, 10, 99, slot)
            ? Kind::LOAD_SLOT
            : Kind::OPEN_FILE,
        args);
  }
  case CMD_WAIT: {
    usize ms = 0;
    return terminal_core::parse_single_unsigned(args, 10, 60000, ms) && ms
               ? Result::wait((i32)ms)
               : fail("Invalid wait duration");
  }
  case CMD_RET:
  case CMD_REINIT:
    if (!terminal_core::at_end(args))
      return fail("Unexpected command arguments");
    return Result::action(
        id == CMD_RET ? Kind::RETURN_SCRIPT : Kind::REINIT_CALCULATOR, "");
  case CMD_REG_SET: {
    const int reg = terminal_core::digit_value(line[1], 16);
    mk61_register_init::Value value{};
    if (reg < 0 || !mk61_ref::register_available(reg) ||
        !mk61_register_init::parse(args, value))
      return fail("Invalid register initialization");
    const mk61_ref::Ref target{mk61_ref::Kind::R, (u8)reg};
    bool ok = false;
    if (value.kind == mk61_register_init::Kind::NUMBER)
      ok = fits(value.number) && mk61_ref::write(target, value.number);
    else if (value.kind == mk61_register_init::Kind::RANDOM)
      ok = mk61_ref::write_fraction7(
          target, terminal_script_backend::random_decimal7());
    else if (value.kind == mk61_register_init::Kind::REGISTER) {
      double number = 0;
      ok = read_reference(value.source_register + 1, number) && fits(number) &&
           mk61_ref::write(target, number);
    }
    else
      ok = mk61_ref::write_raw_register(reg, value.raw);
    return ok ? Result::ok() : fail("Cannot write register");
  }
  case CMD_POKE: {
    mk61_ref::Ref ref{};
    double value = 0;
    char name[2] = {args[0], 0};
    if (!args[0] || !terminal_core::is_space(args[1]) ||
        !mk61_ref::parse_name(name, ref) || ref.kind == mk61_ref::Kind::R ||
        !terminal_core::parse_single_decimal(args + 1, value) || !fits(value) ||
        !mk61_ref::write(ref, value))
      return fail("Invalid stack initialization");
    return Result::ok();
  }
  case CMD_HIN:
  case CMD_SET_CODE:
    return hin(id == CMD_SET_CODE ? line + 4 : args)
               ? Result::ok()
               : fail("Invalid HIN data or program address");
  case CMD_ASM:
    return terminal_script_backend::assemble(args, assembly_address)
               ? Result::ok()
               : fail("Invalid assembly or program address");
  case CMD_INS: {
    usize address = 0, opcode = 0;
    if (!terminal_core::parse_unsigned(args, 10, core_61::program_steps() - 1,
                                       address) ||
        !terminal_core::parse_unsigned(args, 16, 255, opcode) ||
        !terminal_core::at_end(args))
      return fail("Invalid INS arguments");
    u8 page[core_61::MAX_PROGRAM_STEP]{};
    const u16 count = (u16)core_61::program_steps();
    for (u16 i = 0; i < count; ++i)
      if (!core_61::read_absolute_program(i, page[i]))
        return Result::error();
    bool operand = false;
    u8 copy = (u8)opcode;
    for (u16 i = (u16)address; i < count; ++i) {
      const u8 moved = page[i];
      if (operand) {
        if (copy >= address)
          ++copy;
        operand = false;
      } else
        operand = core_61::len_code_command(copy) == 2;
      page[i] = copy;
      copy = moved;
    }
    return terminal_script_backend::write_program(0, page, count)
               ? Result::ok()
               : Result::error();
  }
  case CMD_KBD:
  case CMD_CMD: {
    usize value = 0;
    if (!terminal_core::parse_single_unsigned(
            args, 16, id == CMD_KBD ? 0x27 : 0xEF, value))
      return fail("Invalid key or command code");
    if (id == CMD_KBD)
      return terminal_script_backend::press_key((u8)value) ? Result::ok()
                                                           : Result::error();
    u32 sequence = terminal_keys::sequence((u8)value);
    for (unsigned i = 0; i < 4; ++i) {
      const u8 scan = (u8)sequence;
      if (scan == 255)
        break;
      if (!terminal_script_backend::press_key(scan))
        return Result::error();
      sequence >>= 8;
    }
    return Result::ok();
  }
  default:
    return terminal_script_backend::command(id, line, trap);
  }
}
} // namespace terminal_script
