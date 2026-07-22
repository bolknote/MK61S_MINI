import 'package:flutter/material.dart';

import '../device/keyboard_definition.dart';

class VirtualKeyboard extends StatelessWidget {
  const VirtualKeyboard({
    super.key,
    required this.definition,
    required this.enabled,
    required this.pressedKeys,
    required this.onKeyDown,
    required this.onKeyUp,
  });

  final KeyboardDefinition definition;
  final bool enabled;
  final Set<int> pressedKeys;
  final ValueChanged<int> onKeyDown;
  final ValueChanged<int> onKeyUp;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        const spacing = 6.0;
        final columns = definition.columnCount;
        final displayKeys = definition.displayKeys;
        final keyWidth =
            (constraints.maxWidth - spacing * (columns - 1)) / columns;
        final keyHeight = columns == 8
            ? (keyWidth * 0.72).clamp(58.0, 76.0).toDouble()
            : (constraints.maxWidth < 600 ? 48.0 : 56.0);
        return GridView.builder(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          itemCount: displayKeys.length,
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: columns,
            mainAxisExtent: keyHeight,
            mainAxisSpacing: spacing,
            crossAxisSpacing: spacing,
          ),
          itemBuilder: (context, index) {
            final key = displayKeys[index];
            return _CalculatorKeyButton(
              key: ValueKey('calculator-key-${key.action}'),
              calculatorKey: key,
              enabled: enabled,
              pressed: pressedKeys.contains(key.scanCode),
              onDown: () => onKeyDown(key.scanCode),
              onUp: () => onKeyUp(key.scanCode),
            );
          },
        );
      },
    );
  }
}

class _CalculatorKeyButton extends StatelessWidget {
  const _CalculatorKeyButton({
    super.key,
    required this.calculatorKey,
    required this.enabled,
    required this.pressed,
    required this.onDown,
    required this.onUp,
  });

  final CalculatorKey calculatorKey;
  final bool enabled;
  final bool pressed;
  final VoidCallback onDown;
  final VoidCallback onUp;

  Color _baseColor() => switch (calculatorKey.kind) {
    CalculatorKeyKind.digit => const Color(0xff30383c),
    CalculatorKeyKind.operation => const Color(0xff3d4347),
    CalculatorKeyKind.shift => const Color(0xff9a6727),
    CalculatorKeyKind.navigation => const Color(0xff245b55),
    CalculatorKeyKind.system => const Color(0xff34313e),
  };

  @override
  Widget build(BuildContext context) {
    final base = _baseColor();
    final foreground = enabled ? Colors.white : const Color(0xff7b8589);
    final button = Listener(
      behavior: HitTestBehavior.opaque,
      onPointerDown: enabled ? (_) => onDown() : null,
      onPointerUp: enabled ? (_) => onUp() : null,
      onPointerCancel: enabled ? (_) => onUp() : null,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 55),
        curve: Curves.easeOut,
        transform: Matrix4.translationValues(0, pressed ? 2 : 0, 0),
        decoration: BoxDecoration(
          color: enabled
              ? (pressed ? Color.lerp(base, Colors.black, 0.28)! : base)
              : const Color(0xff202527),
          borderRadius: BorderRadius.circular(9),
          border: Border.all(
            color: pressed ? const Color(0xff79e2c2) : const Color(0xff4b5559),
          ),
          boxShadow: pressed || !enabled
              ? const []
              : const [
                  BoxShadow(
                    color: Color(0x80000000),
                    blurRadius: 0,
                    offset: Offset(0, 3),
                  ),
                ],
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 4),
          child: Stack(
            fit: StackFit.expand,
            children: [
              if (calculatorKey.neutralLegend case final legend?)
                _KeyLegend(
                  text: legend,
                  alignment: Alignment.topLeft,
                  color: const Color(0xffb8c1c4),
                ),
              if (calculatorKey.fLegend case final legend?)
                _KeyLegend(
                  text: legend,
                  alignment: Alignment.topLeft,
                  color: const Color(0xffffc66d),
                ),
              if (calculatorKey.kLegend case final legend?)
                _KeyLegend(
                  text: legend,
                  alignment: Alignment.topRight,
                  color: const Color(0xff7fe0c7),
                ),
              if (calculatorKey.alphaLegend case final legend?)
                _KeyLegend(
                  text: legend,
                  alignment: Alignment.bottomLeft,
                  color: const Color(0xffa9b5b8),
                ),
              Align(
                alignment:
                    calculatorKey.fLegend != null ||
                        calculatorKey.kLegend != null ||
                        calculatorKey.neutralLegend != null
                    ? const Alignment(0, 0.38)
                    : Alignment.center,
                child: FittedBox(
                  fit: BoxFit.scaleDown,
                  child: Text(
                    calculatorKey.label,
                    maxLines: 1,
                    style: Theme.of(context).textTheme.labelLarge?.copyWith(
                      color: foreground,
                      fontSize: 17,
                      fontWeight: FontWeight.w800,
                      letterSpacing: calculatorKey.label.length <= 2 ? 0.5 : 0,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );

    final hint = calculatorKey.hint;
    if (hint == null) return button;
    return Tooltip(message: hint, child: button);
  }
}

class _KeyLegend extends StatelessWidget {
  const _KeyLegend({
    required this.text,
    required this.alignment,
    required this.color,
  });

  final String text;
  final Alignment alignment;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: alignment,
      child: FittedBox(
        fit: BoxFit.scaleDown,
        child: Text(
          text,
          maxLines: 1,
          style: TextStyle(
            color: color,
            fontSize: 12.5,
            height: 1,
            fontWeight: FontWeight.w800,
          ),
        ),
      ),
    );
  }
}
