#!/usr/bin/env python3
"""Recovery helper changes must fail before opening the held serial device."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('memchr_recovery',HERE/'recover-app.py')
recovery=importlib.util.module_from_spec(spec);spec.loader.exec_module(recovery)

class RecoveryTest(unittest.TestCase):
    def test_dynamic_v4_helper_is_always_in_dependency_inventory(self):
        key=str(Path(recovery.app.__file__).resolve().relative_to(recovery.ROOT))
        self.assertEqual(recovery.dependencies()[key],recovery.V4_RUNNER)
    def test_tampered_dynamic_helper_rejects_before_connect(self):
        packet=recovery.ROOT/'.build/memchr-20261023/recovery-only-v2'
        plan=packet/'plan.json'
        if not plan.exists():self.skipTest('Frozen recovery V2 required')
        digest=recovery.sha(plan.read_bytes());port=json.loads(plan.read_text())['port']
        actual_read=Path.read_bytes;helper=Path(recovery.app.__file__).resolve()
        def read(path):return b'tampered helper' if path.resolve()==helper else actual_read(path)
        argv=['recover-app.py','--plan',str(plan),'--plan-sha256',digest,'--port',port,'--output','/unused']
        with patch.object(sys,'argv',argv),patch.object(Path,'read_bytes',read),patch.object(recovery,'connect') as serial:
            with self.assertRaisesRegex(recovery.Hold,'V4 helper changed'):recovery.main()
            serial.assert_not_called()

if __name__=='__main__':unittest.main()
