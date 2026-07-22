import 'package:flutter/services.dart';

/// Maps printable desktop-keyboard characters to short sequences of MK61
/// matrix-key actions.  Text editors already understand these combinations,
/// including the K+digit multi-tap alphabet, so the wire protocol remains the
/// same as for the on-screen keyboard.
abstract final class HostKeyboardMapping {
  static final Map<PhysicalKeyboardKey, ({String plain, String shifted})>
  _englishQwerty = {
    PhysicalKeyboardKey.keyA: (plain: 'a', shifted: 'A'),
    PhysicalKeyboardKey.keyB: (plain: 'b', shifted: 'B'),
    PhysicalKeyboardKey.keyC: (plain: 'c', shifted: 'C'),
    PhysicalKeyboardKey.keyD: (plain: 'd', shifted: 'D'),
    PhysicalKeyboardKey.keyE: (plain: 'e', shifted: 'E'),
    PhysicalKeyboardKey.keyF: (plain: 'f', shifted: 'F'),
    PhysicalKeyboardKey.keyG: (plain: 'g', shifted: 'G'),
    PhysicalKeyboardKey.keyH: (plain: 'h', shifted: 'H'),
    PhysicalKeyboardKey.keyI: (plain: 'i', shifted: 'I'),
    PhysicalKeyboardKey.keyJ: (plain: 'j', shifted: 'J'),
    PhysicalKeyboardKey.keyK: (plain: 'k', shifted: 'K'),
    PhysicalKeyboardKey.keyL: (plain: 'l', shifted: 'L'),
    PhysicalKeyboardKey.keyM: (plain: 'm', shifted: 'M'),
    PhysicalKeyboardKey.keyN: (plain: 'n', shifted: 'N'),
    PhysicalKeyboardKey.keyO: (plain: 'o', shifted: 'O'),
    PhysicalKeyboardKey.keyP: (plain: 'p', shifted: 'P'),
    PhysicalKeyboardKey.keyQ: (plain: 'q', shifted: 'Q'),
    PhysicalKeyboardKey.keyR: (plain: 'r', shifted: 'R'),
    PhysicalKeyboardKey.keyS: (plain: 's', shifted: 'S'),
    PhysicalKeyboardKey.keyT: (plain: 't', shifted: 'T'),
    PhysicalKeyboardKey.keyU: (plain: 'u', shifted: 'U'),
    PhysicalKeyboardKey.keyV: (plain: 'v', shifted: 'V'),
    PhysicalKeyboardKey.keyW: (plain: 'w', shifted: 'W'),
    PhysicalKeyboardKey.keyX: (plain: 'x', shifted: 'X'),
    PhysicalKeyboardKey.keyY: (plain: 'y', shifted: 'Y'),
    PhysicalKeyboardKey.keyZ: (plain: 'z', shifted: 'Z'),
    PhysicalKeyboardKey.digit1: (plain: '1', shifted: '!'),
    PhysicalKeyboardKey.digit2: (plain: '2', shifted: '@'),
    PhysicalKeyboardKey.digit3: (plain: '3', shifted: '#'),
    PhysicalKeyboardKey.digit4: (plain: '4', shifted: r'$'),
    PhysicalKeyboardKey.digit5: (plain: '5', shifted: '%'),
    PhysicalKeyboardKey.digit6: (plain: '6', shifted: '^'),
    PhysicalKeyboardKey.digit7: (plain: '7', shifted: '&'),
    PhysicalKeyboardKey.digit8: (plain: '8', shifted: '*'),
    PhysicalKeyboardKey.digit9: (plain: '9', shifted: '('),
    PhysicalKeyboardKey.digit0: (plain: '0', shifted: ')'),
    PhysicalKeyboardKey.space: (plain: ' ', shifted: ' '),
    PhysicalKeyboardKey.minus: (plain: '-', shifted: '_'),
    PhysicalKeyboardKey.equal: (plain: '=', shifted: '+'),
    PhysicalKeyboardKey.bracketLeft: (plain: '[', shifted: '{'),
    PhysicalKeyboardKey.bracketRight: (plain: ']', shifted: '}'),
    PhysicalKeyboardKey.backslash: (plain: r'\', shifted: '|'),
    PhysicalKeyboardKey.semicolon: (plain: ';', shifted: ':'),
    PhysicalKeyboardKey.quote: (plain: "'", shifted: '"'),
    PhysicalKeyboardKey.backquote: (plain: '`', shifted: '~'),
    PhysicalKeyboardKey.comma: (plain: ',', shifted: '<'),
    PhysicalKeyboardKey.period: (plain: '.', shifted: '>'),
    PhysicalKeyboardKey.slash: (plain: '/', shifted: '?'),
  };

  static const Map<String, List<String>> _direct = {
    ' ': ['pp'],
    '0': ['digit0'],
    '1': ['digit1'],
    '2': ['digit2'],
    '3': ['digit3'],
    '4': ['digit4'],
    '5': ['digit5'],
    '6': ['digit6'],
    '7': ['digit7'],
    '8': ['digit8'],
    '9': ['digit9'],
    '.': ['dot'],
    '+': ['add'],
    '-': ['sub'],
    '/': ['div'],
    '!': ['alpha', 'digit0'],
    '@': ['alpha', 'digit1'],
    '#': ['alpha', 'digit2'],
    r'$': ['alpha', 'digit3'],
    '%': ['alpha', 'digit4'],
    '^': ['power'],
    '&': ['alpha', 'digit6'],
    '*': ['mul'],
    '(': ['alpha', 'digit8'],
    ')': ['alpha', 'digit9'],
    ':': ['k', 'ok'],
    ';': ['k', 'ret'],
    ',': ['k', 'pp'],
    '"': ['k', 'xy'],
    '=': ['k', 'add'],
    "'": ['k', 'dot'],
    '<': ['k', 'up'],
    '>': ['k', 'sub'],
  };

  static const Map<String, String> _letterKeys = {
    'A': 'digit8',
    'B': 'digit8',
    'C': 'digit8',
    'D': 'digit9',
    'E': 'digit9',
    'F': 'digit9',
    'G': 'digit4',
    'H': 'digit4',
    'I': 'digit4',
    'J': 'digit5',
    'K': 'digit5',
    'L': 'digit5',
    'M': 'digit6',
    'N': 'digit6',
    'O': 'digit6',
    'P': 'digit1',
    'Q': 'digit1',
    'R': 'digit1',
    'S': 'digit1',
    'T': 'digit2',
    'U': 'digit2',
    'V': 'digit2',
    'W': 'digit3',
    'X': 'digit3',
    'Y': 'digit3',
    'Z': 'digit3',
  };

  static const Map<String, int> _letterTap = {
    'A': 1,
    'B': 2,
    'C': 3,
    'D': 1,
    'E': 2,
    'F': 3,
    'G': 1,
    'H': 2,
    'I': 3,
    'J': 1,
    'K': 2,
    'L': 3,
    'M': 1,
    'N': 2,
    'O': 3,
    'P': 1,
    'Q': 2,
    'R': 3,
    'S': 4,
    'T': 1,
    'U': 2,
    'V': 3,
    'W': 1,
    'X': 2,
    'Y': 3,
    'Z': 4,
  };

  /// Returns matrix actions for one supported printable character.
  /// Latin lower-case input deliberately becomes upper-case because that is
  /// the alphabet exposed by the firmware text editors.
  static List<String>? actionsForCharacter(String? character) {
    if (character == null || character.runes.length != 1) return null;
    final direct = _direct[character];
    if (direct != null) return direct;

    final upper = character.toUpperCase();
    final digit = _letterKeys[upper];
    final taps = _letterTap[upper];
    if (digit == null || taps == null) return null;
    return <String>['k', ...List<String>.filled(taps, digit)];
  }

  static bool isSupported(String? character) =>
      actionsForCharacter(character) != null;

  /// Returns the US-QWERTY character printed on a physical key. This bypasses
  /// the active OS input source while the PC keyboard controls the device.
  /// Unsupported English punctuation is still returned so callers can consume
  /// it instead of accidentally falling back to an IME-produced character.
  static String? englishCharacterForPhysicalKey(
    PhysicalKeyboardKey key, {
    required bool shift,
  }) {
    final pair = _englishQwerty[key];
    if (pair == null) return null;
    return shift ? pair.shifted : pair.plain;
  }
}
