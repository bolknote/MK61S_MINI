enum CalculatorKeyKind { digit, operation, shift, navigation, system }

enum CalculatorKeyColorRole { standard, fShift, kShift, clear }

class CalculatorKey {
  const CalculatorKey({
    required this.scanCode,
    required this.action,
    required this.label,
    required this.kind,
    this.hint,
    this.fLegend,
    this.kLegend,
    this.alphaLegend,
    this.neutralLegend,
    this.colorRole = CalculatorKeyColorRole.standard,
  });

  final int scanCode;
  final String action;
  final String label;
  final CalculatorKeyKind kind;
  final String? hint;
  final String? fLegend;
  final String? kLegend;
  final String? alphaLegend;
  final String? neutralLegend;
  final CalculatorKeyColorRole colorRole;
}

class KeyboardDefinition {
  KeyboardDefinition._(this.layout, Map<String, int> scanCodes)
    : _scanCodes = Map.unmodifiable(scanCodes),
      keys = List.unmodifiable(_buildKeys(scanCodes));

  factory KeyboardDefinition.forLayout(int layout) {
    return switch (layout) {
      MkKeyboardLayout.classic => KeyboardDefinition._(layout, _classic),
      MkKeyboardLayout.fortieth => KeyboardDefinition._(layout, _mini),
      _ => KeyboardDefinition._(MkKeyboardLayout.mini, _mini),
    };
  }

  final int layout;
  final Map<String, int> _scanCodes;
  final List<CalculatorKey> keys;

  /// Клавиши в порядке их расположения на физической клавиатуре.
  /// Матричные скан-коды намеренно не зависят от представления.
  List<CalculatorKey> get displayKeys {
    if (layout == MkKeyboardLayout.classic) return keys;
    return List.unmodifiable(
      _miniPhysicalOrder.map((action) => keyForAction(action)),
    );
  }

  int get columnCount => layout == MkKeyboardLayout.classic ? 5 : 8;

  String get name => switch (layout) {
    MkKeyboardLayout.classic => 'Classic',
    MkKeyboardLayout.fortieth => '40th',
    _ => 'Mini',
  };

  int? scanCodeFor(String action) => _scanCodes[action];

  CalculatorKey keyForAction(String action) {
    final scanCode = _scanCodes[action];
    if (scanCode == null) {
      throw StateError('Unknown keyboard action: $action');
    }
    return keys[scanCode];
  }

  CalculatorKey? keyForScanCode(int scanCode) {
    if (scanCode < 0 || scanCode >= keys.length) return null;
    return keys[scanCode];
  }

  static List<CalculatorKey> _buildKeys(Map<String, int> scanCodes) {
    final result = List<CalculatorKey?>.filled(40, null);
    for (final spec in _keySpecs) {
      final scanCode = scanCodes[spec.action];
      if (scanCode == null || scanCode < 0 || scanCode >= result.length) {
        continue;
      }
      result[scanCode] = CalculatorKey(
        scanCode: scanCode,
        action: spec.action,
        label: spec.label,
        kind: spec.kind,
        hint: spec.hint,
        fLegend: spec.fLegend,
        kLegend: spec.kLegend,
        alphaLegend: spec.alphaLegend,
        neutralLegend: spec.neutralLegend,
        colorRole: spec.colorRole,
      );
    }
    for (var scanCode = 0; scanCode < result.length; scanCode++) {
      result[scanCode] ??= CalculatorKey(
        scanCode: scanCode,
        action: 'key$scanCode',
        label: 'K$scanCode',
        kind: CalculatorKeyKind.system,
      );
    }
    return result.cast<CalculatorKey>();
  }

  static const Map<String, int> _mini = {
    'cx': 0,
    'bx': 1,
    'mul': 2,
    'div': 3,
    'degree': 4,
    'power': 5,
    'xy': 6,
    'add': 7,
    'sub': 8,
    'grade': 9,
    'neg': 10,
    'digit3': 11,
    'digit6': 12,
    'digit9': 13,
    'radian': 14,
    'dot': 15,
    'digit2': 16,
    'digit5': 17,
    'digit8': 18,
    'user': 19,
    'digit0': 20,
    'digit1': 21,
    'digit4': 22,
    'digit7': 23,
    'right': 24,
    'pp': 25,
    'bp': 26,
    'xToP': 27,
    'pToX': 28,
    'ok': 29,
    'run': 30,
    'ret': 31,
    'frw': 32,
    'bkw': 33,
    'left': 34,
    'up': 32,
    'down': 33,
    'load': 35,
    'save': 36,
    'k': 37,
    'alpha': 38,
    'esc': 39,
  };

  static const Map<String, int> _classic = {
    'cx': 0,
    'power': 1,
    'neg': 2,
    'dot': 3,
    'digit0': 4,
    'bx': 5,
    'xy': 6,
    'digit3': 7,
    'digit2': 8,
    'digit1': 9,
    'mul': 10,
    'add': 11,
    'digit6': 12,
    'digit5': 13,
    'digit4': 14,
    'div': 15,
    'sub': 16,
    'digit9': 17,
    'digit8': 18,
    'digit7': 19,
    'pp': 20,
    'bp': 21,
    'xToP': 22,
    'pToX': 23,
    'k': 24,
    'run': 25,
    'ret': 26,
    'bkw': 27,
    'frw': 28,
    'alpha': 29,
    'degree': 30,
    'grade': 31,
    'radian': 32,
    'load': 33,
    'save': 34,
    'user': 35,
    'right': 36,
    'ok': 37,
    'left': 38,
    'up': 27,
    'down': 28,
    'esc': 39,
  };

  // Порядок передней панели mk61s-mini/A00: слева направо и сверху вниз.
  // Его нельзя заменять числовым порядком матричных скан-кодов.
  static const List<String> _miniPhysicalOrder = [
    'esc',
    'left',
    'ok',
    'right',
    'user',
    'radian',
    'grade',
    'degree',
    'alpha',
    'bkw',
    'pToX',
    'digit7',
    'digit8',
    'digit9',
    'sub',
    'div',
    'k',
    'frw',
    'xToP',
    'digit4',
    'digit5',
    'digit6',
    'add',
    'mul',
    'load',
    'ret',
    'bp',
    'digit1',
    'digit2',
    'digit3',
    'xy',
    'bx',
    'save',
    'run',
    'pp',
    'digit0',
    'dot',
    'neg',
    'power',
    'cx',
  ];

  static const List<_KeySpec> _keySpecs = [
    _KeySpec(
      'cx',
      'Cx',
      CalculatorKeyKind.system,
      hint: 'Очистить',
      fLegend: 'CF',
      kLegend: 'ИНВ',
      alphaLegend: 'd',
      colorRole: CalculatorKeyColorRole.clear,
    ),
    _KeySpec(
      'bx',
      'В↑',
      CalculatorKeyKind.system,
      hint: 'Ввод экспоненты',
      fLegend: 'Вx',
      kLegend: 'СЧ',
      alphaLegend: 'e',
    ),
    _KeySpec('mul', '×', CalculatorKeyKind.operation, fLegend: 'x²'),
    _KeySpec('div', '÷', CalculatorKeyKind.operation, fLegend: '1/x'),
    _KeySpec(
      'power',
      'ВП',
      CalculatorKeyKind.operation,
      fLegend: 'ПРГ',
      kLegend: '⊕',
      alphaLegend: 'c',
    ),
    _KeySpec(
      'xy',
      '↔',
      CalculatorKeyKind.operation,
      fLegend: 'xʸ',
      kLegend: '°→′″',
    ),
    _KeySpec(
      'add',
      '+',
      CalculatorKeyKind.operation,
      fLegend: 'π',
      kLegend: '°→′',
    ),
    _KeySpec('sub', '−', CalculatorKeyKind.operation, fLegend: '√'),
    _KeySpec(
      'neg',
      '/−/',
      CalculatorKeyKind.operation,
      fLegend: 'АВТ',
      kLegend: '∨',
      alphaLegend: 'b',
    ),
    _KeySpec(
      'dot',
      '·',
      CalculatorKeyKind.digit,
      fLegend: '↻',
      kLegend: '^',
      alphaLegend: 'a',
    ),
    _KeySpec(
      'digit0',
      '0',
      CalculatorKeyKind.digit,
      fLegend: '10ˣ',
      kLegend: 'НОП',
    ),
    _KeySpec('digit1', '1', CalculatorKeyKind.digit, fLegend: 'eˣ'),
    _KeySpec('digit2', '2', CalculatorKeyKind.digit, fLegend: 'lg'),
    _KeySpec(
      'digit3',
      '3',
      CalculatorKeyKind.digit,
      fLegend: 'ln',
      kLegend: '°←′″',
    ),
    _KeySpec(
      'digit4',
      '4',
      CalculatorKeyKind.digit,
      fLegend: 'sin⁻¹',
      kLegend: '|x|',
    ),
    _KeySpec(
      'digit5',
      '5',
      CalculatorKeyKind.digit,
      fLegend: 'cos⁻¹',
      kLegend: 'ЗН',
    ),
    _KeySpec(
      'digit6',
      '6',
      CalculatorKeyKind.digit,
      fLegend: 'tg⁻¹',
      kLegend: '°←′',
    ),
    _KeySpec(
      'digit7',
      '7',
      CalculatorKeyKind.digit,
      fLegend: 'sin',
      kLegend: '[x]',
    ),
    _KeySpec(
      'digit8',
      '8',
      CalculatorKeyKind.digit,
      fLegend: 'cos',
      kLegend: '{x}',
    ),
    _KeySpec(
      'digit9',
      '9',
      CalculatorKeyKind.digit,
      fLegend: 'tg',
      kLegend: 'max',
    ),
    _KeySpec('pp', 'ПП', CalculatorKeyKind.system, fLegend: 'L3'),
    _KeySpec('bp', 'БП', CalculatorKeyKind.system, fLegend: 'L2'),
    _KeySpec('xToP', 'X→П', CalculatorKeyKind.system, fLegend: 'L1'),
    _KeySpec('pToX', 'П→X', CalculatorKeyKind.system, fLegend: 'L0'),
    _KeySpec(
      'run',
      'С/П',
      CalculatorKeyKind.system,
      hint: 'Пуск / стоп',
      fLegend: 'X≠0',
    ),
    _KeySpec(
      'ret',
      'В/О',
      CalculatorKeyKind.system,
      hint: 'Возврат',
      fLegend: 'X≥0',
    ),
    _KeySpec('frw', '←ШГ', CalculatorKeyKind.navigation, fLegend: 'X=0'),
    _KeySpec('bkw', 'ШГ→', CalculatorKeyKind.navigation, fLegend: 'X<0'),
    _KeySpec(
      'k',
      'K',
      CalculatorKeyKind.shift,
      colorRole: CalculatorKeyColorRole.kShift,
    ),
    _KeySpec(
      'alpha',
      'F',
      CalculatorKeyKind.shift,
      colorRole: CalculatorKeyColorRole.fShift,
    ),
    _KeySpec('degree', 'Г', CalculatorKeyKind.operation),
    _KeySpec('grade', 'ГРД', CalculatorKeyKind.operation),
    _KeySpec('radian', 'Р', CalculatorKeyKind.operation),
    _KeySpec('user', '[USER]', CalculatorKeyKind.system),
    _KeySpec('save', 'А↑', CalculatorKeyKind.system, hint: 'SAVE'),
    _KeySpec('load', '↑↓', CalculatorKeyKind.system, hint: 'LOAD'),
    _KeySpec('left', '←', CalculatorKeyKind.navigation),
    _KeySpec('right', '→', CalculatorKeyKind.navigation),
    _KeySpec('ok', 'OK', CalculatorKeyKind.navigation),
    _KeySpec('esc', 'ESC', CalculatorKeyKind.navigation, neutralLegend: 'MENU'),
  ];
}

abstract final class MkKeyboardLayout {
  static const mini = 0;
  static const classic = 1;
  static const fortieth = 2;
}

class _KeySpec {
  const _KeySpec(
    this.action,
    this.label,
    this.kind, {
    this.hint,
    this.fLegend,
    this.kLegend,
    this.alphaLegend,
    this.neutralLegend,
    this.colorRole = CalculatorKeyColorRole.standard,
  });

  final String action;
  final String label;
  final CalculatorKeyKind kind;
  final String? hint;
  final String? fLegend;
  final String? kLegend;
  final String? alphaLegend;
  final String? neutralLegend;
  final CalculatorKeyColorRole colorRole;
}
