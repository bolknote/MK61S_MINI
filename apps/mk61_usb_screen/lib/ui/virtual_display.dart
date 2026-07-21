import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../protocol/mk61_protocol.dart';

enum DisplayPaletteChoice { green, amber, ice }

extension DisplayPaletteChoiceUi on DisplayPaletteChoice {
  String get label => switch (this) {
    DisplayPaletteChoice.green => 'Зелёный',
    DisplayPaletteChoice.amber => 'Янтарный',
    DisplayPaletteChoice.ice => 'Холодный',
  };

  Color get foreground => switch (this) {
    DisplayPaletteChoice.green => const Color(0xffb9f7a5),
    DisplayPaletteChoice.amber => const Color(0xffffce62),
    DisplayPaletteChoice.ice => const Color(0xffbcecff),
  };

  Color get background => switch (this) {
    DisplayPaletteChoice.green => const Color(0xff102416),
    DisplayPaletteChoice.amber => const Color(0xff281b08),
    DisplayPaletteChoice.ice => const Color(0xff0b1d25),
  };
}

class VirtualDisplay extends StatelessWidget {
  const VirtualDisplay({
    super.key,
    required this.framebuffer,
    required this.revision,
    required this.palette,
    required this.showGrid,
    required this.attached,
    required this.statusText,
  });

  final Uint8List framebuffer;
  final int revision;
  final DisplayPaletteChoice palette;
  final bool showGrid;
  final bool attached;
  final String statusText;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: 'Виртуальный графический экран 192 на 64 пикселя',
      liveRegion: true,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: const Color(0xff080b0d),
          borderRadius: BorderRadius.circular(22),
          border: Border.all(color: const Color(0xff30373b), width: 2),
          boxShadow: const [
            BoxShadow(
              color: Color(0x8a000000),
              blurRadius: 30,
              offset: Offset(0, 16),
            ),
            BoxShadow(
              color: Color(0x1fffffff),
              blurRadius: 1,
              offset: Offset(0, 1),
            ),
          ],
        ),
        child: Padding(
          padding: const EdgeInsets.all(22),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(7),
            child: AspectRatio(
              aspectRatio: MkGeometry.width / MkGeometry.height,
              child: Stack(
                fit: StackFit.expand,
                children: [
                  RepaintBoundary(
                    child: CustomPaint(
                      painter: _DisplayPainter(
                        framebuffer: framebuffer,
                        revision: revision,
                        foreground: palette.foreground,
                        background: palette.background,
                        showGrid: showGrid,
                      ),
                    ),
                  ),
                  if (!attached)
                    ColoredBox(
                      color: const Color(0x9a050707),
                      child: Center(
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 18,
                            vertical: 10,
                          ),
                          decoration: BoxDecoration(
                            color: const Color(0xdc111618),
                            borderRadius: BorderRadius.circular(9),
                            border: Border.all(color: const Color(0xff394246)),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              const SizedBox(
                                width: 16,
                                height: 16,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  color: Color(0xff65d5b0),
                                ),
                              ),
                              const SizedBox(width: 10),
                              Text(
                                statusText,
                                style: Theme.of(context).textTheme.labelLarge
                                    ?.copyWith(color: Colors.white),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _DisplayPainter extends CustomPainter {
  const _DisplayPainter({
    required this.framebuffer,
    required this.revision,
    required this.foreground,
    required this.background,
    required this.showGrid,
  });

  final Uint8List framebuffer;
  final int revision;
  final Color foreground;
  final Color background;
  final bool showGrid;

  @override
  void paint(Canvas canvas, Size size) {
    final scaleX = size.width / MkGeometry.width;
    final scaleY = size.height / MkGeometry.height;
    canvas.drawRect(
      Offset.zero & size,
      Paint()
        ..color = background
        ..isAntiAlias = false,
    );
    canvas.save();
    canvas.scale(scaleX, scaleY);

    final pixelPaint = Paint()
      ..color = foreground
      ..isAntiAlias = false
      ..style = PaintingStyle.fill;
    for (var y = 0; y < MkGeometry.height; y++) {
      final page = y ~/ MkGeometry.pageHeight;
      final mask = 1 << (y & 7);
      var runStart = -1;
      for (var x = 0; x <= MkGeometry.width; x++) {
        final lit =
            x < MkGeometry.width &&
            (framebuffer[page * MkGeometry.width + x] & mask) != 0;
        if (lit && runStart < 0) {
          runStart = x;
        } else if (!lit && runStart >= 0) {
          canvas.drawRect(
            Rect.fromLTWH(
              runStart.toDouble(),
              y.toDouble(),
              (x - runStart).toDouble(),
              1,
            ),
            pixelPaint,
          );
          runStart = -1;
        }
      }
    }

    if (showGrid && scaleX >= 3 && scaleY >= 3) {
      final gridPaint = Paint()
        ..color = background.withValues(alpha: 0.32)
        ..strokeWidth = 0.16
        ..isAntiAlias = false;
      for (var x = 1; x < MkGeometry.width; x++) {
        canvas.drawLine(
          Offset(x.toDouble(), 0),
          Offset(x.toDouble(), MkGeometry.height.toDouble()),
          gridPaint,
        );
      }
      for (var y = 1; y < MkGeometry.height; y++) {
        canvas.drawLine(
          Offset(0, y.toDouble()),
          Offset(MkGeometry.width.toDouble(), y.toDouble()),
          gridPaint,
        );
      }
    }
    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant _DisplayPainter oldDelegate) {
    return revision != oldDelegate.revision ||
        foreground != oldDelegate.foreground ||
        background != oldDelegate.background ||
        showGrid != oldDelegate.showGrid;
  }
}
