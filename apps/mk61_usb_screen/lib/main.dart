import 'package:flutter/material.dart';

import 'device/device_controller.dart';
import 'ui/home_page.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const Mk61UsbScreenApp());
}

class Mk61UsbScreenApp extends StatelessWidget {
  const Mk61UsbScreenApp({super.key, this.controller, this.autoStart = true});

  static const double _desktopUiScale = 0.6;
  static const double _desktopTextScale = 1.3;

  final DeviceController? controller;
  final bool autoStart;

  @override
  Widget build(BuildContext context) {
    const colorScheme = ColorScheme.dark(
      primary: Color(0xff79e2c2),
      onPrimary: Color(0xff09211b),
      secondary: Color(0xffffc66d),
      surface: Color(0xff111517),
      onSurface: Color(0xffedf3f4),
      error: Color(0xffff9da4),
    );
    final baseTheme = ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: const Color(0xff0b0f11),
    );
    return MaterialApp(
      title: 'MK61 USB Screen',
      debugShowCheckedModeBanner: false,
      builder: (context, child) => _ScaledDesktopUi(
        scale: _desktopUiScale,
        textScale: _desktopTextScale,
        child: child ?? const SizedBox.shrink(),
      ),
      theme: baseTheme.copyWith(
        textTheme: baseTheme.textTheme.copyWith(
          headlineSmall: baseTheme.textTheme.headlineSmall?.copyWith(
            fontWeight: FontWeight.w700,
            letterSpacing: -0.4,
          ),
          titleLarge: baseTheme.textTheme.titleLarge?.copyWith(
            fontWeight: FontWeight.w700,
          ),
        ),
        inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: const Color(0xff0d1214),
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(10),
            borderSide: const BorderSide(color: Color(0xff394246)),
          ),
          enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(10),
            borderSide: const BorderSide(color: Color(0xff394246)),
          ),
          contentPadding: const EdgeInsets.symmetric(
            horizontal: 13,
            vertical: 12,
          ),
        ),
        expansionTileTheme: const ExpansionTileThemeData(
          shape: Border(),
          collapsedShape: Border(),
        ),
        tooltipTheme: TooltipThemeData(
          waitDuration: const Duration(milliseconds: 450),
          decoration: BoxDecoration(
            color: const Color(0xff263034),
            borderRadius: BorderRadius.circular(7),
          ),
        ),
      ),
      home: UsbScreenHomePage(
        controller: controller ?? DeviceController(),
        autoStart: autoStart,
      ),
    );
  }
}

/// Flutter's Material controls are deliberately touch-sized.  The MK61
/// client is a dense desktop instrument, so render its whole logical surface
/// more compactly while giving the child proportionally more layout space.
/// Text is compensated separately to remain readable on desktop displays.
/// Keeping the scaling at this single boundary also scales overlays, pointer
/// hit testing and text-field caret geometry consistently.
class _ScaledDesktopUi extends StatelessWidget {
  const _ScaledDesktopUi({
    required this.scale,
    required this.textScale,
    required this.child,
  });

  final double scale;
  final double textScale;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final media = MediaQuery.of(context);
    return LayoutBuilder(
      builder: (context, constraints) {
        final viewport = Size(
          constraints.maxWidth.isFinite
              ? constraints.maxWidth
              : media.size.width,
          constraints.maxHeight.isFinite
              ? constraints.maxHeight
              : media.size.height,
        );
        final logicalSize = Size(
          viewport.width / scale,
          viewport.height / scale,
        );
        return FittedBox(
          fit: BoxFit.fill,
          alignment: Alignment.topLeft,
          clipBehavior: Clip.hardEdge,
          child: SizedBox.fromSize(
            size: logicalSize,
            child: MediaQuery(
              data: media.copyWith(
                size: logicalSize,
                textScaler: TextScaler.linear(textScale),
              ),
              child: child,
            ),
          ),
        );
      },
    );
  }
}
