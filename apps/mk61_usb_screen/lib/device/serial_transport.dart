import 'dart:typed_data';

import 'package:flutter_libserialport/flutter_libserialport.dart';

class DeviceSerialPort {
  const DeviceSerialPort({
    required this.name,
    this.description,
    this.vendorId,
    this.productId,
    this.manufacturer,
    this.productName,
    this.serialNumber,
  });

  final String name;
  final String? description;
  final int? vendorId;
  final int? productId;
  final String? manufacturer;
  final String? productName;
  final String? serialNumber;

  /// Автоматическая активация намеренно ограничена USB-идентификатором прошивки
  /// МК-61. Имена портов вроде COM3 или ttyUSB0 ничего не доказывают: они могут
  /// принадлежать модемам, ИБП, отладочным консолям или посторонним контроллерам.
  bool get isAutomaticCandidate {
    if (vendorId != 0x0483 || productId != 0x5740) return false;
    final identity = [
      description,
      manufacturer,
      productName,
    ].whereType<String>().join(' ').toLowerCase();
    return identity.contains('mk61') ||
        identity.contains('mk-61') ||
        identity.contains('blackpill_f411ce') ||
        identity.contains('blackpill f411ce');
  }
}

abstract interface class DeviceSerialTransport {
  List<DeviceSerialPort> get availablePorts;

  DeviceSerialConnection open(String name, {required int baudRate});
}

abstract interface class DeviceSerialConnection {
  Stream<Uint8List> get input;

  int write(Uint8List bytes, {required int timeoutMs});

  void drain();

  void close();
}

class LibSerialTransport implements DeviceSerialTransport {
  const LibSerialTransport();

  @override
  List<DeviceSerialPort> get availablePorts =>
      SerialPort.availablePorts.map(_describePort).toList(growable: false);

  static DeviceSerialPort _describePort(String name) {
    final port = SerialPort(name);
    try {
      return DeviceSerialPort(
        name: name,
        description: port.description,
        vendorId: port.vendorId,
        productId: port.productId,
        manufacturer: port.manufacturer,
        productName: port.productName,
        serialNumber: port.serialNumber,
      );
    } catch (_) {
      // Оставляем порт доступным для явного пользовательского подключения,
      // но не проверяем автоматически, если USB-идентификатор нельзя безопасно прочитать.
      return DeviceSerialPort(name: name);
    } finally {
      port.dispose();
    }
  }

  @override
  DeviceSerialConnection open(String name, {required int baudRate}) {
    final port = SerialPort(name);
    try {
      if (!port.openReadWrite()) {
        throw SerialPort.lastError ?? StateError('порт не открылся');
      }

      final config = SerialPortConfig()
        ..baudRate = baudRate
        ..bits = 8
        ..parity = SerialPortParity.none
        ..stopBits = 1;
      try {
        config.setFlowControl(SerialPortFlowControl.none);
      } catch (_) {
        // Порт не владеет конфигурацией до её назначения ниже.
        config.dispose();
        rethrow;
      }
      // libserialport сохраняет назначенную конфигурацию и освобождает её из
      // SerialPort.dispose(). Освобождение здесь привело бы к повторному
      // освобождению того же нативного указателя при закрытии порта.
      port.config = config;
      return _LibSerialConnection(port);
    } catch (_) {
      try {
        if (port.isOpen) port.close();
      } catch (_) {
        // Необязательная попытка при отказе от неудачного кандидата.
      }
      port.dispose();
      rethrow;
    }
  }
}

class _LibSerialConnection implements DeviceSerialConnection {
  _LibSerialConnection(this._port)
    : _reader = SerialPortReader(_port, timeout: 100);

  final SerialPort _port;
  final SerialPortReader _reader;
  bool _closed = false;

  @override
  Stream<Uint8List> get input => _reader.stream;

  @override
  int write(Uint8List bytes, {required int timeoutMs}) =>
      _port.write(bytes, timeout: timeoutMs);

  @override
  void drain() => _port.drain();

  @override
  void close() {
    if (_closed) return;
    _closed = true;
    _reader.close();
    try {
      if (_port.isOpen) _port.close();
    } catch (_) {
      // ОС уже могла удалить порт.
    }
    _port.dispose();
  }
}
