#!/usr/bin/env python3
"""Regress the macOS host failure without executing a forbidden instruction."""
import contextlib
import ctypes
import errno
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch, sentinel
import ast

ROOT = Path(__file__).resolve().parents[1]
import unicorn_runtime as runtime


class Query:
    def __init__(self, result=0, value=128, error=0):
        self.result, self.value, self.error = result, value, error
    def __call__(self, name, output, size, new, new_size):
        assert name == b'hw.cachelinesize' and new is None and new_size == 0
        output._obj.value = self.value
        size._obj.value = ctypes.sizeof(ctypes.c_long)
        ctypes.set_errno(self.error)
        return self.result


class HostTests(unittest.TestCase):
    def check_mac(self, query):
        with patch.object(runtime.platform, 'system', return_value='Darwin'), \
             patch.object(runtime.platform, 'machine', return_value='arm64'), \
             patch.object(runtime.ctypes, 'CDLL', return_value=SimpleNamespace(sysctlbyname=query)):
            runtime.ensure_compatible_host()
    def test_allowed_cache_query(self):
        self.check_mac(Query())
    def test_denied_query_reports_permission_and_no_emulation(self):
        with self.assertRaisesRegex(runtime.UnicornHostError, 'errno=1.*outside the sandbox.*No emulator'):
            self.check_mac(Query(result=-1, value=0, error=errno.EPERM))
    def test_success_with_invalid_size_is_rejected(self):
        with self.assertRaisesRegex(runtime.UnicornHostError, 'invalid cache line size'):
            self.check_mac(Query(value=0))
    def test_other_hosts_do_not_call_macos_api(self):
        for system, machine in [('Linux','aarch64'),('Windows','ARM64'),('Darwin','x86_64')]:
            with self.subTest(system=system, machine=machine), \
                 patch.object(runtime.platform,'system',return_value=system), \
                 patch.object(runtime.platform,'machine',return_value=machine), \
                 patch.object(runtime.ctypes,'CDLL') as library:
                runtime.ensure_compatible_host()
                library.assert_not_called()
    def test_native_constructor_never_called_after_denial(self):
        constructor=Mock()
        with patch.object(runtime,'ensure_compatible_host',side_effect=runtime.UnicornHostError('denied')), \
             patch.dict(sys.modules, {'unicorn':SimpleNamespace(Uc=constructor)}):
            with self.assertRaisesRegex(runtime.UnicornHostError,'denied'):
                runtime.Uc(1,2)
        constructor.assert_not_called()
    def test_allowed_constructor_preserves_native_object_and_arguments(self):
        constructor=Mock(return_value=sentinel.native_engine)
        with patch.object(runtime,'ensure_compatible_host') as check, \
             patch.dict(sys.modules, {'unicorn':SimpleNamespace(Uc=constructor)}):
            self.assertIs(runtime.Uc(1,2,cpu=3),sentinel.native_engine)
        check.assert_called_once_with()
        constructor.assert_called_once_with(1,2,cpu=3)
    def launcher(self):
        spec=importlib.util.spec_from_file_location('arm_test_launcher',ROOT/'dev/tools/run_arm_test.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module
    def test_launcher_stops_before_test_on_denial(self):
        module=self.launcher();error=io.StringIO()
        with patch.object(module,'ensure_compatible_host',side_effect=runtime.UnicornHostError('blocked cache query')), \
             patch.object(module.runpy,'run_path') as run, \
             patch.object(sys,'argv',['run_arm_test.py',str(Path(__file__).resolve())]), \
             contextlib.redirect_stderr(error):
            with self.assertRaises(SystemExit) as raised:
                module.main()
        self.assertEqual(raised.exception.code,2)
        self.assertIn('blocked cache query',error.getvalue())
        run.assert_not_called()
    def test_launcher_forwards_test_arguments_without_a_subshell(self):
        module=self.launcher();seen=[];original_path=list(sys.path)
        def run(path,run_name):seen.append((path,run_name,list(sys.argv)))
        try:
            with patch.object(module,'ensure_compatible_host'), \
                 patch.object(module.runpy,'run_path',side_effect=run), \
                 patch.object(sys,'argv',['run_arm_test.py',str(Path(__file__).resolve()),'--name','two words']):
                module.main()
            self.assertEqual(seen,[(str(Path(__file__).resolve()),'__main__',[str(Path(__file__).resolve()),'--name','two words'])])
        finally:
            sys.path[:]=original_path
    def test_tracked_arm_scripts_do_not_bypass_host_guard(self):
        names=subprocess.check_output(['git','-C',str(ROOT),'ls-files','-z','--','tests','dev/tools']).decode().split('\0')
        violations=[]
        for name in names:
            if not name.endswith('.py') or name=='tests/unicorn_runtime.py':continue
            for node in ast.walk(ast.parse((ROOT/name).read_text())):
                if isinstance(node,ast.ImportFrom) and node.module=='unicorn' and any(alias.name=='Uc' for alias in node.names):
                    violations.append(name)
                if isinstance(node,ast.Import) and any(alias.name=='unicorn' for alias in node.names):
                    violations.append(name)
        self.assertEqual(violations,[],'ARM engine creation must pass through unicorn_runtime.Uc')


if __name__=='__main__':
    unittest.main()
