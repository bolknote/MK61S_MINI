#!/usr/bin/env python3
"""No hardware: Pico point cleanup with hidden/unknown/large-file rejection."""
import importlib.util
from pathlib import Path
import shlex
import sys
import unittest

HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from session import OwnedSession,Hold
spec=importlib.util.spec_from_file_location('pico_namespace',HERE/'pico-namespace.py')
namespace=importlib.util.module_from_spec(spec);spec.loader.exec_module(namespace)


class NamespaceTest(unittest.TestCase):
    def fixture(self):
        directory='/MCHR-Q01';files={'/original.bin':b'original','/.hidden.bin':bytes(70000)};dirs=set();attrs={};reads=[];commands=[]
        def listing(parent):
            prefix=parent.rstrip('/')+'/';rows=[]
            for path in [*files,*dirs]:
                if path.startswith(prefix) and '/' not in path[len(prefix):]:
                    isdir=path in dirs
                    rows.append(dict(path=path,kind='directory' if isdir else 'file',bytes=None if isdir else len(files[path]),fat_attributes=attrs.get(path,0x10 if isdir else 0x20)))
            return rows
        def read(path):reads.append(path);return files[path]
        def write(path,data):files[path]=data
        def command(text):
            commands.append(text);parts=shlex.split(text)
            if parts[:2]==['fsput','cancel']:return 'OK'
            if parts[0]=='mkdir':dirs.add(parts[1])
            elif parts[0]=='rm':del files[parts[1]]
            elif parts[0]=='rmdir':
                self.assertFalse(any(p.startswith(parts[1]+'/') for p in [*files,*dirs]));dirs.remove(parts[1])
            else:raise AssertionError(text)
            return 'OK'
        view=namespace.Namespace(directory,listing,read)
        session=OwnedSession(directory,view.scan,read,write,command,lambda _:None)
        return directory,files,dirs,attrs,reads,commands,view,session

    def test_point_cleanup_reads_only_owned_small_files_and_keeps_other_users_bytes(self):
        directory,files,dirs,attrs,reads,commands,view,session=self.fixture();before=dict(files)
        session.capture();session.create();session.put('CHRBEN.APP',b'app');session.put('INPUT.bin',b'input')
        session.expect_result(lambda data:data==b'owned-report');files[directory+'/RESULT.bin']=b'owned-report';session.admit_result(b'owned-report')
        result=session.cleanup()
        self.assertTrue(result['files_preserved']);self.assertFalse(result['files_restored'])
        self.assertEqual(files,before);self.assertFalse(dirs)
        self.assertTrue(all(path.startswith(directory+'/') for path in reads));self.assertFalse(any('-r' in text for text in commands))

    def test_unknown_hidden_directory_or_large_child_blocks_every_cleanup_mutation(self):
        for fault in ('hidden','directory','large','attributes','unknown','changed-known'):
            with self.subTest(fault=fault):
                directory,files,dirs,attrs,reads,commands,view,session=self.fixture()
                session.capture();session.create();session.put('CHRBEN.APP',b'app')
                path=directory+'/unexpected.bin'
                if fault=='hidden':files[directory+'/.foreign']=b'data'
                elif fault=='directory':dirs.add(directory+'/child')
                elif fault=='large':files[directory+'/RESULT.bin']=bytes(65535)
                elif fault=='attributes':attrs[directory+'/CHRBEN.APP']=0x22
                elif fault=='changed-known':files[directory+'/CHRBEN.APP']=b'foreign app'
                else:files[path]=b'data'
                before=(dict(files),set(dirs));start=len(commands)
                with self.assertRaises(Hold):session.cleanup()
                self.assertEqual(len(commands),start);self.assertEqual((files,dirs),before)
                self.assertNotIn(directory+'/RESULT.bin',reads if fault=='large' else [])

    def test_case_collision_or_namespace_replacement_never_creates_or_deletes(self):
        for fault in ('case','file','hidden-root'):
            directory,files,dirs,attrs,reads,commands,view,session=self.fixture()
            if fault=='case':dirs.add(directory.lower())
            elif fault=='file':files[directory]=b'original'
            else:dirs.add(directory);attrs[directory]=0x12
            with self.subTest(fault=fault),self.assertRaises(Hold):session.capture()
            self.assertFalse(commands);self.assertFalse(reads)

    def test_helper_inventory_aliases_and_nonchild_paths_are_rejected(self):
        row=dict(path='/MCHR-Q01',kind='directory',bytes=None,fat_attributes=0x10)
        for rows in ([row,{**row,'path':'/mchr-q01'}],[{**row,'path':'/MCHR-Q01/foreign'}],[{**row,'path':'/../MCHR-Q01'}]):
            view=namespace.Namespace('/MCHR-Q01',lambda _:rows,lambda _:b'')
            with self.assertRaises(Hold):view.scan()


if __name__=='__main__':unittest.main()
