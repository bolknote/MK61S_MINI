enum CalculatorKeyKind { digit, operation, shift, navigation, system }

class CalculatorKey {
  const CalculatorKey({
    required this.scanCode,
    required this.action,
    required this.label,
    required this.kind,
    this.hint,
  });

  final int scanCode;
  final String action;
  final String label;
  final CalculatorKeyKind kind;
  final String? hint;
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

  String get name => switch (layout) {
    MkKeyboardLayout.classic => 'Classic',
    MkKeyboardLayout.fortieth => '40th',
    _ => 'Mini',
  };

  int? scanCodeFor(String action) => _scanCodes[action];

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
    'esc': 39,
  };

  static const List<_KeySpec> _keySpecs = [
    _KeySpec('cx', 'Cx', CalculatorKeyKind.system, 'Очистить'),
    _KeySpec('bx', 'Bx', CalculatorKeyKind.system, 'Ввод экспоненты'),
    _KeySpec('mul', '×', CalculatorKeyKind.operation),
    _KeySpec('div', '÷', CalculatorKeyKind.operation),
    _KeySpec('power', 'xʸ', CalculatorKeyKind.operation),
    _KeySpec('xy', 'x↔y', CalculatorKeyKind.operation),
    _KeySpec('add', '+', CalculatorKeyKind.operation),
    _KeySpec('sub', '−', CalculatorKeyKind.operation),
    _KeySpec('neg', '+/−', CalculatorKeyKind.operation),
    _KeySpec('dot', '·', CalculatorKeyKind.digit),
    _KeySpec('digit0', '0', CalculatorKeyKind.digit),
    _KeySpec('digit1', '1', CalculatorKeyKind.digit),
    _KeySpec('digit2', '2', CalculatorKeyKind.digit),
    _KeySpec('digit3', '3', CalculatorKeyKind.digit),
    _KeySpec('digit4', '4', CalculatorKeyKind.digit),
    _KeySpec('digit5', '5', CalculatorKeyKind.digit),
    _KeySpec('digit6', '6', CalculatorKeyKind.digit),
    _KeySpec('digit7', '7', CalculatorKeyKind.digit),
    _KeySpec('digit8', '8', CalculatorKeyKind.digit),
    _KeySpec('digit9', '9', CalculatorKeyKind.digit),
    _KeySpec('pp', 'ПП', CalculatorKeyKind.system),
    _KeySpec('bp', 'БП', CalculatorKeyKind.system),
    _KeySpec('xToP', 'X→П', CalculatorKeyKind.system),
    _KeySpec('pToX', 'П→X', CalculatorKeyKind.system),
    _KeySpec('run', 'С/П', CalculatorKeyKind.system, 'Пуск / стоп'),
    _KeySpec('ret', 'В/О', CalculatorKeyKind.system, 'Возврат'),
    _KeySpec('frw', 'ПРГ→', CalculatorKeyKind.navigation),
    _KeySpec('bkw', '←ПРГ', CalculatorKeyKind.navigation),
    _KeySpec('k', 'K', CalculatorKeyKind.shift),
    _KeySpec('alpha', 'F', CalculatorKeyKind.shift),
    _KeySpec('degree', '°', CalculatorKeyKind.operation),
    _KeySpec('grade', 'ГРД', CalculatorKeyKind.operation),
    _KeySpec('radian', 'РАД', CalculatorKeyKind.operation),
    _KeySpec('user', 'USER', CalculatorKeyKind.system),
    _KeySpec('save', 'SAVE', CalculatorKeyKind.system),
    _KeySpec('load', 'LOAD', CalculatorKeyKind.system),
    _KeySpec('left', '←', CalculatorKeyKind.navigation),
    _KeySpec('right', '→', CalculatorKeyKind.navigation),
    _KeySpec('ok', 'OK', CalculatorKeyKind.navigation),
    _KeySpec('esc', 'ESC', CalculatorKeyKind.navigation),
  ];
}

abstract final class MkKeyboardLayout {
  static const mini = 0;
  static const classic = 1;
  static const fortieth = 2;
}

class _KeySpec {
  const _KeySpec(this.action, this.label, this.kind, [this.hint]);

  final String action;
  final String label;
  final CalculatorKeyKind kind;
  final String? hint;
}
