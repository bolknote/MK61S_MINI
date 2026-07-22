import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../device/device_controller.dart';
import '../device/host_keyboard_mapping.dart';
import '../protocol/mk61_protocol.dart';
import 'virtual_display.dart';
import 'virtual_keyboard.dart';

class UsbScreenHomePage extends StatefulWidget {
  const UsbScreenHomePage({
    super.key,
    required this.controller,
    this.autoStart = true,
  });

  final DeviceController controller;
  final bool autoStart;

  @override
  State<UsbScreenHomePage> createState() => _UsbScreenHomePageState();
}

class _UsbScreenHomePageState extends State<UsbScreenHomePage>
    with WidgetsBindingObserver {
  final FocusNode _keyboardFocus = FocusNode(debugLabel: 'calculator keyboard');
  final FocusNode _terminalFocus = FocusNode(debugLabel: 'USB terminal input');
  final TextEditingController _terminalInput = TextEditingController();
  final ScrollController _terminalScroll = ScrollController();
  DisplayPaletteChoice _palette = DisplayPaletteChoice.green;
  bool _showGrid = false;
  bool _terminalExpanded = false;

  DeviceController get controller => widget.controller;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    controller.addListener(_controllerChanged);
    controller.terminalChanges.addListener(_terminalChanged);
    if (widget.autoStart) controller.start();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state != AppLifecycleState.resumed) _releasePhysicalKeys();
  }

  void _controllerChanged() {
    if (!mounted) return;
    setState(() {});
  }

  void _terminalChanged() {
    if (!mounted || !_terminalExpanded) return;
    WidgetsBinding.instance.addPostFrameCallback((_) => _scrollTerminal());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _releasePhysicalKeys();
    controller.removeListener(_controllerChanged);
    controller.terminalChanges.removeListener(_terminalChanged);
    controller.dispose();
    _keyboardFocus.dispose();
    _terminalFocus.dispose();
    _terminalInput.dispose();
    _terminalScroll.dispose();
    super.dispose();
  }

  void _releasePhysicalKeys() {
    controller.releaseAllKeys();
  }

  void _setTerminalExpanded(bool expanded) {
    if (_terminalExpanded == expanded) return;
    _releasePhysicalKeys();
    setState(() => _terminalExpanded = expanded);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      if (expanded) {
        _terminalFocus.requestFocus();
        _scrollTerminal();
      } else {
        _keyboardFocus.requestFocus();
      }
    });
  }

  KeyEventResult _onKeyEvent(FocusNode _, KeyEvent event) {
    if (_terminalExpanded || _terminalFocus.hasFocus) {
      return KeyEventResult.ignored;
    }

    final action = _actionForLogicalKey(event.logicalKey);
    final isArrow =
        event.logicalKey == LogicalKeyboardKey.arrowLeft ||
        event.logicalKey == LogicalKeyboardKey.arrowRight ||
        event.logicalKey == LogicalKeyboardKey.arrowUp ||
        event.logicalKey == LogicalKeyboardKey.arrowDown;

    // An event handled here must not continue into Flutter's focus traversal
    // or ScrollView shortcuts.  Consume arrow key-up as well as key-down even
    // while offline, so arrows never become application navigation while the
    // terminal drawer is hidden.
    if (event is KeyUpEvent) {
      return isArrow ? KeyEventResult.handled : KeyEventResult.ignored;
    }
    if (event is! KeyDownEvent && event is! KeyRepeatEvent) {
      return KeyEventResult.ignored;
    }

    final hardwareKeyboard = HardwareKeyboard.instance;
    if (hardwareKeyboard.isMetaPressed ||
        hardwareKeyboard.isControlPressed ||
        hardwareKeyboard.isAltPressed) {
      return isArrow ? KeyEventResult.handled : KeyEventResult.ignored;
    }
    final englishCharacter = HostKeyboardMapping.englishCharacterForPhysicalKey(
      event.physicalKey,
      shift: hardwareKeyboard.isShiftPressed,
    );
    if (englishCharacter != null) {
      final actions = HostKeyboardMapping.actionsForCharacter(englishCharacter);
      if (actions != null && controller.attached) {
        controller.tapActions(actions);
      }
      return KeyEventResult.handled;
    }
    if (action != null) {
      if (controller.attached) controller.tapActions([action]);
      return KeyEventResult.handled;
    }
    return KeyEventResult.ignored;
  }

  void _scrollTerminal() {
    if (!mounted || !_terminalScroll.hasClients) return;
    _terminalScroll.jumpTo(_terminalScroll.position.maxScrollExtent);
  }

  void _submitTerminal([String? value]) {
    final command = value ?? _terminalInput.text;
    if (!controller.sendTerminalLine(command)) return;
    _terminalInput.clear();
    _terminalFocus.requestFocus();
  }

  String? _actionForLogicalKey(LogicalKeyboardKey key) {
    final digits = {
      LogicalKeyboardKey.digit0: 'digit0',
      LogicalKeyboardKey.digit1: 'digit1',
      LogicalKeyboardKey.digit2: 'digit2',
      LogicalKeyboardKey.digit3: 'digit3',
      LogicalKeyboardKey.digit4: 'digit4',
      LogicalKeyboardKey.digit5: 'digit5',
      LogicalKeyboardKey.digit6: 'digit6',
      LogicalKeyboardKey.digit7: 'digit7',
      LogicalKeyboardKey.digit8: 'digit8',
      LogicalKeyboardKey.digit9: 'digit9',
      LogicalKeyboardKey.numpad0: 'digit0',
      LogicalKeyboardKey.numpad1: 'digit1',
      LogicalKeyboardKey.numpad2: 'digit2',
      LogicalKeyboardKey.numpad3: 'digit3',
      LogicalKeyboardKey.numpad4: 'digit4',
      LogicalKeyboardKey.numpad5: 'digit5',
      LogicalKeyboardKey.numpad6: 'digit6',
      LogicalKeyboardKey.numpad7: 'digit7',
      LogicalKeyboardKey.numpad8: 'digit8',
      LogicalKeyboardKey.numpad9: 'digit9',
    };
    final digit = digits[key];
    if (digit != null) return digit;
    if (key == LogicalKeyboardKey.period ||
        key == LogicalKeyboardKey.numpadDecimal) {
      return 'dot';
    }
    if (key == LogicalKeyboardKey.add || key == LogicalKeyboardKey.numpadAdd) {
      return 'add';
    }
    if (key == LogicalKeyboardKey.minus ||
        key == LogicalKeyboardKey.numpadSubtract) {
      return 'sub';
    }
    if (key == LogicalKeyboardKey.asterisk ||
        key == LogicalKeyboardKey.numpadMultiply) {
      return 'mul';
    }
    if (key == LogicalKeyboardKey.slash ||
        key == LogicalKeyboardKey.numpadDivide) {
      return 'div';
    }
    if (key == LogicalKeyboardKey.enter ||
        key == LogicalKeyboardKey.numpadEnter) {
      return 'ok';
    }
    if (key == LogicalKeyboardKey.escape) return 'esc';
    if (key == LogicalKeyboardKey.arrowLeft) return 'left';
    if (key == LogicalKeyboardKey.arrowRight) return 'right';
    if (key == LogicalKeyboardKey.arrowUp) return 'up';
    if (key == LogicalKeyboardKey.arrowDown) return 'down';
    if (key == LogicalKeyboardKey.backspace ||
        key == LogicalKeyboardKey.delete) {
      return 'cx';
    }
    if (key == LogicalKeyboardKey.space) return 'pp';
    if (key == LogicalKeyboardKey.f1) return 'k';
    if (key == LogicalKeyboardKey.f2) return 'alpha';
    if (key == LogicalKeyboardKey.f3) return 'user';
    if (key == LogicalKeyboardKey.f5) return 'run';
    if (key == LogicalKeyboardKey.f6) return 'save';
    if (key == LogicalKeyboardKey.f7) return 'load';
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final caps = controller.capabilities;
    return Scaffold(
      bottomNavigationBar: _buildTerminalDrawer(context),
      body: SafeArea(
        child: Focus(
          focusNode: _keyboardFocus,
          autofocus: true,
          onKeyEvent: _onKeyEvent,
          child: GestureDetector(
            behavior: HitTestBehavior.translucent,
            onTap: () {
              if (!_terminalExpanded) _keyboardFocus.requestFocus();
            },
            child: CustomScrollView(
              slivers: [
                SliverPadding(
                  padding: const EdgeInsets.fromLTRB(24, 22, 24, 40),
                  sliver: SliverToBoxAdapter(
                    child: Center(
                      child: ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 1240),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            _buildHeader(context),
                            const SizedBox(height: 18),
                            _buildConnectionPanel(context),
                            if (controller.lastError != null) ...[
                              const SizedBox(height: 12),
                              _buildError(context, controller.lastError!),
                            ],
                            const SizedBox(height: 18),
                            _buildDisplayHeader(context, caps),
                            const SizedBox(height: 10),
                            ValueListenableBuilder<int>(
                              valueListenable: controller.displayChanges,
                              builder: (context, revision, child) {
                                return VirtualDisplay(
                                  framebuffer: controller.framebuffer,
                                  revision: revision,
                                  palette: _palette,
                                  showGrid: _showGrid,
                                  attached: controller.attached,
                                  statusText: controller.stateLabel,
                                );
                              },
                            ),
                            if (!controller.attached) ...[
                              const SizedBox(height: 16),
                              _buildConnectionGuide(context),
                            ],
                            const SizedBox(height: 22),
                            _buildKeyboardPanel(context),
                            const SizedBox(height: 18),
                            ValueListenableBuilder<int>(
                              valueListenable: controller.displayChanges,
                              builder: (context, revision, child) =>
                                  _buildDiagnostics(context),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildHeader(BuildContext context) {
    return Row(
      children: [
        Container(
          width: 48,
          height: 48,
          decoration: BoxDecoration(
            color: const Color(0xff163b34),
            borderRadius: BorderRadius.circular(13),
            border: Border.all(color: const Color(0xff2a695e)),
          ),
          child: const Icon(Icons.monitor_rounded, color: Color(0xff79e2c2)),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'MK61 USB Screen',
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              const SizedBox(height: 2),
              Text(
                'Графический экран 192×64 и виртуальная клавиатура',
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: const Color(0xff9ba7ab),
                ),
              ),
            ],
          ),
        ),
        _StatusBadge(
          text: controller.stateLabel,
          active: controller.attached,
          busy:
              controller.state != DeviceConnectionState.disconnected &&
              controller.state != DeviceConnectionState.error &&
              !controller.attached,
        ),
      ],
    );
  }

  Widget _buildConnectionPanel(BuildContext context) {
    final selected = controller.ports.contains(controller.selectedPort)
        ? controller.selectedPort
        : null;
    return _Panel(
      child: Wrap(
        spacing: 14,
        runSpacing: 12,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          SizedBox(
            width: 320,
            child: DropdownButtonFormField<String>(
              initialValue: selected,
              isExpanded: true,
              decoration: const InputDecoration(
                labelText: 'Последовательный порт',
                prefixIcon: Icon(Icons.usb_rounded),
              ),
              hint: const Text('USB-устройство не найдено'),
              items: controller.ports
                  .map(
                    (port) => DropdownMenuItem(
                      value: port,
                      child: Text(port, overflow: TextOverflow.ellipsis),
                    ),
                  )
                  .toList(),
              onChanged: controller.hasOpenPort ? null : controller.selectPort,
            ),
          ),
          FilterChip(
            selected: controller.autoConnect,
            onSelected: controller.setAutoConnect,
            avatar: const Icon(Icons.radar_rounded, size: 18),
            label: const Text('Автоподключение'),
          ),
          OutlinedButton.icon(
            onPressed: controller.hasOpenPort
                ? null
                : () => controller.refreshPorts(),
            icon: const Icon(Icons.refresh_rounded),
            label: const Text('Обновить'),
          ),
          if (controller.canRequestUsbScreen)
            FilledButton.icon(
              onPressed: controller.requestUsbScreen,
              icon: const Icon(Icons.monitor_rounded),
              label: const Text('Включить USB Screen'),
            ),
          if (controller.hasOpenPort)
            FilledButton.tonalIcon(
              onPressed: () => controller.disconnect(),
              icon: const Icon(Icons.link_off_rounded),
              label: const Text('Отключить'),
            )
          else
            FilledButton.icon(
              onPressed: selected == null
                  ? null
                  : () => controller.connectSelected(),
              icon: const Icon(Icons.cable_rounded),
              label: const Text('Подключить'),
            ),
        ],
      ),
    );
  }

  Widget _buildDisplayHeader(
    BuildContext context,
    DeviceCapabilities? capabilities,
  ) {
    final profile = capabilities?.textRows == null
        ? 'UC1609-view'
        : '${capabilities!.textRows} строк · '
              '${capabilities.glyphWidth}×${capabilities.glyphHeight}';
    return Wrap(
      alignment: WrapAlignment.spaceBetween,
      crossAxisAlignment: WrapCrossAlignment.center,
      runSpacing: 10,
      children: [
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Виртуальный дисплей',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            Text(
              '192×64 · $profile',
              style: Theme.of(
                context,
              ).textTheme.bodySmall?.copyWith(color: const Color(0xff8e999d)),
            ),
          ],
        ),
        Wrap(
          spacing: 8,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            DropdownButton<DisplayPaletteChoice>(
              value: _palette,
              underline: const SizedBox.shrink(),
              borderRadius: BorderRadius.circular(10),
              items: DisplayPaletteChoice.values
                  .map(
                    (choice) => DropdownMenuItem(
                      value: choice,
                      child: Text(choice.label),
                    ),
                  )
                  .toList(),
              onChanged: (choice) {
                if (choice != null) setState(() => _palette = choice);
              },
            ),
            FilterChip(
              selected: _showGrid,
              onSelected: (value) => setState(() => _showGrid = value),
              avatar: const Icon(Icons.grid_on_rounded, size: 17),
              label: const Text('Пиксели'),
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildConnectionGuide(BuildContext context) {
    return _Panel(
      color: const Color(0xff121b1d),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Как подключить',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 12),
          const Wrap(
            spacing: 16,
            runSpacing: 10,
            children: [
              _GuideStep(number: '1', text: 'Подключите MK61 по USB'),
              _GuideStep(number: '2', text: 'Запустите приложение'),
              _GuideStep(
                number: '3',
                text: 'USB Screen включится автоматически',
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            'Физический экран погаснет только после успешного handshake. '
            'Пункт «Разработка → USB-экран» остаётся ручным способом входа.',
            style: Theme.of(
              context,
            ).textTheme.bodySmall?.copyWith(color: const Color(0xffa7b2b5)),
          ),
        ],
      ),
    );
  }

  Widget _buildKeyboardPanel(BuildContext context) {
    return _Panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Виртуальная клавиатура',
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                    Text(
                      '${controller.keyboard.name} · мышь, touch и клавиши ПК',
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: const Color(0xff8e999d),
                      ),
                    ),
                  ],
                ),
              ),
              if (controller.pressedKeys.isNotEmpty)
                TextButton.icon(
                  onPressed: controller.releaseAllKeys,
                  icon: const Icon(Icons.pan_tool_alt_outlined),
                  label: const Text('Отпустить все'),
                ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            'ПК: фиксированная EN/QWERTY независимо от раскладки macOS · '
            'A–Z, 0–9, знаки, пробел, ←↑↓→, Backspace, Enter, Esc · '
            'F1=K, F2=F, F3=USER, F5=С/П, F6=SAVE, F7=LOAD',
            style: Theme.of(
              context,
            ).textTheme.bodySmall?.copyWith(color: const Color(0xffa8b3b6)),
          ),
          const SizedBox(height: 16),
          VirtualKeyboard(
            definition: controller.keyboard,
            enabled: controller.attached,
            pressedKeys: controller.pressedKeys,
            onKeyDown: controller.keyDown,
            onKeyUp: controller.keyUp,
          ),
        ],
      ),
    );
  }

  Widget _buildTerminalDrawer(BuildContext context) {
    final available = controller.terminalAvailable;
    final terminalHeight = MediaQuery.sizeOf(context).height < 700
        ? 155.0
        : 230.0;

    return Material(
      color: const Color(0xff111719),
      elevation: 18,
      child: SafeArea(
        top: false,
        child: Container(
          decoration: const BoxDecoration(
            border: Border(top: BorderSide(color: Color(0xff334044))),
          ),
          child: Align(
            alignment: Alignment.bottomCenter,
            heightFactor: 1,
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 1240),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  InkWell(
                    key: const ValueKey('terminal-toggle'),
                    onTap: () => _setTerminalExpanded(!_terminalExpanded),
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(18, 10, 10, 10),
                      child: Row(
                        children: [
                          const Icon(
                            Icons.terminal_rounded,
                            color: Color(0xff79e2c2),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  'Терминал',
                                  style: Theme.of(
                                    context,
                                  ).textTheme.titleMedium,
                                ),
                                Text(
                                  _terminalExpanded
                                      ? 'Открыт · ввод клавиатуры направлен в USB-терминал'
                                      : 'Скрыт · клавиатура ПК управляет MK61',
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: Theme.of(context).textTheme.bodySmall
                                      ?.copyWith(
                                        color: const Color(0xff8e999d),
                                      ),
                                ),
                              ],
                            ),
                          ),
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 9,
                              vertical: 5,
                            ),
                            decoration: BoxDecoration(
                              color: available
                                  ? const Color(0xff173b35)
                                  : const Color(0xff252b2d),
                              borderRadius: BorderRadius.circular(99),
                              border: Border.all(
                                color: available
                                    ? const Color(0xff2d7165)
                                    : const Color(0xff3b4447),
                              ),
                            ),
                            child: Text(
                              available ? 'MUX' : '—',
                              style: TextStyle(
                                color: available
                                    ? const Color(0xff78dfc0)
                                    : const Color(0xff929da0),
                                fontSize: 12,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                          ),
                          if (_terminalExpanded)
                            ValueListenableBuilder<int>(
                              valueListenable: controller.terminalChanges,
                              builder: (context, revision, child) => IconButton(
                                tooltip: 'Очистить терминал',
                                onPressed: controller.terminalLogEmpty
                                    ? null
                                    : controller.clearTerminal,
                                icon: const Icon(Icons.delete_sweep_outlined),
                              ),
                            ),
                          Icon(
                            _terminalExpanded
                                ? Icons.keyboard_arrow_down_rounded
                                : Icons.keyboard_arrow_up_rounded,
                            color: const Color(0xffaab5b8),
                          ),
                        ],
                      ),
                    ),
                  ),
                  AnimatedSize(
                    duration: const Duration(milliseconds: 180),
                    curve: Curves.easeOutCubic,
                    alignment: Alignment.topCenter,
                    child: _terminalExpanded
                        ? Padding(
                            padding: const EdgeInsets.fromLTRB(18, 2, 18, 16),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.stretch,
                              children: [
                                Container(
                                  height: terminalHeight,
                                  padding: const EdgeInsets.all(12),
                                  decoration: BoxDecoration(
                                    color: const Color(0xff080c0d),
                                    borderRadius: BorderRadius.circular(10),
                                    border: Border.all(
                                      color: const Color(0xff2b3638),
                                    ),
                                  ),
                                  child: Scrollbar(
                                    controller: _terminalScroll,
                                    thumbVisibility: true,
                                    child: SingleChildScrollView(
                                      controller: _terminalScroll,
                                      child: ValueListenableBuilder<int>(
                                        valueListenable:
                                            controller.terminalChanges,
                                        builder: (context, revision, child) {
                                          final terminalText =
                                              controller.terminalText;
                                          return SelectableText(
                                            terminalText.isEmpty
                                                ? available
                                                      ? 'Терминал готов. Введите команду ниже.'
                                                      : 'Подключите USB Screen для доступа к терминалу.'
                                                : terminalText,
                                            style: const TextStyle(
                                              fontFamily: 'monospace',
                                              fontSize: 13,
                                              height: 1.35,
                                              color: Color(0xffb8e7d7),
                                            ),
                                          );
                                        },
                                      ),
                                    ),
                                  ),
                                ),
                                const SizedBox(height: 12),
                                LayoutBuilder(
                                  builder: (context, constraints) {
                                    final input = Focus(
                                      onKeyEvent: (_, event) {
                                        if (event is KeyDownEvent &&
                                            event.logicalKey ==
                                                LogicalKeyboardKey.escape) {
                                          _setTerminalExpanded(false);
                                          return KeyEventResult.handled;
                                        }
                                        return KeyEventResult.ignored;
                                      },
                                      child: TextField(
                                        key: const ValueKey('terminal-input'),
                                        controller: _terminalInput,
                                        focusNode: _terminalFocus,
                                        enabled: available,
                                        maxLines: 1,
                                        textInputAction: TextInputAction.send,
                                        onSubmitted: _submitTerminal,
                                        decoration: const InputDecoration(
                                          labelText: 'Команда терминала',
                                          hintText: 'help, ver, reg, ls…',
                                          prefixIcon: Icon(
                                            Icons.terminal_rounded,
                                          ),
                                        ),
                                      ),
                                    );
                                    final send = FilledButton.icon(
                                      onPressed: available
                                          ? _submitTerminal
                                          : null,
                                      icon: const Icon(Icons.send_rounded),
                                      label: const Text('Выполнить'),
                                    );
                                    if (constraints.maxWidth < 590) {
                                      return Column(
                                        crossAxisAlignment:
                                            CrossAxisAlignment.stretch,
                                        children: [
                                          input,
                                          const SizedBox(height: 10),
                                          send,
                                        ],
                                      );
                                    }
                                    return Row(
                                      children: [
                                        Expanded(child: input),
                                        const SizedBox(width: 10),
                                        send,
                                      ],
                                    );
                                  },
                                ),
                              ],
                            ),
                          )
                        : const SizedBox.shrink(),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildDiagnostics(BuildContext context) {
    final caps = controller.capabilities;
    return _Panel(
      padding: EdgeInsets.zero,
      child: ExpansionTile(
        title: const Text('Диагностика соединения'),
        subtitle: Text(
          '${controller.completedFrames} кадров · '
          '${controller.framesPerSecond.toStringAsFixed(1)} fps · '
          '${_formatBytes(controller.rxBytes)} принято',
        ),
        childrenPadding: const EdgeInsets.fromLTRB(18, 0, 18, 18),
        children: [
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _Metric(label: 'Порт', value: controller.connectedPort ?? '—'),
              _Metric(label: 'RX', value: _formatBytes(controller.rxBytes)),
              _Metric(label: 'TX', value: _formatBytes(controller.txBytes)),
              _Metric(label: 'Кадры', value: '${controller.completedFrames}'),
              _Metric(
                label: 'Отклонено',
                value: '${controller.rejectedFrames}',
              ),
              _Metric(label: 'Потери seq', value: '${controller.sequenceGaps}'),
              _Metric(
                label: 'Пакеты CRC/COBS',
                value: '${controller.discardedPackets}',
              ),
              _Metric(label: 'Клавиатура', value: controller.keyboard.name),
              if (caps != null)
                _Metric(
                  label: 'Heartbeat',
                  value: '${caps.heartbeatTimeoutMs} мс',
                ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildError(BuildContext context, String message) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
      decoration: BoxDecoration(
        color: const Color(0xff351b1d),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: const Color(0xff71363b)),
      ),
      child: Row(
        children: [
          const Icon(Icons.error_outline_rounded, color: Color(0xffff9da4)),
          const SizedBox(width: 10),
          Expanded(child: Text(message)),
        ],
      ),
    );
  }

  String _formatBytes(int bytes) {
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KiB';
    return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MiB';
  }
}

class _Panel extends StatelessWidget {
  const _Panel({
    required this.child,
    this.color = const Color(0xff151a1c),
    this.padding = const EdgeInsets.all(18),
  });

  final Widget child;
  final Color color;
  final EdgeInsets padding;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: padding,
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(15),
        border: Border.all(color: const Color(0xff30383b)),
      ),
      child: child,
    );
  }
}

class _StatusBadge extends StatelessWidget {
  const _StatusBadge({
    required this.text,
    required this.active,
    required this.busy,
  });

  final String text;
  final bool active;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    final color = active
        ? const Color(0xff65d5b0)
        : busy
        ? const Color(0xffffc66d)
        : const Color(0xff8e999d);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.11),
        borderRadius: BorderRadius.circular(99),
        border: Border.all(color: color.withValues(alpha: 0.45)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
          const SizedBox(width: 8),
          Text(
            text,
            style: TextStyle(color: color, fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }
}

class _GuideStep extends StatelessWidget {
  const _GuideStep({required this.number, required this.text});

  final String number;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 25,
          height: 25,
          alignment: Alignment.center,
          decoration: const BoxDecoration(
            color: Color(0xff245b55),
            shape: BoxShape.circle,
          ),
          child: Text(
            number,
            style: const TextStyle(fontWeight: FontWeight.bold),
          ),
        ),
        const SizedBox(width: 8),
        Flexible(child: Text(text)),
      ],
    );
  }
}

class _Metric extends StatelessWidget {
  const _Metric({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 8),
      decoration: BoxDecoration(
        color: const Color(0xff0f1315),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(0xff2c3437)),
      ),
      child: Text('$label: $value'),
    );
  }
}
