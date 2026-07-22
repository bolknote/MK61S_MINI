import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mk61_usb_screen/device/device_controller.dart';
import 'package:mk61_usb_screen/device/keyboard_definition.dart';
import 'package:mk61_usb_screen/main.dart';
import 'package:mk61_usb_screen/ui/home_page.dart';

class _RecordingController extends DeviceController {
  final List<List<String>> tappedActions = [];
  final List<int> keyDowns = [];
  final List<int> keyUps = [];
  final List<String> terminalLines = [];
  int releaseAllCount = 0;

  @override
  bool get attached => true;

  @override
  DeviceConnectionState get state => DeviceConnectionState.attached;

  @override
  String get stateLabel => 'USB Screen подключён';

  @override
  bool get terminalAvailable => true;

  @override
  KeyboardDefinition get keyboard =>
      KeyboardDefinition.forLayout(MkKeyboardLayout.mini);

  @override
  bool tapActions(Iterable<String> actions) {
    tappedActions.add(List<String>.of(actions));
    return true;
  }

  @override
  void keyDown(int scanCode) => keyDowns.add(scanCode);

  @override
  void keyUp(int scanCode) => keyUps.add(scanCode);

  @override
  void releaseAllKeys() => releaseAllCount++;

  @override
  bool sendTerminalLine(String line) {
    terminalLines.add(line);
    return true;
  }
}

Future<void> _finishDrawerAnimation(WidgetTester tester) async {
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 200));
}

void main() {
  testWidgets('shows the display and connection guide while offline', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData.dark(useMaterial3: true),
        home: UsbScreenHomePage(
          controller: DeviceController(),
          autoStart: false,
        ),
      ),
    );
    expect(find.text('MK61 USB Screen'), findsOneWidget);
    expect(find.text('Виртуальный дисплей'), findsOneWidget);
    expect(find.text('Как подключить'), findsOneWidget);
    expect(find.text('Терминал'), findsOneWidget);
    expect(find.text('Команда терминала'), findsNothing);
    expect(find.textContaining('клавиатура ПК управляет MK61'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('terminal-toggle')));
    await _finishDrawerAnimation(tester);
    expect(find.text('Команда терминала'), findsOneWidget);
    expect(find.textContaining('ввод клавиатуры направлен'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('terminal-toggle')));
    await _finishDrawerAnimation(tester);
    expect(find.text('Команда терминала'), findsNothing);
  });

  testWidgets('routes PC input by terminal visibility', (tester) async {
    final controller = _RecordingController();
    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData.dark(useMaterial3: true),
        home: UsbScreenHomePage(controller: controller, autoStart: false),
      ),
    );
    await tester.pump();

    await tester.sendKeyEvent(LogicalKeyboardKey.keyA, character: 'a');
    expect(controller.tappedActions, [
      ['k', 'digit8'],
    ]);

    // A Russian input source reports "ф" for the physical A key. Device
    // input must still use the English QWERTY position.
    await tester.sendKeyEvent(
      LogicalKeyboardKey.keyF,
      character: 'ф',
      physicalKey: PhysicalKeyboardKey.keyA,
    );
    expect(controller.tappedActions.last, ['k', 'digit8']);

    await tester.sendKeyDownEvent(LogicalKeyboardKey.shiftLeft);
    await tester.sendKeyEvent(
      LogicalKeyboardKey.digit1,
      character: '!',
      physicalKey: PhysicalKeyboardKey.digit1,
    );
    await tester.sendKeyUpEvent(LogicalKeyboardKey.shiftLeft);
    expect(controller.tappedActions.last, ['alpha', 'digit0']);

    await tester.sendKeyDownEvent(LogicalKeyboardKey.arrowLeft);
    await tester.sendKeyUpEvent(LogicalKeyboardKey.arrowLeft);
    expect(controller.tappedActions.last, ['left']);

    await tester.tap(find.byKey(const ValueKey('terminal-toggle')));
    await _finishDrawerAnimation(tester);
    expect(
      tester
          .widget<TextField>(find.byKey(const ValueKey('terminal-input')))
          .focusNode
          ?.hasFocus,
      isTrue,
    );

    await tester.sendKeyEvent(LogicalKeyboardKey.keyB, character: 'b');
    expect(controller.tappedActions, hasLength(4));

    await tester.enterText(
      find.byKey(const ValueKey('terminal-input')),
      'reg Привет 😀',
    );
    await tester.tap(find.text('Выполнить'));
    expect(controller.terminalLines, ['reg Привет 😀']);

    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await _finishDrawerAnimation(tester);
    expect(find.byKey(const ValueKey('terminal-input')), findsNothing);

    await tester.sendKeyEvent(LogicalKeyboardKey.keyC, character: 'c');
    expect(controller.tappedActions.last, ['k', 'digit8', 'digit8', 'digit8']);
  });

  testWidgets('compact desktop UI fills the whole window', (tester) async {
    tester.view.physicalSize = const Size(800, 600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      Mk61UsbScreenApp(controller: _RecordingController(), autoStart: false),
    );
    await tester.pump();

    final scaffold = find.byType(Scaffold);
    expect(tester.getTopLeft(scaffold), Offset.zero);
    final scaffoldBottomRight = tester.getBottomRight(scaffold);
    expect(scaffoldBottomRight.dx, closeTo(800, 0.01));
    expect(scaffoldBottomRight.dy, closeTo(600, 0.01));

    final terminalToggle = find.byKey(const ValueKey('terminal-toggle'));
    expect(tester.getBottomRight(terminalToggle).dx, lessThanOrEqualTo(800));
    expect(tester.getBottomRight(terminalToggle).dy, lessThanOrEqualTo(600));
    await tester.tap(terminalToggle);
    await _finishDrawerAnimation(tester);
    expect(find.byKey(const ValueKey('terminal-input')), findsOneWidget);
  });

  for (final size in const [Size(500, 800), Size(720, 640), Size(1280, 900)]) {
    testWidgets('offline layout has no overflow at ${size.width.toInt()}px', (
      tester,
    ) async {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(useMaterial3: true),
          home: UsbScreenHomePage(
            controller: DeviceController(),
            autoStart: false,
          ),
        ),
      );
      await tester.pump();
      expect(tester.takeException(), isNull);
    });
  }

  for (final size in const [Size(500, 800), Size(720, 640)]) {
    testWidgets(
      'expanded terminal has no overflow at ${size.width.toInt()}px',
      (tester) async {
        tester.view.physicalSize = size;
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);

        await tester.pumpWidget(
          MaterialApp(
            theme: ThemeData.dark(useMaterial3: true),
            home: UsbScreenHomePage(
              controller: DeviceController(),
              autoStart: false,
            ),
          ),
        );
        await tester.tap(find.byKey(const ValueKey('terminal-toggle')));
        await _finishDrawerAnimation(tester);
        expect(tester.takeException(), isNull);
      },
    );
  }
}
