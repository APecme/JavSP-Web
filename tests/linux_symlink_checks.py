"""Real cross-filesystem symlink checks; run in an isolated Linux container.
Only Cfg is stubbed: these tests exercise Movie filesystem operations directly.
"""
import ast
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'vendor/JavSP'))
config = types.ModuleType('javsp.config'); config.Cfg = lambda: None
sys.modules['javsp.config'] = config
from javsp.datatype import Movie

class LinuxSymlinks(unittest.TestCase):
    def setUp(self):
        self.src_tmp = tempfile.TemporaryDirectory(dir='/tmp')
        self.dst_tmp = tempfile.TemporaryDirectory(dir='/dev/shm')
        self.addCleanup(self.src_tmp.cleanup); self.addCleanup(self.dst_tmp.cleanup)
        self.src, self.dst = Path(self.src_tmp.name), Path(self.dst_tmp.name)
        self.assertNotEqual(self.src.stat().st_dev, self.dst.stat().st_dev)

    def movie(self, count=1):
        m = Movie('ABC-123'); m.files=[]; m.save_dir=str(self.dst); m.basename='ABC-123'
        for i in range(count):
            p=self.src/f'input-{i}.mp4'; p.write_bytes(b'original video'); m.files.append(str(p))
        return m

    def test_cross_device_link_rerun_and_restore(self):
        m=self.movie(); m.rename_files(use_symlink=True)
        target=Path(m.new_paths[0]); original=Path(m.files[0])
        self.assertTrue(target.is_symlink()); self.assertTrue(os.path.samefile(target, original))
        m.rename_files(use_symlink=True)
        # Execute production restore planning without importing the Web server.
        tree=ast.parse((ROOT/'javsp_web/tasks.py').read_text())
        funcs=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('_restore_plan','restore_task_files')]
        import threading
        task={'file_organizer': {'original_files':m.files,'organized_files':m.new_paths,'generated_files':[]},'image_output':{'save_dir':str(self.dst)}}
        env=dict(Path=Path,os=os,_lock=threading.RLock(),get_task_record=lambda _:task,_fanart_paths=lambda *a:[],now_iso=lambda:'now',_logs={},_clean_log_lines=lambda v:v,_MAX_LOG_LINES=100,_persist=lambda _:None)
        exec(compile(ast.Module(body=funcs,type_ignores=[]),'restore','exec'),env)
        self.assertTrue(env['restore_task_files']('test'))
        self.assertTrue(original.is_file()); self.assertFalse(os.path.lexists(target))

    def test_overwrite_link_never_touches_old_target_and_handles_dangling(self):
        m=self.movie(); target=Path(m.organization_paths()[0])
        old=self.src/'old.mp4'; old.write_bytes(b'old video'); target.symlink_to(old)
        m.rename_files(use_symlink=True,policy='never'); self.assertEqual(target.read_bytes(),b'old video')
        m.rename_files(use_symlink=True,policy='always'); self.assertEqual(target.read_bytes(),b'original video'); self.assertEqual(old.read_bytes(),b'old video')
        target.unlink(); target.symlink_to(self.src/'missing.mp4')
        m.rename_files(use_symlink=True,policy='always'); self.assertTrue(target.is_file())

    def test_second_part_failure_restores_previous_links(self):
        m=self.movie(2); targets=list(map(Path,m.organization_paths()))
        old=self.src/'old.mp4'; old.write_bytes(b'old video')
        for p in targets:p.symlink_to(old)
        real=os.symlink
        def fail_second(src,dst):
            if src==m.files[1]:raise OSError('second part failure')
            real(src,dst)
        with patch('javsp.datatype.os.symlink',side_effect=fail_second),self.assertRaises(OSError):m.rename_files(use_symlink=True,policy='always')
        self.assertTrue(all(Path(p).read_bytes()==b'original video' for p in m.files))
        self.assertTrue(all(p.is_symlink() and p.read_bytes()==b'old video' for p in targets))
        self.assertFalse(list(self.dst.glob('.javsp-backup-*')))

if __name__=='__main__':unittest.main()
