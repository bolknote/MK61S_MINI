#!/usr/bin/env python3
"""Exercise stale resource rejection and CI triggers for the native asset tree."""
import ast
import fnmatch
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class ResourceCiTests(unittest.TestCase):
    def test_resource_edits_trigger_validation(self):
        workflow=(ROOT/'.github/workflows/picocalc.yml').read_text()
        triggers=[ast.literal_eval(line.split('paths:',1)[1].strip()) for line in workflow.splitlines() if 'paths:' in line]
        self.assertEqual(len(triggers),2)
        for paths in triggers:
            for path in ('programs/games/Bumblebee/scene-320.wbmp','doc/game-artwork/native/recipe.json',
                'doc/game-artwork/bumblebee.svg','programs/examples/Graphics.foc',
                'tools/generate_picocalc_game_assets.py','tools/m8_codec.py','tools/.fmk-font/ui-atlases/pixel-16.json',
                'tests/run_picocalc_recovery_tests.sh','tests/basic_graphics_self_test.cpp'):
                self.assertTrue(any(fnmatch.fnmatchcase(path,p) for p in paths),path)
        for command in ('python3 tools/generate_picocalc_game_assets.py --check-inputs',
            'python3 tests/picocalc_native_assets_self_test.py','python3 tests/picocalc_version_self_test.py',
            'bash tests/run_picocalc_recovery_tests.sh','bash tests/run_basic_graphics_tests.sh'):
            self.assertIn(command,workflow)

    def test_modified_input_or_output_requires_regeneration(self):
        receipt=ROOT/'doc/game-artwork/native/recipe.json'
        recipe=json.loads(receipt.read_text())
        with tempfile.TemporaryDirectory(prefix='mk61-native-recipe-') as directory:
            target=Path(directory)
            for name in {*recipe['inputs_sha256'],*recipe['outputs_sha256'],str(receipt.relative_to(ROOT))}:
                dest=target/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,dest)
            command=[sys.executable,str(target/'tools/generate_picocalc_game_assets.py'),'--check-inputs']
            result=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            for name in ('doc/game-artwork/bumblebee.svg','programs/games/Bumblebee/scene-320.wbmp'):
                file=target/name;original=file.read_bytes();file.write_bytes(original+b'changed')
                result=subprocess.run(command,capture_output=True,text=True)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('regenerate and review',result.stderr)
                file.write_bytes(original)


if __name__=='__main__':unittest.main()
