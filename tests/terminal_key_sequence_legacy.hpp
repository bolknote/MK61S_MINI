#ifndef MK61_TERMINAL_KEY_SEQUENCE_LEGACY_HPP
#define MK61_TERMINAL_KEY_SEQUENCE_LEGACY_HPP

// Characterization of the pre-R4 table. Keep independent of its replacement.
static  constexpr u32 seqNOP = seq(sw::K,sw::_0);
static  const u32 legacy_key_sequences[15*16] = {
  seq(sw::_0),  seq(sw::_1),  seq(sw::_2),  seq(sw::_3),  seq(sw::_4), seq(sw::_5), seq(sw::_6), seq(sw::_7), seq(sw::_8), seq(sw::_9), seq(sw::DOT), seq(sw::NEG), seq(sw::POW), seq(sw::CX), seq(sw::Bx), seq(sw::F,sw::Bx),
  seq(sw::ADD), seq(sw::SUB), seq(sw::MUL), seq(sw::DIV), seq(sw::XY), seq(sw::F,sw::DOT), seq(sw::F,sw::_5), seq(sw::F,sw::_1), seq(sw::F,sw::_2), seq(sw::F,sw::_4), seq(sw::F,sw::_5), seq(sw::F,sw::_6), seq(sw::F,sw::_7), seq(sw::F,sw::_8), seq(sw::F,sw::_9), seqNOP,
  seq(sw::F,sw::ADD),seq(sw::F,sw::SUB),seq(sw::F,sw::MUL),seq(sw::F,sw::DIV),seq(sw::F,sw::XY),seq(sw::F,sw::DOT),seq(sw::K,sw::ADD),seq(sw::K,sw::SUB),seq(sw::K,sw::MUL),seq(sw::K,sw::DIV),seq(sw::K,sw::XY),seqNOP,seqNOP,seqNOP,seqNOP,seqNOP,
  seq(sw::K,sw::_3),seq(sw::K,sw::_4),seq(sw::K,sw::_5),seq(sw::K,sw::_6),seq(sw::K,sw::_7),seq(sw::K,sw::_8),seq(sw::K,sw::_9),seq(sw::K,sw::DOT),seq(sw::K,sw::NEG),seq(sw::K,sw::POW),seq(sw::K,sw::CX),seq(sw::K,sw::Bx),seqNOP,seqNOP,seqNOP,seqNOP,
  seq(sw::xP,sw::_0),seq(sw::xP,sw::_1),seq(sw::xP,sw::_2),seq(sw::xP,sw::_3),seq(sw::xP,sw::_4),seq(sw::xP,sw::_5),seq(sw::xP,sw::_6),seq(sw::xP,sw::_7),seq(sw::xP,sw::_8),seq(sw::xP,sw::_9),seq(sw::xP,sw::DOT),seq(sw::xP,sw::NEG),seq(sw::xP,sw::POW),seq(sw::xP,sw::CX),seq(sw::xP,sw::Bx),seqNOP,
  seq(sw::RUN),seq(sw::JP),seq(sw::RET),seq(sw::JSR),seqNOP,seq(sw::K,sw::_1),seq(sw::K,sw::_2),seq(sw::F,sw::RUN),seq(sw::F,sw::JP),seq(sw::F,sw::RET),seq(sw::F,sw::JSR),seq(sw::F,sw::xP),seq(sw::F,sw::BK),seq(sw::F,sw::Px),seq(sw::F,sw::FW),seqNOP,
  seq(sw::Px,sw::_0),seq(sw::Px,sw::_1),seq(sw::Px,sw::_2),seq(sw::Px,sw::_3),seq(sw::Px,sw::_4),seq(sw::Px,sw::_5),seq(sw::Px,sw::_6),seq(sw::Px,sw::_7),seq(sw::Px,sw::_8),seq(sw::Px,sw::_9),seq(sw::Px,sw::DOT),seq(sw::Px,sw::NEG),seq(sw::Px,sw::POW),seq(sw::Px,sw::CX),seq(sw::Px,sw::Bx),seqNOP,
  seq(sw::K,sw::RUN,sw::_0),seq(sw::K,sw::RUN,sw::_1),seq(sw::K,sw::RUN,sw::_2),seq(sw::K,sw::RUN,sw::_3),seq(sw::K,sw::RUN,sw::_4),seq(sw::K,sw::RUN,sw::_5),seq(sw::K,sw::RUN,sw::_6),seq(sw::K,sw::RUN,sw::_7),
    seq(sw::K,sw::RUN,sw::_8),seq(sw::K,sw::RUN,sw::_9),seq(sw::K,sw::RUN,sw::DOT),seq(sw::K,sw::RUN,sw::NEG),seq(sw::K,sw::RUN,sw::POW),seq(sw::K,sw::RUN,sw::CX),seq(sw::K,sw::RUN,sw::Bx),seqNOP,
  seq(sw::K,sw::JP,sw::_0),seq(sw::K,sw::JP,sw::_1),seq(sw::K,sw::JP,sw::_2),seq(sw::K,sw::JP,sw::_3),seq(sw::K,sw::JP,sw::_4),seq(sw::K,sw::JP,sw::_5),seq(sw::K,sw::JP,sw::_6),seq(sw::K,sw::JP,sw::_7),
    seq(sw::K,sw::JP,sw::_8),seq(sw::K,sw::JP,sw::_9),seq(sw::K,sw::JP,sw::DOT),seq(sw::K,sw::JP,sw::NEG),seq(sw::K,sw::JP,sw::POW),seq(sw::K,sw::JP,sw::CX),seq(sw::K,sw::JP,sw::Bx),seqNOP,
  seq(sw::K,sw::RET,sw::_0),seq(sw::K,sw::RET,sw::_1),seq(sw::K,sw::RET,sw::_2),seq(sw::K,sw::RET,sw::_3),seq(sw::K,sw::RET,sw::_4),seq(sw::K,sw::RET,sw::_5),seq(sw::K,sw::RET,sw::_6),seq(sw::K,sw::RET,sw::_7),
    seq(sw::K,sw::RET,sw::_8),seq(sw::K,sw::RET,sw::_9),seq(sw::K,sw::RET,sw::DOT),seq(sw::K,sw::RET,sw::NEG),seq(sw::K,sw::RET,sw::POW),seq(sw::K,sw::RET,sw::CX),seq(sw::K,sw::RET,sw::Bx),seqNOP,
  seq(sw::K,sw::JSR,sw::_0),seq(sw::K,sw::JSR,sw::_1),seq(sw::K,sw::JSR,sw::_2),seq(sw::K,sw::JSR,sw::_3),seq(sw::K,sw::JSR,sw::_4),seq(sw::K,sw::JSR,sw::_5),seq(sw::K,sw::JSR,sw::_6),seq(sw::K,sw::JSR,sw::_7),
    seq(sw::K,sw::JSR,sw::_8),seq(sw::K,sw::JSR,sw::_9),seq(sw::K,sw::JSR,sw::DOT),seq(sw::K,sw::JSR,sw::NEG),seq(sw::K,sw::JSR,sw::POW),seq(sw::K,sw::JSR,sw::CX),seq(sw::K,sw::JSR,sw::Bx),seqNOP,
  seq(sw::K,sw::xP,sw::_0),seq(sw::K,sw::xP,sw::_1),seq(sw::K,sw::xP,sw::_2),seq(sw::K,sw::xP,sw::_3),seq(sw::K,sw::xP,sw::_4),seq(sw::K,sw::xP,sw::_5),seq(sw::K,sw::xP,sw::_6),seq(sw::K,sw::xP,sw::_7),
    seq(sw::K,sw::xP,sw::_8),seq(sw::K,sw::xP,sw::_9),seq(sw::K,sw::xP,sw::DOT),seq(sw::K,sw::xP,sw::NEG),seq(sw::K,sw::xP,sw::POW),seq(sw::K,sw::xP,sw::CX),seq(sw::K,sw::xP,sw::Bx),seqNOP,
  seq(sw::K,sw::BK,sw::_0),seq(sw::K,sw::BK,sw::_1),seq(sw::K,sw::BK,sw::_2),seq(sw::K,sw::BK,sw::_3),seq(sw::K,sw::BK,sw::_4),seq(sw::K,sw::BK,sw::_5),seq(sw::K,sw::BK,sw::_6),seq(sw::K,sw::BK,sw::_7),
    seq(sw::K,sw::BK,sw::_8),seq(sw::K,sw::BK,sw::_9),seq(sw::K,sw::BK,sw::DOT),seq(sw::K,sw::BK,sw::NEG),seq(sw::K,sw::BK,sw::POW),seq(sw::K,sw::BK,sw::CX),seq(sw::K,sw::BK,sw::Bx),seqNOP,
  seq(sw::K,sw::Px,sw::_0),seq(sw::K,sw::Px,sw::_1),seq(sw::K,sw::Px,sw::_2),seq(sw::K,sw::Px,sw::_3),seq(sw::K,sw::Px,sw::_4),seq(sw::K,sw::Px,sw::_5),seq(sw::K,sw::Px,sw::_6),seq(sw::K,sw::Px,sw::_7),
    seq(sw::K,sw::Px,sw::_8),seq(sw::K,sw::Px,sw::_9),seq(sw::K,sw::Px,sw::DOT),seq(sw::K,sw::Px,sw::NEG),seq(sw::K,sw::Px,sw::POW),seq(sw::K,sw::Px,sw::CX),seq(sw::K,sw::Px,sw::Bx),seqNOP,
  seq(sw::K,sw::FW,sw::_0),seq(sw::K,sw::FW,sw::_1),seq(sw::K,sw::FW,sw::_2),seq(sw::K,sw::FW,sw::_3),seq(sw::K,sw::FW,sw::_4),seq(sw::K,sw::FW,sw::_5),seq(sw::K,sw::FW,sw::_6),seq(sw::K,sw::FW,sw::_7),
    seq(sw::K,sw::FW,sw::_8),seq(sw::K,sw::FW,sw::_9),seq(sw::K,sw::FW,sw::DOT),seq(sw::K,sw::FW,sw::NEG),seq(sw::K,sw::FW,sw::POW),seq(sw::K,sw::FW,sw::CX),seq(sw::K,sw::FW,sw::Bx),seqNOP
};
#endif
