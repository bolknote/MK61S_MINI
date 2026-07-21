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
    });
  }
}
