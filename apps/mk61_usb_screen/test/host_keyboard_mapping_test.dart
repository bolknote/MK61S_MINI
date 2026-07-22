import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mk61_usb_screen/device/host_keyboard_mapping.dart';
import 'package:mk61_usb_screen/device/keyboard_definition.dart';

void main() {
  test('maps Latin letters through the firmware multi-tap alphabet', () {
    expect(HostKeyboardMapping.actionsForCharacter('A'), ['k', 'digit8']);
    expect(HostKeyboardMapping.actionsForCharacter('b'), [
      'k',
      'digit8',
      'digit8',
    ]);
    expect(HostKeyboardMapping.actionsForCharacter('S'), [
      'k',
      'digit1',
      'digit1',
      'digit1',
      'digit1',
    ]);
    expect(HostKeyboardMapping.actionsForCharacter('z'), [
      'k',
      'digit3',
      'digit3',
      'digit3',
      'digit3',
    ]);
  });

  test('maps supported printable symbols and rejects unsupported input', () {
    expect(HostKeyboardMapping.actionsForCharacter('5'), ['digit5']);
    expect(HostKeyboardMapping.actionsForCharacter(' '), ['pp']);
    expect(HostKeyboardMapping.actionsForCharacter('*'), ['mul']);
    expect(HostKeyboardMapping.actionsForCharacter(':'), ['k', 'ok']);
    expect(HostKeyboardMapping.actionsForCharacter('@'), ['alpha', 'digit1']);
    expect(HostKeyboardMapping.actionsForCharacter('<'), ['k', 'up']);
    expect(HostKeyboardMapping.actionsForCharacter('Ж'), isNull);
    expect(HostKeyboardMapping.actionsForCharacter('😀'), isNull);
    expect(HostKeyboardMapping.actionsForCharacter('\n'), isNull);
    expect(HostKeyboardMapping.actionsForCharacter('AB'), isNull);
  });

  test('derives English QWERTY text from physical keys', () {
    expect(
      HostKeyboardMapping.englishCharacterForPhysicalKey(
        PhysicalKeyboardKey.keyA,
        shift: false,
      ),
      'a',
    );
    expect(
      HostKeyboardMapping.englishCharacterForPhysicalKey(
        PhysicalKeyboardKey.digit2,
        shift: true,
      ),
      '@',
    );
    expect(
      HostKeyboardMapping.englishCharacterForPhysicalKey(
        PhysicalKeyboardKey.semicolon,
        shift: true,
      ),
      ':',
    );
    expect(
      HostKeyboardMapping.englishCharacterForPhysicalKey(
        PhysicalKeyboardKey.arrowLeft,
        shift: false,
      ),
      isNull,
    );
  });

  test('every mapped action resolves on every supported keyboard layout', () {
    const characters =
        ' ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.+-/!@#\$%^&*():;,"=\'<>';

    for (final layout in [
      MkKeyboardLayout.mini,
      MkKeyboardLayout.classic,
      MkKeyboardLayout.fortieth,
    ]) {
      final keyboard = KeyboardDefinition.forLayout(layout);
      for (final character in characters.split('')) {
        final actions = HostKeyboardMapping.actionsForCharacter(character);
        expect(actions, isNotNull, reason: 'layout=$layout char=$character');
        for (final action in actions!) {
          expect(
            keyboard.scanCodeFor(action),
            isNotNull,
            reason: 'layout=$layout char=$character action=$action',
          );
        }
      }
    }
  });
}
