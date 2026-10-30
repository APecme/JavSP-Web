"""Directory watch regression tests.

These tests drive the real watcher against real temporary directories and the
real ``create_tasks`` pipeline (preset validation, multipart grouping, task
store persistence). Only the scrape worker boundary is patched
(``tasks._enqueue_task``), exactly like the existing scan tests, so nothing here
mocks the module under test.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor/JavSP"))

from javsp_web import directory_watch, directory_watch_router, storage, task_store, tasks

T0 = 1_760_000_000.0  # deterministic epoch for the injected clock


class DirectoryWatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data_dir = self.root / "state"
        old = storage.DATA_DIR
        for name, value in list(vars(storage).items()):
            if isinstance(value, Path) and value.is_relative_to(old):
                self.enterContext(patch.object(storage, name, self.data_dir / value.relative_to(old)))
        self.enterContext(patch.object(tasks, "DATA_DIR", self.data_dir))
        self.enterContext(patch.object(tasks, "_TASK_COVERS_DIR", self.data_dir / "task-covers"))
        self.enterContext(patch.object(tasks, "_TASK_COOKIECLOUD_DIR", self.data_dir / "task-cookiecloud"))
        self.enterContext(patch.object(tasks, "_logs", {}))
        self.enterContext(patch.object(tasks, "_cancelled_tasks", set()))
        self.enterContext(patch.object(tasks, "_deleted_tasks", set()))
        self.enterContext(patch.object(tasks, "_processes", {}))
        self.enterContext(patch.object(tasks, "_google_captcha_sessions", {}))
        storage.ensure_seed_data()
        config = yaml.safe_load((ROOT / "vendor/JavSP/config.yml").read_text(encoding="utf-8"))
        # A real preset: only the minimum size is relaxed so tiny fixtures count.
        form = {"scanner": {"minimum_size": "1B", "input_directory": None, "manual": False}}
        self.preset = {
            "id": "default", "name": "目录监控测试", "mode": "form", "form": form,
            "content": yaml.safe_dump(config, allow_unicode=True), "created_at": "", "updated_at": "",
        }
        storage.save_preset(self.preset)
        self.mount = self.root / "mount"
        self.mount.mkdir()
        self.submitted: list[dict] = []
        self.enqueue = self.enterContext(patch.object(tasks, "_enqueue_task", side_effect=self._enqueue))
        directory_watch.stop_scheduler()

    def _enqueue(self, task):
        self.submitted.append(task)

    # ------------------------------------------------------------------ utils
    def write(self, rel: str, payload: bytes = b"x" * 32, ns: int | None = None) -> Path:
        path = self.mount / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        if ns is not None:
            os.utime(path, ns=(ns, ns))
        return path

    def rule(self, **overrides) -> dict:
        payload = {
            "name": "监控", "path": str(self.mount), "preset_id": "default",
            "poll_seconds": 30, "stable_seconds": 60,
        }
        payload.update(overrides)
        return directory_watch.create_rule(payload)

    def scan(self, rule_id: str, at: float):
        return directory_watch.scan_rule(rule_id, now=at)

    def report(self, rule_id: str) -> dict:
        return next(item for item in directory_watch.list_rule_reports() if item["id"] == rule_id)

    def finish(self, task_id: str) -> None:
        tasks._persist({**tasks.get_task(task_id), "status": "succeeded", "finished_at": "2026-10-23T00:00:00+00:00"})

    # --------------------------------------------------------------- behaviour
    def test_new_file_waits_for_stable_window_then_submits_once(self):
        rule = self.rule(stable_seconds=60)
        self.write("ABC-123.mkv", ns=1_760_000_000_000_000_000)

        first = self.scan(rule["id"], T0)
        self.assertEqual(first["submitted"], [], "a file that just appeared is not stable yet")
        self.assertEqual(first["state"], "ok")
        self.assertEqual(self.report(rule["id"])["status"]["pending"], 1)

        self.assertEqual(self.scan(rule["id"], T0 + 30)["submitted"], [], "still inside the stable window")
        stable = self.scan(rule["id"], T0 + 61)
        self.assertEqual(len(stable["submitted"]), 1, stable)
        self.assertEqual(len(self.submitted), 1)
        task = self.submitted[0]
        self.assertEqual(task["source"], "directory_watch")
        self.assertEqual(task["preset_id"], "default")
        self.assertEqual(Path(task["input_directory"]).name, "ABC-123.mkv")

        repeat = self.scan(rule["id"], T0 + 200)
        self.assertEqual(repeat["submitted"], [])
        self.assertEqual(len(self.submitted), 1, "an unchanged committed file never re-enters the queue")

    def test_continuously_written_file_is_not_submitted_until_it_settles(self):
        rule = self.rule(stable_seconds=60)
        self.write("ABC-200.mkv", payload=b"a" * 10, ns=1_760_000_000_000_000_000)
        self.scan(rule["id"], T0)
        # The download engine keeps extending the file: size and mtime move.
        for index, at in enumerate((T0 + 30, T0 + 60, T0 + 90)):
            self.write("ABC-200.mkv", payload=b"a" * (10 + 10 * (index + 1)), ns=1_760_000_000_000_000_000 + 30 * 10**9 * (index + 1))
            self.assertEqual(self.scan(rule["id"], at)["submitted"], [], "a growing file must stay out of the queue")

        settled = self.scan(rule["id"], T0 + 160)
        self.assertEqual(len(settled["submitted"]), 1)
        self.assertEqual(len(self.submitted), 1)

    def test_multipart_parts_aggregate_into_one_task(self):
        rule = self.rule(stable_seconds=0)
        self.assertEqual(self.report(rule["id"])["status"]["state"], "ok")
        self.write("ABC-123-CD1.mkv", ns=1_760_000_000_000_000_000)
        self.write("ABC-123-CD2.mkv", ns=1_760_000_000_000_000_000)
        result = self.scan(rule["id"], T0)
        self.assertEqual(len(result["submitted"]), 1, "both parts must land in a single aggregated task")
        self.assertEqual(len(self.submitted), 1)
        self.assertEqual(sorted(Path(path).name for path in self.submitted[0]["input_files"]),
                         ["ABC-123-CD1.mkv", "ABC-123-CD2.mkv"])

    def test_late_multipart_part_joins_the_movie_task(self):
        rule = self.rule(stable_seconds=0, max_tasks_per_scan=5)
        self.write("ABC-300-CD1.mkv", ns=1_760_000_000_000_000_000)
        self.assertEqual(len(self.scan(rule["id"], T0)["submitted"]), 1)
        self.finish(self.submitted[0]["id"])
        self.write("ABC-300-CD2.mkv", ns=1_760_000_000_000_000_000)
        result = self.scan(rule["id"], T0 + 5)
        self.assertEqual(len(result["submitted"]), 1)
        self.assertEqual(len(self.submitted), 2)
        self.assertEqual(sorted(Path(path).name for path in self.submitted[1]["input_files"]),
                         ["ABC-300-CD1.mkv", "ABC-300-CD2.mkv"],
                         "the new part is submitted together with the already known sibling")

    def test_files_present_at_creation_are_baselined_unless_requested(self):
        self.write("OLD-001.mkv", ns=1_760_000_000_000_000_000)
        self.write("OLD-002.mkv", ns=1_760_000_000_000_000_000)
        rule = self.rule(stable_seconds=0, include_existing=False)
        self.assertEqual(self.report(rule["id"])["status"]["committed"], 2, "保存规则时把已有文件记为基线")
        first = self.scan(rule["id"], T0)
        self.assertEqual(first["submitted"], [], "默认只监控新增或变化的文件")
        self.assertEqual(self.submitted, [])

        self.write("NEW-003.mkv", ns=1_760_000_000_000_000_000)
        second = self.scan(rule["id"], T0 + 10)
        self.assertEqual(len(second["submitted"]), 1)
        self.assertEqual(Path(self.submitted[0]["input_directory"]).name, "NEW-003.mkv")

        (self.root / "mount2").mkdir()
        self.write("../mount2/OLD-009.mkv", ns=1_760_000_000_000_000_000)
        existing = self.rule(path=str(self.root / "mount2"), stable_seconds=0, include_existing=True)
        self.assertEqual(len(self.scan(existing["id"], T0 + 10)["submitted"]), 1,
                         "勾选处理已有文件后，已有文件也会进入队列")

    def test_subdirectories_and_exclude_patterns(self):
        rule = self.rule(stable_seconds=0, exclude=["skipme", "*.nfo", "OS-*"])
        self.write("TOP-001.mkv", ns=1_760_000_000_000_000_000)
        self.write("sub/DEEP-001.mkv", ns=1_760_000_000_000_000_000)
        self.write("skipme/IGNORED-001.mkv", ns=1_760_000_000_000_000_000)
        self.write("sub/skipme/IGNORED-002.mkv", ns=1_760_000_000_000_000_000)
        self.write("OS-777.mkv", ns=1_760_000_000_000_000_000)
        result = self.scan(rule["id"], T0)
        names = sorted(Path(task["input_directory"]).name for task in self.submitted)
        self.assertEqual(names, ["DEEP-001.mkv", "TOP-001.mkv"], result)

        (self.root / "flat").mkdir()
        flat = self.rule(path=str(self.root / "flat"), stable_seconds=0, recursive=False)
        self.write("../flat/FLAT-001.mkv", ns=1_760_000_000_000_000_000)
        self.write("../flat/nested/FLAT-002.mkv", ns=1_760_000_000_000_000_000)
        self.submitted.clear()
        self.scan(flat["id"], T0)
        self.assertEqual([Path(task["input_directory"]).name for task in self.submitted], ["FLAT-001.mkv"],
                         "recursive=false only watches the rule directory itself")

    def test_temporary_download_files_and_output_folders_are_ignored(self):
        rule = self.rule(stable_seconds=0)
        self.write("ABC-400.mkv.!qB", ns=1_760_000_000_000_000_000)
        self.write("ABC-401.mkv.part", ns=1_760_000_000_000_000_000)
        self.write("ABC-402.mkv.tmp", ns=1_760_000_000_000_000_000)
        self.write(".incoming/ABC-403.mkv", ns=1_760_000_000_000_000_000)
        self.write("#整理完成/ABC-404/ABC-404.mkv", ns=1_760_000_000_000_000_000)
        self.write("#recycle/ABC-405.mkv", ns=1_760_000_000_000_000_000)
        self.assertEqual(self.scan(rule["id"], T0)["submitted"], [])
        self.assertEqual(self.submitted, [])

        # Renaming the finished temp file into place makes it a new candidate.
        (self.mount / "ABC-400.mkv.!qB").rename(self.mount / "ABC-400.mkv")
        os.utime(self.mount / "ABC-400.mkv", ns=(1_760_000_000_000_000_000, 1_760_000_000_000_000))
        self.assertEqual(len(self.scan(rule["id"], T0 + 5)["submitted"]), 1)

    def test_changed_file_resubmits_only_after_the_previous_task_finishes(self):
        rule = self.rule(stable_seconds=0)
        self.write("ABC-500.mkv", ns=1_760_000_000_000_000_000)
        self.assertEqual(len(self.scan(rule["id"], T0)["submitted"]), 1)
        # The task is still queued: a change must not create a second task.
        self.write("ABC-500.mkv", payload=b"y" * 64, ns=1_760_000_000_000_000_000 + 5 * 10**9)
        waiting = self.scan(rule["id"], T0 + 10)
        self.assertEqual(waiting["submitted"], [])
        self.assertEqual(len(self.submitted), 1)
        self.assertIn("等待", self.report(rule["id"])["status"]["message"])

        self.finish(self.submitted[0]["id"])
        changed = self.scan(rule["id"], T0 + 20)
        self.assertEqual(len(changed["submitted"]), 1, "a changed file may be scraped again once the old task is done")
        self.assertEqual(len(self.submitted), 2)

    def test_submission_cap_bounds_a_large_folder(self):
        rule = self.rule(stable_seconds=0, max_tasks_per_scan=2)
        for index in range(7):
            self.write(f"BULK-{index:03d}.mkv", ns=1_760_000_000_000_000_000)
        self.assertEqual(len(self.scan(rule["id"], T0)["submitted"]), 2)
        self.assertEqual(len(self.scan(rule["id"], T0 + 5)["submitted"]), 2)
        self.assertEqual(len(self.scan(rule["id"], T0 + 10)["submitted"]), 2)
        self.assertEqual(len(self.scan(rule["id"], T0 + 15)["submitted"]), 1)
        self.assertEqual(self.scan(rule["id"], T0 + 20)["submitted"], [])
        self.assertEqual(len(self.submitted), 7, "每个文件只提交一次，且不会整目录重复批量")

    def test_restart_restores_state_without_duplicates(self):
        rule = self.rule(stable_seconds=0)
        self.write("ABC-600.mkv", ns=1_760_000_000_000_000_000)
        self.assertEqual(len(self.scan(rule["id"], T0)["submitted"]), 1)
        before = self.submitted[0]["id"]

        # A fresh process: no in-memory state at all, only the persisted files.
        directory_watch.stop_scheduler()
        directory_watch.reset_runtime()
        restarted = directory_watch.Scheduler(poll_interval=0.05)
        self.addCleanup(restarted.stop)
        same = self.scan(rule["id"], T0 + 30)
        self.assertEqual(same["submitted"], [], "重启后同一文件不会重复入队")
        self.assertEqual(len(self.submitted), 1)
        self.assertEqual(self.submitted[0]["id"], before)

        self.write("ABC-600.mkv", payload=b"z" * 40, ns=1_760_000_000_000_000_000 + 60 * 10**9)
        self.finish(before)
        self.assertEqual(len(self.scan(rule["id"], T0 + 90)["submitted"]), 1, "重启期间发生变化的文件会补交")

    def test_verified_strm_copy_persists_after_original_moves(self):
        rule = self.rule(stable_seconds=0)
        original = self.write("ABC-610.strm", b"https://example.test/video.mp4\n")
        copy = self.write("ABC-610 (1).strm", b"\xef\xbb\xbfhttps://example.test/video.mp4\r\n")
        result = self.scan(rule["id"], T0)
        self.assertEqual(result["submitted_count"], 1, result)
        self.assertEqual(self.submitted[0]["input_files"], [str(original)])
        record = directory_watch.read_state()["rules"][rule["id"]]["committed"][copy.name]
        self.assertEqual(record["status"], "duplicate")
        self.assertEqual(record["original"], str(original))
        self.assertTrue(record["reason"])
        self.assertNotIn("https://", json.dumps(record))
        self.finish(self.submitted[0]["id"])
        original.rename(self.root / original.name)
        directory_watch.reset_runtime()
        self.assertEqual(self.scan(rule["id"], T0 + 30)["submitted_count"], 0)
        self.assertEqual(len(self.submitted), 1, "copy must not become a standalone task")

    def test_copy_skip_prompt_is_visible_once_and_never_leaks_links(self):
        rule = self.rule(stable_seconds=0)
        original = self.write("ABC-616.strm", b"https://example.test/video-616.mp4\n")
        self.write("ABC-616 (1).strm", original.read_bytes())
        first = self.scan(rule["id"], T0)
        self.assertEqual(first["submitted_count"], 1, first)
        expected = "跳过重复副本：ABC-616 (1).strm → ABC-616.strm"
        self.assertIn(expected, first["message"], "检测到副本时必须给出用户可见提示")
        self.assertIn(expected, self.report(rule["id"])["status"]["message"])
        self.assertNotIn("https://", json.dumps(first, ensure_ascii=False))
        self.assertNotIn("https://", json.dumps(self.report(rule["id"]), ensure_ascii=False))
        self.finish(self.submitted[0]["id"])
        second = self.scan(rule["id"], T0 + 30)
        self.assertNotIn("跳过重复副本", second["message"], "重复轮询不得重复刷屏")
        self.assertNotIn("跳过重复副本", self.report(rule["id"])["status"]["message"])

    def test_copy_skip_prompt_survives_a_baselined_folder(self):
        original = self.write("ABC-617.strm", b"https://example.test/video-617.mp4\n")
        self.write("ABC-617 (1).strm", original.read_bytes())
        rule = self.rule(stable_seconds=0)  # create_rule baselines the existing folder
        message = self.report(rule["id"])["status"]["message"]
        self.assertIn("跳过重复副本：ABC-617 (1).strm → ABC-617.strm", message)
        self.assertNotIn("https://", message)
        self.assertEqual(self.scan(rule["id"], T0)["submitted_count"], 0,
                         "基线中的副本和原文件都不应再提交")

    def test_changed_copy_same_stat_is_reevaluated_after_original_moves(self):
        rule = self.rule(stable_seconds=0)
        payload = b"https://example.test/video-a.mp4\n"
        original = self.write("ABC-611.strm", payload)
        copy = self.write("ABC-611 (2).strm", payload)
        self.assertEqual(self.scan(rule["id"], T0)["submitted_count"], 1)
        self.finish(self.submitted[0]["id"])
        original.rename(self.root / original.name)
        before = copy.stat()
        copy.write_bytes(payload.replace(b"video-a", b"video-b"))
        os.utime(copy, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.assertEqual(copy.stat().st_size, before.st_size)
        changed = self.scan(rule["id"], T0 + 30)
        self.assertEqual(changed["submitted_count"], 1, changed)
        self.assertEqual(self.submitted[-1]["input_files"], [str(copy)])
        self.assertEqual(self.scan(rule["id"], T0 + 60)["submitted_count"], 0)

    def test_changed_copy_conflict_is_not_suppressed_and_recorded_once(self):
        rule = self.rule(stable_seconds=0)
        payload = b"https://example.test/video-a.mp4\n"
        self.write("ABC-612.strm", payload)
        copy = self.write("ABC-612 (1).strm", payload)
        self.assertEqual(self.scan(rule["id"], T0)["submitted_count"], 1)
        self.finish(self.submitted[0]["id"])
        before = copy.stat()
        copy.write_bytes(payload.replace(b"video-a", b"video-b"))
        os.utime(copy, ns=(before.st_atime_ns, before.st_mtime_ns))
        result = self.scan(rule["id"], T0 + 30)
        self.assertEqual(result["submitted_count"], 0, result)
        self.assertGreater(result["skipped"], 0, result)
        record = directory_watch.read_state()["rules"][rule["id"]]["committed"][copy.name]
        self.assertNotEqual(record["status"], "duplicate")
        self.assertTrue(record["reason"])
        self.assertNotIn("https://", record["reason"])
        self.assertEqual(self.scan(rule["id"], T0 + 60)["skipped"], 0)

    def test_same_stat_copy_changes_restart_stability_window(self):
        rule = self.rule(stable_seconds=60)
        payload = b"https://example.test/video-a.mp4\n"
        copy = self.write("ABC-615 (1).strm", payload)
        self.assertEqual(self.scan(rule["id"], T0)["submitted_count"], 0)
        before = copy.stat()
        copy.write_bytes(payload.replace(b"video-a", b"video-b"))
        os.utime(copy, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.assertEqual(self.scan(rule["id"], T0 + 50)["submitted_count"], 0)
        self.assertEqual(self.scan(rule["id"], T0 + 65)["submitted_count"], 0)
        self.assertEqual(self.scan(rule["id"], T0 + 111)["submitted_count"], 1)

    def test_unreadable_original_is_not_treated_as_verified_duplicate(self):
        rule = self.rule(stable_seconds=0)
        self.write("ABC-614.strm", b"\xff\xfeinvalid UTF-8")
        copy = self.write("ABC-614 (1).strm", b"https://example.test/video.mp4\n")
        result = self.scan(rule["id"], T0)
        self.assertEqual(result["submitted_count"], 0, result)
        self.assertGreater(result["skipped"], 0, result)
        record = directory_watch.read_state()["rules"][rule["id"]]["committed"][copy.name]
        self.assertNotEqual(record["status"], "duplicate")
        self.assertNotIn("https://", record["reason"])
        self.assertEqual(self.scan(rule["id"], T0 + 30)["skipped"], 0)

    def test_baselined_copy_relation_survives_original_move_before_first_poll(self):
        original = self.write("ABC-613.strm", b"https://example.test/video.mp4\n")
        copy = self.write("ABC-613 (1).strm", original.read_bytes())
        rule = self.rule(stable_seconds=0)
        original.rename(self.root / original.name)
        directory_watch.reset_runtime()
        self.assertEqual(self.scan(rule["id"], T0)["submitted_count"], 0)
        record = directory_watch.read_state()["rules"][rule["id"]]["committed"][copy.name]
        self.assertEqual(record["status"], "duplicate")
        self.assertEqual(record["original"], str(original))

    def test_offline_root_keeps_state_and_recovers(self):
        rule = self.rule(stable_seconds=0)
        self.write("ABC-700.mkv", ns=1_760_000_000_000_000_000)
        self.assertEqual(len(self.scan(rule["id"], T0)["submitted"]), 1)
        parked = self.root / "mount-parked"
        self.mount.rename(parked)

        offline = self.scan(rule["id"], T0 + 30)
        self.assertEqual(offline["state"], "offline")
        self.assertTrue(offline["message"])
        self.assertEqual(self.report(rule["id"])["status"]["state"], "offline")
        self.assertEqual(self.report(rule["id"])["status"]["committed"], 1, "离线时保留已提交签名")

        parked.rename(self.mount)
        recovered = self.scan(rule["id"], T0 + 60)
        self.assertEqual(recovered["state"], "ok")
        self.assertEqual(recovered["submitted"], [], "恢复后已提交的文件不会再入队")
        self.write("ABC-701.mkv", ns=1_760_000_000_000_000_000)
        self.assertEqual(len(self.scan(rule["id"], T0 + 90)["submitted"]), 1, "恢复后新文件继续被提交")

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root ignores directory permissions")
    def test_permission_failure_is_reported_and_recovers(self):
        rule = self.rule(stable_seconds=0)
        blocked = self.mount / "blocked"
        blocked.mkdir()
        self.write("blocked/ABC-710.mkv", ns=1_760_000_000_000_000_000)
        os.chmod(blocked, 0o000)
        self.addCleanup(os.chmod, blocked, 0o755)
        unreadable = self.scan(rule["id"], T0)
        self.assertEqual(unreadable["submitted"], [])
        self.assertEqual(unreadable["state"], "error")
        self.assertIn("权限", unreadable["message"])
        self.assertEqual(self.report(rule["id"])["status"]["state"], "error")

        os.chmod(blocked, 0o755)
        recovered = self.scan(rule["id"], T0 + 10)
        self.assertEqual(len(recovered["submitted"]), 1, "权限恢复后重试成功")

    def test_disabled_rule_stops_submitting_immediately(self):
        rule = self.rule(stable_seconds=0)
        self.assertEqual(self.report(rule["id"])["status"]["committed"], 0, "保存规则时建立空基线")
        self.write("ABC-800.mkv", ns=1_760_000_000_000_000_000)
        directory_watch.set_rule_enabled(rule["id"], False)
        paused = self.scan(rule["id"], T0 + 5)
        self.assertEqual(paused["submitted"], [])
        self.assertEqual(paused["state"], "disabled")
        self.assertEqual(self.report(rule["id"])["status"]["state"], "disabled")
        self.write("ABC-801.mkv", ns=1_760_000_000_000_000_000)
        self.assertEqual(self.scan(rule["id"], T0 + 10)["submitted"], [])
        self.assertEqual(self.submitted, [], "暂停期间不创建任何任务")

        directory_watch.set_rule_enabled(rule["id"], True)
        resumed = self.scan(rule["id"], T0 + 15)
        self.assertEqual(len(resumed["submitted"]), 2, "重新启用后补交暂停期间出现的文件")
        self.assertEqual(sorted(Path(task["input_directory"]).name for task in self.submitted),
                         ["ABC-800.mkv", "ABC-801.mkv"])

    def test_disable_during_scan_stops_further_submissions(self):
        rule = self.rule(stable_seconds=0, max_tasks_per_scan=5)
        for index in range(3):
            self.write(f"MID-{index}.mkv", ns=1_760_000_000_000_000_000)
        original = directory_watch._submit

        def submit_then_disable(active_rule, paths):
            created = original(active_rule, paths)
            directory_watch.set_rule_enabled(active_rule["id"], False)
            return created

        with patch.object(directory_watch, "_submit", side_effect=submit_then_disable):
            result = directory_watch.scan_rule(rule["id"], now=T0)
        self.assertEqual(len(result["submitted"]), 1, "暂停后不再提交后续分组")
        self.assertTrue(result["skipped_run"])
        self.assertIn("已停止", result["message"])
        self.assertEqual(len(self.submitted), 1)
        self.assertEqual(self.report(rule["id"])["status"]["state"], "disabled")

    def test_missing_preset_blocks_submission(self):
        storage.save_preset({**self.preset, "id": "temp-preset"})
        rule = self.rule(stable_seconds=0, preset_id="temp-preset")
        self.write("ABC-810.mkv", ns=1_760_000_000_000_000_000)
        result = self.scan(rule["id"], T0)
        self.assertEqual(len(result["submitted"]), 1)
        self.assertEqual(storage.delete_preset("temp-preset"), True)

        self.write("ABC-811.mkv", ns=1_760_000_000_000_000_000)
        blocked = self.scan(rule["id"], T0 + 10)
        self.assertEqual(blocked["state"], "error")
        self.assertIn("预设", blocked["message"])
        self.assertEqual(len(self.submitted), 1, "预设被删除后不再创建任务")

    def test_skipped_file_is_not_retried_on_every_scan(self):
        storage.save_preset({**self.preset, "form": {"scanner": {"minimum_size": "232MiB"}}})
        rule = self.rule(stable_seconds=0)
        self.write("TINY-001.mkv", ns=1_760_000_000_000_000_000)
        first = self.scan(rule["id"], T0)
        self.assertEqual(first["submitted"], [])
        self.assertEqual(first["skipped"], 1)
        self.assertEqual(self.submitted, [])
        second = self.scan(rule["id"], T0 + 30)
        self.assertEqual(second["skipped"], 0, "同签名的跳过结果会持久保存，不重复尝试")
        self.assertIn("最小匹配文件大小", self.report(rule["id"])["status"]["message"])

    def test_submission_never_holds_the_rule_lock(self):
        """create_tasks must run outside the module lock, or a slow NAS scan would
        freeze the admin API."""
        rule = self.rule(stable_seconds=0)
        self.write("ABC-010.mkv", ns=1_760_000_000_000_000_000)
        entered = threading.Event()
        release = threading.Event()
        original = directory_watch._submit

        def slow_submit(active_rule, paths):
            entered.set()
            release.wait(20)
            return original(active_rule, paths)

        with patch.object(directory_watch, "_submit", side_effect=slow_submit):
            worker = threading.Thread(target=lambda: directory_watch.scan_rule(rule["id"], now=T0))
            worker.start()
            self.assertTrue(entered.wait(10), "扫描应进入提交流程")
            started = time.monotonic()
            directory_watch.set_rule_enabled(rule["id"], True)
            elapsed = time.monotonic() - started
            release.set()
            worker.join(30)
            self.assertLess(elapsed, 5, "提交任务期间管理员接口不应被模块锁阻塞")
        self.assertEqual(len(self.submitted), 1)

    def test_application_data_directory_is_never_ingested(self):
        outside = self.data_dir / "task-output"
        outside.mkdir(parents=True, exist_ok=True)
        (outside / "INSIDE-001.mkv").write_bytes(b"x" * 32)
        os.utime(outside / "INSIDE-001.mkv", ns=(1_760_000_000_000_000_000,) * 2)
        rule = directory_watch.create_rule({
            "name": "整盘", "path": str(self.root), "preset_id": "default", "stable_seconds": 0,
        })
        committed = directory_watch.read_state()["rules"][rule["id"]]["committed"]
        self.assertFalse([rel for rel in committed if rel.startswith("state")],
                         "应用数据目录中的文件不会被监控入队")
        self.assertEqual(self.scan(rule["id"], T0)["submitted"], [])

    def test_directory_symlink_loop_does_not_hang(self):
        rule = self.rule(stable_seconds=0)
        loop = self.mount / "loop"
        loop.mkdir()
        (loop / "back").symlink_to(self.mount, target_is_directory=True)
        self.write("loop/ABC-020.mkv", ns=1_760_000_000_000_000_000)
        submitted = self.scan(rule["id"], T0)
        self.assertEqual(len(submitted["submitted"]), 1, "符号链循环不会重复遍历或卡死")
        self.assertEqual(len(self.submitted), 1)

    def test_concurrent_scans_create_at_most_one_task(self):
        rule = self.rule(stable_seconds=0)
        self.write("ABC-900.mkv", ns=1_760_000_000_000_000_000)
        barrier = threading.Barrier(4)
        results = []

        def worker():
            barrier.wait()
            results.append(directory_watch.scan_rule(rule["id"], now=T0))

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(30)
        self.assertEqual(len(self.submitted), 1, "并发扫描不能重复入队")
        self.assertEqual(sum(len(item["submitted"]) for item in results), 1)

    def test_committed_ledger_does_not_grow_without_bound(self):
        rule = self.rule(stable_seconds=0)
        self.write("KEEP-001.mkv", ns=1_760_000_000_000_000_000)
        self.assertEqual(len(self.scan(rule["id"], T0)["submitted"]), 1)
        state = directory_watch.read_state()
        state["rules"][rule["id"]]["committed"]["GONE-000.mkv"] = {
            "size": 1, "mtime_ns": 1, "status": "submitted", "task_id": "old", "reason": "", "at": "",
        }
        directory_watch.write_state(state)
        self.write("KEEP-002.mkv", ns=1_760_000_000_000_000_000)
        with patch.object(directory_watch, "MAX_COMMITTED_ENTRIES", 1):
            self.assertEqual(len(self.scan(rule["id"], T0 + 10)["submitted"]), 1)
        committed = directory_watch.read_state()["rules"][rule["id"]]["committed"]
        self.assertNotIn("GONE-000.mkv", committed, "超过上限时只清理当前已不存在的记录")
        self.assertIn("KEEP-001.mkv", committed)
        self.assertIn("KEEP-002.mkv", committed)

    def test_corrupt_state_file_is_recovered(self):
        rule = self.rule(stable_seconds=0)
        self.write("ABC-910.mkv", ns=1_760_000_000_000_000_000)
        self.assertEqual(len(self.scan(rule["id"], T0)["submitted"]), 1)
        path = next(iter(self.data_dir.glob("directory-watch-state*.json")))
        path.write_text("{ not json", encoding="utf-8")
        recovered = self.scan(rule["id"], T0 + 10)
        self.assertEqual(recovered["state"], "ok", recovered)
        leftovers = list(self.data_dir.glob("*.tmp"))
        self.assertEqual(leftovers, [], "原子写入不留临时文件")

    def test_scheduler_thread_scans_and_stops_cleanly(self):
        rule = self.rule(stable_seconds=0, poll_seconds=5)
        self.write("ABC-920.mkv", ns=1_760_000_000_000_000_000)
        scheduler = directory_watch.Scheduler(poll_interval=0.2)
        scheduler.start()
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline and not self.submitted:
                time.sleep(0.1)
            self.assertEqual(len(self.submitted), 1, "后台调度线程应按轮询周期扫描")
        finally:
            scheduler.stop(timeout=10)
        self.assertFalse(scheduler.running)
        self.assertFalse(any(thread.name == "directory-watch" and thread.is_alive()
                             for thread in threading.enumerate()))
        self.assertEqual(directory_watch.read_state()["rules"][rule["id"]]["submitted_total"], 1,
                         "扫描结果已原子持久化")

    def test_scheduler_stop_handles_unstarted_and_repeated_stops(self):
        scheduler = directory_watch.Scheduler(poll_interval=0.05)
        self.assertEqual(scheduler.stop(timeout=0), None, "从未启动的调度器停止时必须无异常")
        scheduler.stop(timeout=0)
        self.assertFalse(scheduler.running)
        self.assertIsNone(scheduler._thread)

    def test_scheduler_stop_skips_a_thread_that_was_created_but_never_started(self):
        # Same boundary as the shared-process regression: an import patches
        # Thread.start, leaving a created-but-unstarted thread behind.
        scheduler = directory_watch.Scheduler(poll_interval=0.05)
        with patch.object(threading.Thread, "start"):
            scheduler.start()
        self.assertFalse(scheduler.running)
        scheduler.stop(timeout=0)
        self.assertIsNone(scheduler._thread)

    def test_scheduler_stop_accepts_an_already_finished_thread(self):
        scheduler = directory_watch.Scheduler(poll_interval=0.05)
        finished = threading.Thread(target=lambda: None, name="directory-watch-finished")
        finished.start()
        finished.join(5)
        self.assertFalse(finished.is_alive())
        scheduler._thread = finished
        scheduler.stop(timeout=0)
        scheduler.stop(timeout=0)
        self.assertIsNone(scheduler._thread)

    def test_scheduler_stop_timeout_restarts_the_same_worker(self):
        entered, release = threading.Event(), threading.Event()
        calls: list[threading.Thread] = []

        def run_due(*args, **kwargs):
            calls.append(threading.current_thread())
            if len(calls) == 1:
                entered.set()
                release.wait(5)
            return []

        scheduler = directory_watch.Scheduler(poll_interval=0.05)
        self.enterContext(patch.object(scheduler, "run_due", side_effect=run_due))
        self.addCleanup(scheduler.stop, 5)
        self.addCleanup(release.set)
        before = {thread.ident for thread in threading.enumerate()
                  if thread.name == "directory-watch" and thread.is_alive()}
        scheduler.start()
        self.assertTrue(entered.wait(5), "调度线程应进入扫描")
        first = scheduler._thread
        scheduler.stop(timeout=0)
        self.assertTrue(first.is_alive(), "阻塞中的工作线程不会被超时停止杀掉")
        self.assertIs(scheduler._thread, first, "超时停止后必须保留存活线程引用")
        self.assertFalse(scheduler.running, "停止中的线程不再算运行中")
        scheduler.start()
        self.assertIs(scheduler._thread, first, "超时停止后重启不得创建第二个线程")
        alive = {thread.ident for thread in threading.enumerate()
                 if thread.name == "directory-watch" and thread.is_alive()}
        self.assertEqual(alive, before | {first.ident}, "同一时间只允许一个调度线程")
        release.set()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and len(calls) < 2:
            time.sleep(0.02)
        self.assertGreaterEqual(len(calls), 2, "工作线程应继续轮询而不是被第二个线程取代")
        scheduler.stop(timeout=5)
        self.assertFalse(scheduler.running)
        self.assertIsNone(scheduler._thread)

    def test_scheduler_final_stop_cancels_pending_restart(self):
        # stop(timeout=0) → start() → stop(timeout=0) while the worker is
        # blocked inside run_due(): the last stop must win, the worker exits.
        entered, release = threading.Event(), threading.Event()
        calls: list[threading.Thread] = []

        def run_due(*args, **kwargs):
            calls.append(threading.current_thread())
            if len(calls) == 1:
                entered.set()
                release.wait(5)
            return []

        scheduler = directory_watch.Scheduler(poll_interval=0.05)
        self.enterContext(patch.object(scheduler, "run_due", side_effect=run_due))
        self.addCleanup(release.set)
        scheduler.start()
        self.assertTrue(entered.wait(5), "调度线程应进入扫描")
        first = scheduler._thread
        scheduler.stop(timeout=0)
        scheduler.start()
        self.assertIs(scheduler._thread, first, "超时停止后重启复用原线程")
        scheduler.stop(timeout=0)
        release.set()
        first.join(2)
        self.assertFalse(first.is_alive(), "最后发生的停止必须让旧线程真正退出")
        self.assertFalse(scheduler.running, "最终停止后调度器不得报告运行中")
        poll_count = len(calls)
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(len(calls), poll_count, "退出后的旧线程不得继续轮询")
        alive = [t for t in threading.enumerate()
                 if t.name == "directory-watch" and t.is_alive()]
        self.assertEqual(alive, [], "不得存在第二调度线程")
        scheduler.start()
        try:
            self.assertIsNot(scheduler._thread, first, "完全退出后重启应创建新线程")
        finally:
            scheduler.stop(timeout=5)
        self.assertIsNone(scheduler._thread)

    def test_scheduler_restarts_after_a_clean_stop(self):
        scheduler = directory_watch.Scheduler(poll_interval=0.05)
        self.addCleanup(scheduler.stop, 5)
        scheduler.start()
        first = scheduler._thread
        scheduler.stop(timeout=5)
        self.assertFalse(first.is_alive())
        self.assertIsNone(scheduler._thread)
        scheduler.start()
        self.assertIsNot(scheduler._thread, first, "正常退出后重启应创建新线程")
        self.assertTrue(scheduler.running)
        scheduler.stop(timeout=5)
        self.assertIsNone(scheduler._thread)

    def test_scheduler_stop_from_inside_the_worker_is_safe(self):
        scheduler = directory_watch.Scheduler(poll_interval=0.05)
        stopped = threading.Event()

        def run_due(*args, **kwargs):
            scheduler.stop(timeout=0)
            stopped.set()
            return []

        with patch.object(scheduler, "run_due", side_effect=run_due):
            scheduler.start()
            self.assertTrue(stopped.wait(5))
            worker = scheduler._thread
            worker.join(5)
        self.assertFalse(worker.is_alive(), "线程内部停止后应自行退出")
        self.assertFalse(scheduler.running)
        scheduler.start()
        try:
            self.assertIsNot(scheduler._thread, worker, "线程内部停止后仍可重新启动")
            self.assertTrue(scheduler.running)
        finally:
            scheduler.stop(timeout=5)
        self.assertIsNone(scheduler._thread)

    # ------------------------------------------------------------------- HTTP
    def client(self, admin: bool = True):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from javsp_web.auth import current_user

        app = FastAPI()
        app.include_router(directory_watch_router.router)
        app.dependency_overrides[current_user] = lambda: {"username": "tester", "role": "admin" if admin else "operator"}
        client = TestClient(app)
        self.addCleanup(client.close)
        return client

    def test_router_crud_and_validation(self):
        client = self.client()
        self.assertEqual(client.post("/api/directory-watch/rules", json={"path": "/nope/missing"}).status_code, 400)
        bad_preset = client.post("/api/directory-watch/rules", json={"path": str(self.mount), "preset_id": "ghost"})
        self.assertEqual(bad_preset.status_code, 400)
        self.assertIn("预设", bad_preset.json()["detail"])
        for payload in (
            {"path": str(self.mount), "poll_seconds": 1},
            {"path": str(self.mount), "stable_seconds": 999999},
            {"path": str(self.mount), "exclude": ["../etc"]},
            {"path": str(self.mount), "exclude": ["/absolute"]},
        ):
            response = client.post("/api/directory-watch/rules", json=payload)
            self.assertEqual(response.status_code, 400, payload)

        created = client.post("/api/directory-watch/rules", json={"name": "规则", "path": str(self.mount)})
        self.assertEqual(created.status_code, 201, created.text)
        rule = created.json()
        self.assertEqual((rule["poll_seconds"], rule["stable_seconds"]), (30, 60), "默认 30 秒扫描、60 秒稳定")
        self.assertEqual(rule["status"]["state"], "ok", "保存规则时已建立基线")
        self.assertEqual(rule["status"]["committed"], 0)

        listed = client.get("/api/directory-watch/rules").json()
        self.assertEqual([item["id"] for item in listed["rules"]], [rule["id"]])
        self.assertEqual(listed["limits"]["poll_seconds"]["default"], 30)
        self.assertIn("directory_watch_enabled", listed["scheduler"])

        (self.mount / "sub").mkdir()
        overlap = client.post("/api/directory-watch/rules", json={"path": str(self.mount / "sub")})
        self.assertEqual(overlap.status_code, 400, "重叠目录会重复提交，必须拒绝")
        self.assertIn("重叠", overlap.json()["detail"])

        paused = client.post(f"/api/directory-watch/rules/{rule['id']}/pause")
        self.assertEqual(paused.status_code, 200)
        self.assertFalse(paused.json()["enabled"])
        self.assertEqual(paused.json()["status"]["state"], "disabled")
        resumed = client.post(f"/api/directory-watch/rules/{rule['id']}/resume")
        self.assertTrue(resumed.json()["enabled"])

        scanned = client.post(f"/api/directory-watch/rules/{rule['id']}/scan")
        self.assertEqual(scanned.status_code, 200, scanned.text)
        self.assertEqual(scanned.json()["state"], "ok")

        self.assertEqual(client.delete(f"/api/directory-watch/rules/{rule['id']}").status_code, 200)
        self.assertEqual(client.delete(f"/api/directory-watch/rules/{rule['id']}").status_code, 404)
        self.assertEqual(client.post("/api/directory-watch/rules/ghost/scan").status_code, 404)

    def test_router_requires_admin(self):
        client = self.client(admin=False)
        self.assertEqual(client.get("/api/directory-watch/rules").status_code, 403)
        self.assertEqual(client.post("/api/directory-watch/rules", json={"path": str(self.mount)}).status_code, 403)

    def test_rule_edit_resets_observation_but_pause_does_not(self):
        rule = self.rule(stable_seconds=0)
        self.write("ABC-930.mkv", ns=1_760_000_000_000_000_000)
        self.assertEqual(len(self.scan(rule["id"], T0)["submitted"]), 1)
        self.finish(self.submitted[0]["id"])

        paused = directory_watch.set_rule_enabled(rule["id"], False)
        self.assertEqual(directory_watch.read_state()["rules"][rule["id"]]["committed"].keys(),
                         {"ABC-930.mkv"}, f"暂停不重置观察状态: {paused}")
        directory_watch.set_rule_enabled(rule["id"], True)
        self.assertEqual(self.scan(rule["id"], T0 + 10)["submitted"], [], "暂停恢复后已提交文件不再提交")

        updated = directory_watch.update_rule(rule["id"], {
            "name": "改过的规则", "path": str(self.mount), "preset_id": "default",
            "poll_seconds": 30, "stable_seconds": 0, "exclude": [],
        })
        self.assertEqual(updated["name"], "改过的规则")
        committed = directory_watch.read_state()["rules"][rule["id"]]["committed"]
        self.assertEqual(list(committed), ["ABC-930.mkv"])
        self.assertEqual(committed["ABC-930.mkv"]["status"], "baseline",
                         "修改规则后重新建立基线，而不是重复提交旧文件")
        self.assertEqual(self.scan(rule["id"], T0 + 20)["submitted"], [])


    def test_index_html_mounts_the_panel_and_assets(self):
        document = (ROOT / "javsp_web/web/index.html").read_text(encoding="utf-8")
        self.assertIn('id="directory-watch-panel"', document)
        self.assertIn('/assets/directory-watch.js?v=__ASSET_VERSION__', document)
        self.assertIn('/assets/directory-watch.css?v=__ASSET_VERSION__', document)
        panel_index = document.index('id="directory-watch-panel"')
        self.assertLess(panel_index, document.index('id="auto-scrape-schedule-list"'),
                        "目录监控位于自动刮削页的最前面")
        self.assertTrue((ROOT / "javsp_web/web/assets/directory-watch.js").is_file())
        self.assertTrue((ROOT / "javsp_web/web/assets/directory-watch.css").is_file())


class UnifiedTriggerTests(unittest.TestCase):
    """trigger=watch/schedule 统一规则模型与迁移验收。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data_dir = self.root / "state"
        old = storage.DATA_DIR
        for name, value in list(vars(storage).items()):
            if isinstance(value, Path) and value.is_relative_to(old):
                self.enterContext(patch.object(storage, name, self.data_dir / value.relative_to(old)))
        self.enterContext(patch.object(tasks, "DATA_DIR", self.data_dir))
        self.enterContext(patch.object(tasks, "_TASK_COVERS_DIR", self.data_dir / "task-covers"))
        self.enterContext(patch.object(tasks, "_TASK_COOKIECLOUD_DIR", self.data_dir / "task-cookiecloud"))
        self.enterContext(patch.object(tasks, "_logs", {}))
        self.enterContext(patch.object(tasks, "_cancelled_tasks", set()))
        self.enterContext(patch.object(tasks, "_deleted_tasks", set()))
        self.enterContext(patch.object(tasks, "_processes", {}))
        self.enterContext(patch.object(tasks, "_google_captcha_sessions", {}))
        storage.ensure_seed_data()
        config = yaml.safe_load((ROOT / "vendor/JavSP/config.yml").read_text(encoding="utf-8"))
        form = {"scanner": {"minimum_size": "1B", "input_directory": None, "manual": False}}
        storage.save_preset({
            "id": "default", "name": "统一规则测试", "mode": "form", "form": form,
            "content": yaml.safe_dump(config, allow_unicode=True), "created_at": "", "updated_at": "",
        })
        self.mount = self.root / "mount"
        self.mount.mkdir()
        self.submitted: list[dict] = []
        self.enterContext(patch.object(tasks, "_enqueue_task", side_effect=self.submitted.append))
        directory_watch.stop_scheduler()

    # ------------------------------------------------------------- trigger
    def test_trigger_must_be_watch_or_schedule_and_mutually_exclusive(self):
        with self.assertRaises(directory_watch.RuleError):
            directory_watch.normalize_payload({"path": str(self.mount), "trigger": "both"})
        with self.assertRaises(directory_watch.RuleError):
            directory_watch.normalize_payload({"path": str(self.mount), "trigger": "schedule"})  # 无 cron
        with self.assertRaises(directory_watch.RuleError):
            directory_watch.normalize_payload({"path": str(self.mount), "trigger": "schedule", "cron": "bad"})
        rule = directory_watch.normalize_payload({"path": str(self.mount), "trigger": "schedule", "cron": "0 2 * * *"})
        self.assertEqual((rule["trigger"], rule["cron"]), ("schedule", "0 2 * * *"))
        watch = directory_watch.normalize_payload({"path": str(self.mount)})
        self.assertEqual((watch["trigger"], watch["cron"]), ("watch", ""))
        stored = directory_watch.read_rules()
        self.assertTrue(all(rule.get("trigger") in ("watch", "schedule") for rule in stored))

    def test_watch_rule_creates_without_any_time_fields(self):
        # watch（监控新增）只需要目录 + 预设；时间/间隔字段整体省略时给默认值，不报错。
        rule = directory_watch.create_rule({
            "name": "纯监控", "path": str(self.mount), "preset_id": "default", "trigger": "watch",
        })
        self.assertEqual(rule["trigger"], "watch")
        self.assertEqual(rule["cron"], "")
        self.assertEqual((rule["poll_seconds"], rule["stable_seconds"], rule["max_tasks_per_scan"]), (30, 60, 20),
                         "缺省时间字段使用默认值")
        # 前端空输入会提交 0：0 不是合法下限，视为未填写而不是报错。
        zeroed = directory_watch.normalize_payload({
            "path": str(self.mount), "trigger": "watch", "poll_seconds": 0, "max_tasks_per_scan": 0,
        })
        self.assertEqual((zeroed["poll_seconds"], zeroed["max_tasks_per_scan"]), (30, 20))
        # 但明确填写且越界的值仍然报错，不会被静默纠正。
        with self.assertRaises(directory_watch.RuleError):
            directory_watch.normalize_payload({"path": str(self.mount), "trigger": "watch", "poll_seconds": 3})

    def test_cron_mode_still_requires_a_valid_cron(self):
        for payload in (
            {"path": str(self.mount), "trigger": "schedule"},  # 缺 cron
            {"path": str(self.mount), "trigger": "schedule", "cron": "bad"},
            {"path": str(self.mount), "trigger": "schedule", "cron": ""},  # watch 的默认值救不了 schedule
        ):
            with self.assertRaises(directory_watch.RuleError):
                directory_watch.create_rule(payload)
        rule = directory_watch.create_rule({"path": str(self.mount), "trigger": "schedule", "cron": "0 2 * * *"})
        self.assertEqual(rule["cron"], "0 2 * * *")

    def test_legacy_watch_rule_with_time_fields_still_loads(self):
        # 旧数据：watch 规则带调度时间字段，读取时不报错、字段照常保留。
        legacy = {
            "id": "legacy-watch", "name": "旧规则", "trigger": "watch", "path": str(self.mount),
            "preset_id": "default", "poll_seconds": 15, "stable_seconds": 120,
            "max_tasks_per_scan": 5, "cron": "0 3 * * *", "enabled": True,
            "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00",
        }
        directory_watch.write_rules([legacy])
        rules = directory_watch.read_rules()
        self.assertEqual(len(rules), 1)
        loaded = rules[0]
        self.assertEqual((loaded["trigger"], loaded["poll_seconds"], loaded["stable_seconds"]), ("watch", 15, 120),
                         "旧 watch 规则的时间字段原样保留，不强制迁移")
        self.assertEqual(loaded["cron"], "", "watch 规则的 cron 不参与调度，读取时被清空属正常归一化")
        # 旧的带 cron 的 watch 规则更新后仍可用，且更新时保持 watch 语义。
        updated = directory_watch.update_rule("legacy-watch", {"name": "改名", "cron": "0 4 * * *"})
        self.assertEqual((updated["trigger"], updated["cron"], updated["poll_seconds"]), ("watch", "", 15))

    def test_schedule_rule_never_enters_the_polling_scanner(self):
        rule = directory_watch.create_rule({
            "name": "定时", "path": str(self.mount), "trigger": "schedule", "cron": "0 2 * * *",
        })
        self.assertEqual(rule["trigger"], "schedule")
        # watch 路径的 scan_rule 对 schedule 规则不提交任何任务（语义互斥）。
        self.write_file("ABC-100.mkv")
        result = directory_watch.scan_rule(rule["id"], now=T0)
        self.assertEqual(result["submitted"], [], "schedule 规则不得走 watch 轮询提交")

    def write_file(self, rel: str):
        path = self.mount / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * 32)
        os.utime(path, ns=(1_760_000_000_000_000_000,) * 2)
        return path

    # ------------------------------------------------------------ migration
    def test_migration_preserves_disabled_rules_and_is_idempotent(self):
        storage.save_auto_scrape_schedules([
            {"id": "sched-on", "name": "启用", "enabled": True, "cron": "5 3 * * *",
             "input_directory": str(self.mount), "preset_id": "default",
             "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00",
             "last_run_key": "", "last_run_at": "", "last_result": "尚未执行", "runs": []},
            {"id": "sched-off", "name": "停用", "enabled": False, "cron": "0 4 * * *",
             "input_directory": str(self.mount), "preset_id": "default",
             "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00",
             "last_run_key": "", "last_run_at": "", "last_result": "尚未执行", "runs": []},
        ])
        first = directory_watch.migrate_legacy_schedules()
        self.assertEqual((first["checked"], first["imported"]), (2, 2))
        rules = {rule["id"]: rule for rule in directory_watch.read_rules()
                 if rule.get("trigger") == "schedule"}
        self.assertEqual(rules["sched-on"]["enabled"], True, "启用状态保留")
        self.assertEqual(rules["sched-off"]["enabled"], False, "停用规则也迁移并保留停用")
        self.assertTrue(all(rule.get("migrated") for rule in rules.values()))
        self.assertEqual(rules["sched-on"]["cron"], "5 3 * * *")
        self.assertEqual(rules["sched-on"]["preset_id"], "default")
        # 稳定 ID：旧 id 直接成为统一规则 id。
        # 幂等：重跑不重复导入。
        second = directory_watch.migrate_legacy_schedules()
        self.assertEqual((second["imported"], second["skipped_existing"]), (0, 2))
        # 旧文件不删除不重写。
        self.assertEqual(len(storage.list_auto_scrape_schedules()), 2)

    def test_migration_recovers_from_an_interrupted_run(self):
        # 模拟中断：只写了一半（imported 未落盘）后进程崩溃 → 重跑完整迁移。
        storage.save_auto_scrape_schedules([
            {"id": "half", "name": "中断", "enabled": True, "cron": "0 5 * * *",
             "input_directory": str(self.mount), "preset_id": "default",
             "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00",
             "last_run_key": "", "last_run_at": "", "last_result": "尚未执行", "runs": []},
        ])
        # 部分落盘：规则文件里已有一个无关 watch 规则，迁移必须在其后追加。
        directory_watch.create_rule({"name": "监控", "path": str(self.mount)})
        directory_watch.delete_rule(next(iter([r["id"] for r in directory_watch.read_rules()])))
        report = directory_watch.migrate_legacy_schedules()
        self.assertEqual(report["imported"], 1)
        ids = [rule["id"] for rule in directory_watch.read_rules()]
        self.assertIn("half", ids)

    # ------------------------------------------------------------- dedupe
    def test_overlapping_rules_submit_a_file_exactly_once(self):
        # 迁移允许 schedule 与 watch 目录重叠；提交守卫保证只入队一次。
        outer = self.root / "outer"
        inner = outer / "inner"
        inner.mkdir(parents=True)
        first = {
            "id": "legacy-watch", "name": "外层", "enabled": True, "trigger": "watch",
            "path": str(outer), "preset_id": "default", "recursive": True, "exclude": [],
            "include_existing": False, "poll_seconds": 30, "stable_seconds": 0,
            "max_tasks_per_scan": 20, "cron": "", "migrated": True, "generation": 1,
            "created_at": "", "updated_at": "",
        }
        # 直接写统一存储，绕过创建时的重叠校验，模拟迁移产生的重叠规则。
        directory_watch.write_rules([first, {**first, "id": "second-rule", "name": "内层"}])
        # 两条规则各自建立基线（此刻目录为空）。
        directory_watch.scan_rule("legacy-watch", now=T0)
        directory_watch.scan_rule("second-rule", now=T0)
        target = inner / "ABC-200.mkv"
        target.write_bytes(b"x" * 32)
        os.utime(target, ns=(1_760_000_000_000_000_000,) * 2)
        # 顺序扫描两条规则，对同一文件合计只允许提交一次。
        directory_watch.scan_rule("legacy-watch", now=T0 + 10)
        directory_watch.scan_rule("second-rule", now=T0 + 10)
        self.assertEqual(len(self.submitted), 1, "重叠规则对同一文件只能提交一次")
        # 任务完成后，另一条规则也不得重复提交。
        tasks._persist({**tasks.get_task(self.submitted[0]["id"]), "status": "succeeded",
                        "finished_at": "2026-10-23T00:00:00+00:00"})
        directory_watch.scan_rule("second-rule", now=T0 + 20)
        directory_watch.scan_rule("legacy-watch", now=T0 + 20)
        self.assertEqual(len(self.submitted), 1, "已提交过的文件不会被另一条规则再次入队")

    # ----------------------------------------------------------- scheduling
    def test_schedule_trigger_claims_the_minute_and_runs_full_scan(self):
        rule = directory_watch.create_rule({
            "name": "定时", "path": str(self.mount), "trigger": "schedule", "cron": "* * * * *",
        })
        self.write_file("ABC-300.mkv")
        outcome = directory_watch.run_schedule_rule(rule["id"], "2026-10-23T18:00")
        self.assertEqual(outcome["state"], "ok")
        self.assertEqual(len(self.submitted), 1, "schedule 触发走全量扫描")
        self.assertEqual(self.submitted[0]["source"], "schedule")
        self.assertEqual(self.submitted[0]["schedule_id"], rule["id"])
        repeat = directory_watch.run_schedule_rule(rule["id"], "2026-10-23T18:00")
        self.assertEqual(repeat["state"], "duplicate", "同一分钟声明不重复执行")
        self.assertEqual(len(self.submitted), 1)

    def test_schedule_trigger_skips_while_previous_batch_is_active(self):
        rule = directory_watch.create_rule({
            "name": "定时", "path": str(self.mount), "trigger": "schedule", "cron": "* * * * *",
        })
        self.write_file("ABC-310.mkv")
        first = directory_watch.run_schedule_rule(rule["id"], "2026-10-23T18:01")
        self.assertEqual(first["state"], "ok")
        self.assertEqual(len(self.submitted), 1)
        # 队列里的任务未完成：下一次触发跳过而不是堆积。
        second = directory_watch.run_schedule_rule(rule["id"], "2026-10-23T18:02")
        self.assertEqual(second["state"], "skipped")
        self.assertIn("尚未完成", second["message"])
        self.assertEqual(len(self.submitted), 1)
        # 任务完成后恢复触发。
        tasks._persist({**tasks.get_task(self.submitted[0]["id"]), "status": "succeeded",
                        "finished_at": "2026-10-23T18:03:00+00:00"})
        third = directory_watch.run_schedule_rule(rule["id"], "2026-10-23T18:04")
        self.assertEqual(third["state"], "ok")

    def test_schedule_failure_is_recorded_and_retryable(self):
        rule = directory_watch.create_rule({
            "name": "定时", "path": str(self.mount), "trigger": "schedule", "cron": "* * * * *",
        })
        self.write_file("ABC-320.mkv")
        with patch.object(directory_watch, "_submit_schedule", side_effect=RuntimeError("boom")):
            failed = directory_watch.run_schedule_rule(rule["id"], "2026-10-23T19:00")
        self.assertEqual(failed["state"], "error")
        self.assertIn("执行失败", failed["message"])
        # 失败不吞文件：下一分钟重试可以成功。
        recovered = directory_watch.run_schedule_rule(rule["id"], "2026-10-23T19:01")
        self.assertEqual(recovered["state"], "ok")
        self.assertEqual(len(self.submitted), 1)

    def test_disabled_schedule_rule_never_fires(self):
        rule = directory_watch.create_rule({
            "name": "定时", "path": str(self.mount), "trigger": "schedule", "cron": "* * * * *",
        })
        directory_watch.set_rule_enabled(rule["id"], False)
        self.write_file("ABC-330.mkv")
        scheduler = directory_watch.Scheduler(poll_interval=0.05)
        scheduler.start()
        try:
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and not self.submitted:
                time.sleep(0.05)
        finally:
            scheduler.stop(timeout=5)
        self.assertEqual(self.submitted, [], "停用的 schedule 规则不触发")

    def test_scheduler_fires_due_schedule_rules(self):
        rule = directory_watch.create_rule({
            "name": "定时", "path": str(self.mount), "trigger": "schedule", "cron": "* * * * *",
        })
        self.write_file("ABC-340.mkv")
        scheduler = directory_watch.Scheduler(poll_interval=0.2)
        scheduler.start()
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline and not self.submitted:
                time.sleep(0.1)
        finally:
            scheduler.stop(timeout=10)
        self.assertEqual(len(self.submitted), 1, "调度线程按 cron 分钟触发 schedule 规则")
        self.assertEqual(directory_watch.read_state()["rules"][rule["id"]]["last_schedule_run_key"],
                         time.strftime("%Y-%m-%dT%H:%M"))

    def test_legacy_api_shell_reads_the_unified_store(self):
        from fastapi.testclient import TestClient
        from javsp_web import server as server_module

        with patch.dict(server_module.app.dependency_overrides,
                        {server_module.current_user: lambda: {"username": "tester", "role": "admin"}}):
            client = TestClient(server_module.app)
            self.addCleanup(client.close)
            created = client.post("/api/auto-scrape-schedules", json={
                "name": "壳测试", "cron": "0 6 * * *", "input_directory": str(self.mount),
                "preset_id": "default", "enabled": True,
            })
            self.assertEqual(created.status_code, 200, created.text)
            body = created.json()
            self.assertEqual(body["cron"], "0 6 * * *")
            listed = client.get("/api/auto-scrape-schedules").json()
            self.assertEqual([item["id"] for item in listed], [body["id"]])
            unified = directory_watch.get_rule(body["id"])
            self.assertIsNotNone(unified, "旧 API 创建的规则落在统一存储")
            self.assertEqual(unified["trigger"], "schedule")
            deleted = client.delete(f"/api/auto-scrape-schedules/{body['id']}")
            self.assertEqual(deleted.status_code, 200)
            self.assertIsNone(directory_watch.get_rule(body["id"]))


class UnifiedAcceptanceTests(unittest.TestCase):
    setUp = UnifiedTriggerTests.setUp
    write_file = UnifiedTriggerTests.write_file
    """Boundary regressions that the initial happy-path suite did not exercise."""

    def legacy(self, **changes):
        schedule = {"id": "legacy", "name": "旧定时", "enabled": False,
            "cron": "0 2 * * *", "input_directory": str(self.mount), "preset_id": "default",
            "timezone": "Asia/Shanghai", "created_at": "2026-01-01", "updated_at": "2026-01-02",
            "last_run_key": "2026-10-23T02:00", "last_run_at": "2026-10-23T02:00:00+08:00",
            "last_result": "旧结果", "runs": [{"id": "2026-10-23T02:00", "started_at": "2026-10-23T02:00:00+08:00",
                "result": "旧结果", "task_ids": ["historic-task"]}]}
        schedule.update(changes)
        storage.save_auto_scrape_schedules([schedule])
        return schedule

    def client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from javsp_web.auth import require_admin
        app = FastAPI()
        app.include_router(directory_watch_router.router)
        app.dependency_overrides[require_admin] = lambda: {"role": "admin"}
        client = TestClient(app)
        self.addCleanup(client.close)
        return client

    def finish(self, task, status="succeeded"):
        tasks._persist({**tasks.get_task(task["id"]), "status": status,
                        "finished_at": "2026-10-23T00:00:00+00:00"})

    def overlapping(self):
        one = directory_watch.create_rule({"path": str(self.mount), "stable_seconds": 0})
        two = {**one, "id": "second", "name": "第二条"}
        directory_watch.write_rules([one, two])
        directory_watch.scan_rule(two["id"], now=T0)
        return one, two

    def test_api_accepts_trigger_and_rejects_invalid_cron_and_mode(self):
        client = self.client()
        for trigger, cron in [("both", ""), ("schedule", ""), ("schedule", "0 0 * * * *")]:
            result = client.post("/api/directory-watch/rules", json={"path": str(self.mount), "trigger": trigger, "cron": cron})
            self.assertEqual(result.status_code, 400, result.text)
        result = client.post("/api/directory-watch/rules", json={"path": str(self.mount), "trigger": "schedule", "cron": "0 2 * * *"})
        self.assertEqual(result.status_code, 201, result.text)
        rule = result.json()
        self.assertEqual((rule["trigger"], rule["cron"]), ("schedule", "0 2 * * *"))
        self.write_file("ABC-900.mkv")
        self.assertEqual(directory_watch.scan_rule(rule["id"], now=T0)["submitted"], [])
        manual = client.post(f"/api/directory-watch/rules/{rule['id']}/scan")
        self.assertEqual(manual.json()["created"], 1, manual.text)
        self.assertEqual(self.submitted[0]["source"], "schedule")
        changed = client.put(f"/api/directory-watch/rules/{rule['id']}", json={"trigger": "watch"})
        self.assertEqual((changed.json()["trigger"], changed.json()["cron"]), ("watch", ""))

    def test_migration_preserves_offline_disabled_history_and_timezone(self):
        old = self.legacy(input_directory=str(self.root / "offline"))
        before = storage.AUTO_SCRAPE_SCHEDULES_FILE.read_bytes()
        self.assertEqual(directory_watch.migrate_legacy_schedules()["imported"], 1)
        rule = directory_watch.get_rule("legacy")
        self.assertFalse(rule["enabled"])
        self.assertEqual(rule["timezone"], "Asia/Shanghai")
        self.assertEqual(rule["path"], old["input_directory"])
        self.assertEqual(directory_watch.schedule_history("legacy")["runs"], old["runs"])
        stored = json.loads(directory_watch._rules_file().read_text())
        self.assertEqual(stored["migration_version"], directory_watch.MIGRATION_VERSION)
        self.assertEqual(stored["legacy_schedule_ids"], {"legacy": "legacy"})
        self.assertEqual(storage.AUTO_SCRAPE_SCHEDULES_FILE.read_bytes(), before)
        directory_watch.delete_rule("legacy")
        directory_watch.migrate_legacy_schedules()
        self.assertIsNone(directory_watch.get_rule("legacy"), "deleted imports must not resurrect")

    def test_real_atomic_write_interruption_before_and_after_replace(self):
        self.legacy()
        original = directory_watch._atomic_write
        with patch.object(directory_watch, "_atomic_write", side_effect=OSError("disk interrupted")):
            with self.assertRaises(OSError):
                directory_watch.migrate_legacy_schedules()
        self.assertIsNone(directory_watch.get_rule("legacy"))
        def write_then_crash(path, payload):
            original(path, payload)
            raise OSError("process stopped after replace")
        with patch.object(directory_watch, "_atomic_write", side_effect=write_then_crash):
            with self.assertRaises(OSError):
                directory_watch.migrate_legacy_schedules()
        report = directory_watch.migrate_legacy_schedules()
        self.assertEqual(report["imported"], 0)
        self.assertEqual(len(directory_watch.read_rules()), 1)
        self.assertEqual(len(directory_watch.schedule_history("legacy")["runs"]), 1)

    def test_id_collision_keeps_both_rules_and_history_mapping(self):
        watch = directory_watch.create_rule({"path": str(self.mount)})
        self.legacy(id=watch["id"])
        directory_watch.migrate_legacy_schedules()
        rules = directory_watch.read_rules()
        self.assertEqual(len(rules), 2)
        schedule = next(rule for rule in rules if rule["trigger"] == "schedule")
        self.assertNotEqual(schedule["id"], watch["id"])
        self.assertEqual(len(directory_watch.schedule_history(schedule["id"])["runs"]), 1)
        directory_watch.migrate_legacy_schedules()
        self.assertEqual(len(directory_watch.read_rules()), 2)

    def test_history_edit_delete_and_minute_claim_survive_restart(self):
        self.legacy(enabled=True)
        directory_watch.migrate_legacy_schedules()
        self.assertEqual(directory_watch.run_schedule_rule("legacy", "2026-10-23T02:00")["state"], "duplicate")
        self.write_file("ABC-901.mkv")
        directory_watch.run_schedule_rule("legacy", "2026-10-23T03:00")
        directory_watch.update_rule("legacy", {"name": "改名"})
        history = directory_watch.schedule_history("legacy")
        self.assertEqual(len(history["runs"]), 2)
        self.assertEqual(history["last_run_key"], "2026-10-23T03:00")
        self.assertTrue(directory_watch.delete_schedule_run("legacy", "2026-10-23T02:00"))
        directory_watch.migrate_legacy_schedules()
        self.assertEqual([run["id"] for run in directory_watch.schedule_history("legacy")["runs"]], ["2026-10-23T03:00"])

    def test_failed_watch_task_is_retryable_on_same_and_other_rule(self):
        one, two = self.overlapping()
        self.write_file("ABC-902.mkv")
        directory_watch.scan_rule(one["id"], now=T0 + 1)
        self.finish(self.submitted[0], "failed")
        directory_watch.scan_rule(two["id"], now=T0 + 2)
        self.assertEqual(len(self.submitted), 2, "failed task cannot block another rule")
        self.finish(self.submitted[1], "failed")
        directory_watch.scan_rule(one["id"], now=T0 + 3)
        self.assertEqual(len(self.submitted), 3, "same signature must retry after failure")

    def test_submission_error_releases_reservation_immediately(self):
        one, two = self.overlapping()
        self.write_file("ABC-903.mkv")
        with patch.object(directory_watch, "_submit", side_effect=RuntimeError("offline")):
            directory_watch.scan_rule(one["id"], now=T0 + 1)
        directory_watch.scan_rule(two["id"], now=T0 + 2)
        self.assertEqual(len(self.submitted), 1, "failed submission must not reserve the file for 5 minutes")

    def test_deleted_rule_active_task_still_blocks_overlapping_rule(self):
        one, two = self.overlapping()
        self.write_file("ABC-904.mkv")
        directory_watch.scan_rule(one["id"], now=T0 + 1)
        directory_watch.delete_rule(one["id"])
        directory_watch.scan_rule(two["id"], now=T0 + 2)
        self.assertEqual(len(self.submitted), 1)

    def test_changed_successful_file_can_be_processed_by_other_rule(self):
        one, two = self.overlapping()
        path = self.write_file("ABC-905.mkv")
        directory_watch.scan_rule(one["id"], now=T0 + 1)
        self.finish(self.submitted[0])
        path.write_bytes(b"changed" * 12)
        directory_watch.scan_rule(two["id"], now=T0 + 2)
        self.assertEqual(len(self.submitted), 2, "cross-rule success claims must compare file signatures")

    def test_concurrent_watch_reservation_closes_check_submit_race(self):
        one, two = self.overlapping()
        self.write_file("ABC-906.mkv")
        entered, release = threading.Event(), threading.Event()
        submit = directory_watch._submit
        def delayed(rule, paths):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("test timed out")
            return submit(rule, paths)
        with patch.object(directory_watch, "_submit", side_effect=delayed):
            thread = threading.Thread(target=directory_watch.scan_rule, args=(one["id"],), kwargs={"now": T0 + 1})
            thread.start()
            try:
                self.assertTrue(entered.wait(5))
                directory_watch.scan_rule(two["id"], now=T0 + 1)
            finally:
                release.set()
                thread.join(10)
            self.assertFalse(thread.is_alive())
        self.assertEqual(len(self.submitted), 1)

    def test_schedule_and_watch_dedupe_both_directions_without_cron_success_ledger(self):
        watch = directory_watch.create_rule({"path": str(self.mount), "stable_seconds": 0})
        schedule = {**watch, "id": "schedule", "trigger": "schedule", "cron": "* * * * *"}
        directory_watch.write_rules([watch, schedule])
        self.write_file("ABC-907.mkv")
        directory_watch.scan_rule(watch["id"], now=T0)
        self.assertEqual(directory_watch.run_schedule_rule("schedule", "minute-1")["created"], 0)
        self.finish(self.submitted[0])
        self.assertEqual(directory_watch.run_schedule_rule("schedule", "minute-2")["created"], 1,
                         "cron scans must not inherit persistent watch success dedup")
        directory_watch.scan_rule(watch["id"], now=T0 + 1)
        self.assertEqual(len(self.submitted), 2)
        self.finish(self.submitted[1], "failed")
        self.assertEqual(directory_watch.run_schedule_rule("schedule", "minute-3")["created"], 1)

    def test_late_part_blocks_against_active_schedule_movie_identity(self):
        watch = directory_watch.create_rule({"path": str(self.mount), "stable_seconds": 0})
        schedule = {**watch, "id": "schedule", "trigger": "schedule", "cron": "* * * * *"}
        directory_watch.write_rules([watch, schedule])
        part_a = self.write_file("ABC-908-A.mkv")
        directory_watch.run_schedule_rule("schedule", "minute-1")
        part_a.unlink()  # the first part may already have moved out of the input folder
        self.write_file("ABC-908-B.mkv")
        directory_watch.scan_rule(watch["id"], now=T0)
        self.assertEqual(len(self.submitted), 1, "active A blocks B by normalized movie identity")

    def test_cron_full_scan_skips_problem_group_but_keeps_normal_movie(self):
        rule = directory_watch.create_rule({"path": str(self.mount), "trigger": "schedule", "cron": "* * * * *"})
        self.write_file("FC2-4953812-1.mp4")
        self.write_file("FC2PPV-4953812-01.mkv")
        self.write_file("ABC-909.mkv")
        outcome = directory_watch.run_schedule_rule(rule["id"], "minute-1")
        self.assertEqual(outcome["created"], 1)
        self.assertTrue(self.submitted[0]["input_directory"].endswith("ABC-909.mkv"))


    def test_multipart_group_waits_for_each_part_to_stabilize(self):
        watch = directory_watch.create_rule({"path": str(self.mount), "stable_seconds": 60})
        self.write_file("ABC-910-A.mkv")
        directory_watch.scan_rule(watch["id"], now=T0)
        self.write_file("ABC-910-B.mkv")
        directory_watch.scan_rule(watch["id"], now=T0 + 61)
        self.assertEqual(self.submitted, [], "stable A must wait for unstable B")
        directory_watch.scan_rule(watch["id"], now=T0 + 122)
        self.assertEqual(len(self.submitted), 1)
        self.assertEqual(len(self.submitted[0]["input_files"]), 2)

    def test_interrupted_schedule_recovers_persisted_tasks_and_history(self):
        rule = directory_watch.create_rule({"path": str(self.mount), "trigger": "schedule", "cron": "* * * * *"})
        self.write_file("ABC-911.mkv")
        with patch.object(directory_watch, "_record_schedule_result", side_effect=OSError("process stopped")):
            with self.assertRaises(OSError):
                directory_watch.run_schedule_rule(rule["id"], "minute-1")
        self.assertEqual(len(self.submitted), 1)
        directory_watch.recover_schedule_runs()
        history = directory_watch.schedule_history(rule["id"])
        self.assertEqual(history["runs"][0]["task_ids"], [self.submitted[0]["id"]])
        directory_watch.recover_schedule_runs()
        self.assertEqual(len(directory_watch.schedule_history(rule["id"])["runs"]), 1)
        self.assertEqual(directory_watch.run_schedule_rule(rule["id"], "minute-1")["state"], "duplicate")

    def test_per_rule_migrated_timezone_controls_cron_match(self):
        from datetime import datetime, timezone
        self.legacy(enabled=True, cron="0 2 * * *", last_run_key="")
        directory_watch.migrate_legacy_schedules()
        self.write_file("ABC-912.mkv")
        results = directory_watch.Scheduler().run_schedules(datetime(2026, 10, 22, 18, 0, tzinfo=timezone.utc))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["run_key"], "2026-10-23T02:00")
        self.assertEqual(len(self.submitted), 1)

    def test_old_api_history_read_delete_and_wrong_mode_isolation(self):
        from fastapi.testclient import TestClient
        from javsp_web import server
        directory_watch.stop_scheduler()
        self.legacy()
        directory_watch.migrate_legacy_schedules()
        with patch.dict(server.app.dependency_overrides,
                        {server.current_user: lambda: {"username": "tester", "role": "admin"}}):
            client = TestClient(server.app)
            self.addCleanup(client.close)
            rows = client.get("/api/auto-scrape-schedules").json()
            self.assertEqual(rows[0]["runs"][0]["task_ids"], ["historic-task"])
            self.assertEqual(rows[0]["last_run_key"], "2026-10-23T02:00")
            result = client.delete("/api/auto-scrape-schedules/legacy/runs/2026-10-23T02:00")
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(client.get("/api/auto-scrape-schedules").json()[0]["runs"], [])
            watch = directory_watch.create_rule({"path": str(self.mount)})
            result = client.delete(f"/api/auto-scrape-schedules/{watch['id']}")
            self.assertEqual(result.status_code, 404)
            self.assertIsNotNone(directory_watch.get_rule(watch["id"]))


class ServerWiringTests(unittest.TestCase):
    """server.py 只允许最小 include/lifecycle glue。"""

    def test_server_includes_router_and_stops_scheduler(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        old = storage.DATA_DIR
        patches = [patch.object(storage, name, Path(temp.name) / value.relative_to(old))
                   for name, value in list(vars(storage).items())
                   if isinstance(value, Path) and value.is_relative_to(old)]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        with patch("threading.Thread.start"):
            from fastapi.testclient import TestClient
            from javsp_web import server
        self.assertIn(directory_watch.stop_scheduler, server.app.router.on_shutdown,
                      "关停时必须停止目录监控调度线程")
        client = TestClient(server.app)
        self.addCleanup(client.close)
        response = client.get("/api/directory-watch/rules")
        self.assertEqual(response.status_code, 401, "路由已挂载但需要登录（404 表示没有挂载）")


if __name__ == "__main__":
    unittest.main()
