#!/usr/bin/env python3
"""Exercise IDE's real gRPC compile stream, including the native /System hook.

Test-only dependencies: grpcio and protobuf. Firmware/build scripts use neither.
Wire fields follow Arduino CLI v1.5.1's official commands/common/compile.proto:
https://github.com/arduino/arduino-cli/tree/v1.5.1/rpc/cc/arduino/cli/commands/v1
Unknown response fields are retained by protobuf; no generated SDK is needed.
"""
import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time

import grpc
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

SERVICE = '/cc.arduino.cli.commands.v1.ArduinoCoreService/'


def messages():
    file = descriptor_pb2.FileDescriptorProto(name='mk61_arduino_probe.proto',
        package='probe', syntax='proto3')
    # Only the public wire fields used by this integration test are described.
    definitions = {
        'Instance': [('id', 1, 'int32')],
        'CreateRequest': [], 'CreateResponse': [('instance', 1, 'Instance')],
        'InitRequest': [('instance', 1, 'Instance')],
        'Status': [('code', 1, 'int32'), ('message', 2, 'string')],
        'InitResponse': [('error', 2, 'Status')],
        'CompileRequest': [('instance', 1, 'Instance'), ('fqbn', 2, 'string'),
            ('sketch_path', 3, 'string'), ('build_path', 7, 'string'), ('verbose', 10, 'bool')],
        # Library records are opaque; any external Arduino library fails below.
        'BuilderResult': [('build_path', 1, 'string'), ('used_libraries', 2, 'bytes', True),
            ('build_properties', 7, 'string', True)],
        'CompileResponse': [('out_stream', 1, 'bytes'), ('err_stream', 2, 'bytes'),
            ('result', 4, 'BuilderResult')],
        'VersionRequest': [], 'VersionResponse': [('version', 1, 'string')],
        'DestroyRequest': [('instance', 1, 'Instance')], 'DestroyResponse': []}
    scalar = {'int32': 5, 'string': 9, 'bytes': 12, 'bool': 8}
    for name, fields in definitions.items():
        message = file.message_type.add(name=name)
        for field_name, number, kind, *repeated in fields:
            field = message.field.add(name=field_name, number=number,
                label=3 if repeated and repeated[0] else 1,
                type=scalar.get(kind, 11))
            if kind not in scalar:
                field.type_name = '.probe.' + kind
    pool = descriptor_pool.DescriptorPool()
    pool.Add(file)
    return {name: message_factory.GetMessageClass(pool.FindMessageTypeByName('probe.' + name))
            for name in definitions}


def run(args):
    types = messages()
    build = args.build_path.resolve()
    build.mkdir(parents=True, exist_ok=True)
    daemon_log = build / 'mk61-arduino-daemon.log'
    compile_log = build / 'mk61-arduino-grpc-compile.log'
    lines = queue.Queue()
    command = [args.cli, '--config-file', str(args.config_file.resolve()),
               'daemon', '--daemonize', '--port', '0', '--log']
    process = subprocess.Popen(command, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')

    def collect():
        with daemon_log.open('w', encoding='utf-8') as output:
            for line in process.stdout:
                output.write(line)
                output.flush()
                lines.put(line)
        lines.put(None)

    thread = threading.Thread(target=collect, daemon=True)
    thread.start()
    channel = None
    try:
        deadline = time.monotonic() + 45
        port = None
        while time.monotonic() < deadline:
            try:
                line = lines.get(timeout=1)
            except queue.Empty:
                continue
            if line is None:
                raise RuntimeError('Arduino daemon exited during startup: ' + str(process.wait(timeout=5)))
            try:
                startup = json.loads(line)
            except ValueError:
                continue
            if isinstance(startup, dict) and 'Port' in startup:
                port = int(startup['Port'])
                break
        if not port:
            raise RuntimeError('Arduino daemon did not report its local gRPC port')
        channel = grpc.insecure_channel('127.0.0.1:' + str(port),
            options=[('grpc.enable_http_proxy', 0)])

        def rpc(name, streaming=False):
            factory = channel.unary_stream if streaming else channel.unary_unary
            return factory(SERVICE + name,
                request_serializer=types[name + 'Request'].SerializeToString,
                response_deserializer=types[name + 'Response'].FromString)

        version = rpc('Version')(types['VersionRequest'](), timeout=15).version
        print('Arduino daemon gRPC connected: CLI ' + version, flush=True)
        created = rpc('Create')(types['CreateRequest'](), timeout=15)
        instance = created.instance
        if not instance.id:
            raise RuntimeError('Arduino daemon returned an empty instance')
        for event in rpc('Init', True)(types['InitRequest'](instance=instance), timeout=120):
            if event.HasField('error') and event.error.code:
                raise RuntimeError('Arduino daemon initialization: ' + event.error.message)
        print('Arduino daemon initialized; compiling resident and System', flush=True)
        request = types['CompileRequest'](instance=instance, fqbn=args.fqbn,
            sketch_path=str(args.sketch.resolve()), build_path=str(build), verbose=True)
        result = None
        output_text = []
        with compile_log.open('wb') as output:
            for event in rpc('Compile', True)(request, timeout=1800):
                for chunk in (event.out_stream, event.err_stream):
                    if chunk:
                        output.write(chunk)
                        output.flush()
                        text = chunk.decode('utf-8', errors='replace')
                        output_text.append(text)
                        print(text, end='', flush=True)
                if event.HasField('result'):
                    result = event.result
        if result is None or not result.build_path:
            raise RuntimeError('gRPC stream ended without the completed build result')
        if result.used_libraries:
            raise RuntimeError('Native daemon build used external Arduino libraries')
        if 'build.core=mk61' not in result.build_properties:
            raise RuntimeError('gRPC compiled a different board Core')
        if 'unified ABI 6 bundle built by Arduino IDE' not in ''.join(output_text):
            raise RuntimeError('gRPC compile did not complete the System APP post-build')
        for suffix in ('elf', 'bin'):
            if not (build / ('code.ino.' + suffix)).is_file():
                raise RuntimeError('gRPC compile did not produce code.ino.' + suffix)
        manifests = list((build / 'mk61-system-apps').glob('*/build.system.json'))
        if os.name == 'nt' and len(manifests) != 1:
            raise RuntimeError('gRPC compile did not publish exactly one complete System manifest')
        for name in ('FOCAL.APP', 'BASIC.APP', 'LANGVM.APP', 'LANGIN.APP',
                     'MARKDOWN.APP', 'SETUP.APP', 'EXPLORER.APP', 'USBDISK.APP',
                     'HELP0.TXT', 'HELP1.TXT'):
            if not any((build / 'mk61-system-apps').glob('*/System/' + name)):
                raise RuntimeError('gRPC post-build omitted ' + name)
        after = rpc('Version')(types['VersionRequest'](), timeout=15).version
        if after != version or process.poll() is not None:
            raise RuntimeError('Arduino daemon did not survive its post-build')
        rpc('Destroy')(types['DestroyRequest'](instance=instance), timeout=15)
        print(f'Arduino IDE gRPC compile: CLI {version}, complete resident/System, '
              'no external libraries, daemon alive PASS', flush=True)
    except Exception:
        print('\nArduino daemon log:', daemon_log)
        if daemon_log.exists():
            print(daemon_log.read_text(encoding='utf-8')[-12000:])
        raise
    finally:
        if channel is not None:
            channel.close()
        if process.poll() is None:
            if os.name == 'nt':
                # Own daemon only: also close its builtin discovery children.
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        thread.join(timeout=5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cli', default='arduino-cli')
    parser.add_argument('--config-file', required=True, type=Path)
    parser.add_argument('--sketch', required=True, type=Path)
    parser.add_argument('--build-path', required=True, type=Path)
    parser.add_argument('--fqbn', default='mk61:stm32:mk61_f401_app:mk61_platform=classic_v2,'
        'mk61_display=uc1609,mk61_focal=app,mk61_basic=app,mk61_documents=markdown,'
        'mk61_chip8=disabled,mk61_setup=app,mk61_explorer_module=app,'
        'mk61_usb_screen=disabled,mk61_explorer=enabled,mk61_math=core')
    run(parser.parse_args())
