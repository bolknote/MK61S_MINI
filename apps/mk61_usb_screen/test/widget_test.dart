import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mk61_usb_screen/device/device_controller.dart';
import 'package:mk61_usb_screen/ui/home_page.dart';

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
}
