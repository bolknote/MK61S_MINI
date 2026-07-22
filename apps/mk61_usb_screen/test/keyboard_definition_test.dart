import 'package:flutter_test/flutter_test.dart';
import 'package:mk61_usb_screen/device/keyboard_definition.dart';

void main() {
  for (final layout in [
    MkKeyboardLayout.mini,
    MkKeyboardLayout.classic,
    MkKeyboardLayout.fortieth,
  ]) {
    test('layout $layout defines all 40 matrix keys exactly once', () {
      final definition = KeyboardDefinition.forLayout(layout);
      expect(definition.keys, hasLength(40));
      expect(definition.keys.map((key) => key.scanCode).toSet(), hasLength(40));
      expect(
        definition.keys.any((key) => key.action.startsWith('key')),
        isFalse,
      );
      expect(definition.scanCodeFor('ok'), isNotNull);
      expect(definition.scanCodeFor('esc'), isNotNull);
      expect(definition.scanCodeFor('up'), isNotNull);
      expect(definition.scanCodeFor('down'), isNotNull);
      expect(
        definition.scanCodeFor('up'),
        isNot(definition.scanCodeFor('down')),
      );
    });
  }

  test('mini display order mirrors the physical A00 5x8 panel', () {
    final definition = KeyboardDefinition.forLayout(MkKeyboardLayout.mini);

    expect(definition.columnCount, 8);
    expect(definition.displayKeys, hasLength(40));
    expect(definition.displayKeys.take(8).map((key) => key.action), [
      'esc',
      'left',
      'ok',
      'right',
      'user',
      'radian',
      'grade',
      'degree',
    ]);
    expect(definition.displayKeys.skip(8).take(8).map((key) => key.action), [
      'alpha',
      'bkw',
      'pToX',
      'digit7',
      'digit8',
      'digit9',
      'sub',
      'div',
    ]);
    expect(definition.displayKeys.skip(32).map((key) => key.action), [
      'save',
      'run',
      'pp',
      'digit0',
      'dot',
      'neg',
      'power',
      'cx',
    ]);
  });

  test('desktop vertical arrows use the two Mini step keys', () {
    final definition = KeyboardDefinition.forLayout(MkKeyboardLayout.mini);

    expect(definition.scanCodeFor('up'), definition.scanCodeFor('frw'));
    expect(definition.keyForAction('up').label, '←ШГ');
    expect(definition.scanCodeFor('down'), definition.scanCodeFor('bkw'));
    expect(definition.keyForAction('down').label, 'ШГ→');
  });

  test('A00 key faces include the printed shifted and alphabet legends', () {
    final definition = KeyboardDefinition.forLayout(MkKeyboardLayout.mini);

    final seven = definition.keyForAction('digit7');
    expect(seven.label, '7');
    expect(seven.fLegend, 'sin');
    expect(seven.kLegend, '[x]');

    final clear = definition.keyForAction('cx');
    expect(clear.fLegend, 'CF');
    expect(clear.kLegend, 'ИНВ');
    expect(clear.alphaLegend, 'd');

    expect(definition.keyForAction('bkw').label, 'ШГ→');
    expect(definition.keyForAction('frw').label, '←ШГ');
    expect(definition.keyForAction('esc').neutralLegend, 'MENU');
  });

  test('prefix and clear keys expose their authentic color roles', () {
    for (final layout in [
      MkKeyboardLayout.mini,
      MkKeyboardLayout.classic,
      MkKeyboardLayout.fortieth,
    ]) {
      final definition = KeyboardDefinition.forLayout(layout);
      expect(
        definition.keyForAction('alpha').colorRole,
        CalculatorKeyColorRole.fShift,
      );
      expect(
        definition.keyForAction('k').colorRole,
        CalculatorKeyColorRole.kShift,
      );
      expect(
        definition.keyForAction('cx').colorRole,
        CalculatorKeyColorRole.clear,
      );
    }
  });
}
