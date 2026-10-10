import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from javsp_web import ai, ai_router, ai_tools, storage, tasks


def tool_call(name, arguments, identifier="call-1"):
    return {"role": "assistant", "content": "", "tool_calls": [
        {"id": identifier, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}
    ]}


class AITests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        old = storage.DATA_DIR
        for name, value in list(vars(storage).items()):
            if isinstance(value, Path) and value.is_relative_to(old):
                self.enterContext(patch.object(storage, name, self.root / value.relative_to(old)))
        with patch("threading.Thread.start"), patch.object(tasks, "recover_interrupted_tasks"):
            from javsp_web import server
        self.server = server
        self.user = {"username": "ai-admin", "role": "admin"}
        self.enterContext(patch.dict(server.app.dependency_overrides, {server.current_user: lambda: self.user}))
        self.enterContext(patch.object(ai_router, "_active", set()))
        self.enterContext(patch.object(ai_router, "_cancelled", set()))
        self.client = TestClient(server.app)
        self.addCleanup(self.client.close)
        self.config = {"enabled": True, "provider": "compatible", "base_url": "https://llm.test/v1",
                       "model": "test-model", "api_key": "private-ai-key", "timeout": 60}
        ai.save_settings(ai.AISettings(**self.config))

    def conversation(self, message="请创建刮削任务"):
        with patch.object(ai_router, "_start_analysis"):
            response = self.client.post("/api/ai/chat", json={"message": message})
        self.assertEqual(response.status_code, 202, response.text)
        return storage._read_json(ai_router._path(response.json()["id"]), None)

    def run_reply(self, conversation, replies):
        with patch.object(ai, "complete", side_effect=replies):
            ai_router._run(conversation, self.config)
        return self.client.get("/api/ai/conversations/" + conversation["id"]).json()

    def test_settings_key_preserved_cleared_and_not_returned(self):
        response = self.client.get("/api/ai/settings")
        self.assertTrue(response.json()["has_api_key"])
        self.assertNotIn("private-ai-key", response.text)
        update = dict(self.config, model="another", api_key="")
        response = self.client.put("/api/ai/settings", json=update)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ai.settings(True)["api_key"], "private-ai-key")
        update["clear_api_key"] = True
        self.client.put("/api/ai/settings", json=update)
        self.assertFalse(ai.settings()["has_api_key"])

    def test_admin_only_and_owner_checks(self):
        conversation = self.conversation()
        self.user["username"] = "other-admin"
        self.assertEqual(self.client.get("/api/ai/conversations/" + conversation["id"]).status_code, 404)
        self.user["role"] = "operator"
        for path in ("/api/ai/settings", "/api/ai/skills"):
            self.assertEqual(self.client.get(path).status_code, 403)
        self.assertEqual(self.client.post("/api/ai/chat", json={"message": "test"}).status_code, 403)

    def test_action_is_not_executed_until_confirmed_and_only_once(self):
        conversation = self.conversation()
        with patch.object(self.server, "start_task", return_value={"count": 1, "scan": True}) as create:
            result = self.run_reply(conversation, [tool_call("create_task", {"input_directory": "/video/example"}),
                                                   {"role": "assistant", "content": "请检查并确认创建任务。"}])
            create.assert_not_called()
            action = result["actions"][0]
            self.assertNotIn("snapshot", action)
            path = f"/api/ai/conversations/{conversation['id']}/actions/{action['id']}"
            self.assertEqual(self.client.post(path, json={"approve": True}).status_code, 200)
            self.assertEqual(create.call_count, 1)
            self.assertEqual(self.client.post(path, json={"approve": True}).status_code, 409)
            self.assertEqual(create.call_count, 1)

    def test_rejected_action_never_runs(self):
        conversation = self.conversation()
        result = self.run_reply(conversation, [tool_call("create_task", {"input_directory": "/video/example"}),
                                               {"role": "assistant", "content": "待确认"}])
        action = result["actions"][0]
        with patch.object(self.server, "start_task") as create:
            path = f"/api/ai/conversations/{conversation['id']}/actions/{action['id']}"
            self.assertEqual(self.client.post(path, json={"approve": False}).json()["actions"][0]["status"], "rejected")
            self.assertEqual(self.client.post(path, json={"approve": True}).status_code, 409)
            create.assert_not_called()

    def test_tool_read_results_redacted_before_sent_to_llm(self):
        conversation = self.conversation("读取预设")
        replies = [tool_call("get_preset", {"preset_id": "default"}), {"role": "assistant", "content": "完成"}]
        seen = []
        def complete(config, messages, tools, on_update=None):
            seen.append(copy.deepcopy(messages))
            return replies.pop(0)
        with patch.object(ai_tools, "execute", return_value={"api_key": "another-key", "nested": {"password": "secret"}}), patch.object(ai, "complete", side_effect=complete):
            ai_router._run(conversation, self.config)
        sent = json.dumps(seen, ensure_ascii=False)
        self.assertNotIn("another-key", sent)
        self.assertNotIn('"secret"', sent)
        self.assertIn("已隐藏", sent)

    def test_unknown_tool_is_not_dispatched(self):
        conversation = self.conversation()
        with patch.object(ai_tools, "execute") as execute:
            result = self.run_reply(conversation, [tool_call("shell", {"command": "echo unsafe"}), {"role": "assistant", "content": "无法执行"}])
            execute.assert_not_called()
        self.assertEqual(result["steps"][0]["status"], "failed")

    def test_restart_marks_running_action_unknown(self):
        conversation = self.conversation()
        conversation["actions"] = [{"id": "action", "status": "executing", "tool": "create_task", "arguments": {}}]
        ai_router._save(conversation)
        ai_router._active.clear()
        result = self.client.get("/api/ai/conversations/" + conversation["id"]).json()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["actions"][0]["status"], "unknown")

    def test_loop_is_bounded_and_errors_do_not_expose_key(self):
        conversation = self.conversation()
        with patch.object(ai_tools, "execute", return_value=[]):
            result = self.run_reply(conversation, [tool_call("list_presets", {})] * 6)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(result["steps"]), 6)
        conversation = self.conversation()
        result = self.run_reply(conversation, [ai.AIError("failed private-ai-key")])
        self.assertNotIn("private-ai-key", json.dumps(result))

    def test_skills_catalog_and_path_validation(self):
        self.assertEqual(len(self.client.get("/api/ai/skills").json()), 5)
        with self.assertRaises(ValueError):
            ai_tools.validate_arguments("read_skill", {"name": "../../config"})

    def test_conversation_management_persistence_and_ownership(self):
        first = self.conversation("第一段对话")
        self.run_reply(first, [{"role": "assistant", "content": "完成"}])
        second = self.conversation("第二段对话")
        self.run_reply(second, [{"role": "assistant", "content": "完成"}])
        items = self.client.get('/api/ai/conversations').json()
        self.assertEqual({item['title'] for item in items}, {'第一段对话', '第二段对话'})
        self.assertNotIn('turns', items[0])
        path = '/api/ai/conversations/' + first['id']
        self.assertEqual(self.client.patch(path, json={'title': '新标题'}).status_code, 200)
        self.assertEqual(self.client.get(path).json()['title'], '新标题')
        self.assertEqual(self.client.patch(path, json={'title': '   '}).status_code, 400)
        self.assertEqual(self.client.patch(path, json={'title': '长' * 81}).status_code, 422)
        self.user['username'] = 'another-admin'
        self.assertEqual(self.client.get('/api/ai/conversations').json(), [])
        self.assertEqual(self.client.patch(path, json={'title': '不能修改'}).status_code, 404)
        self.assertEqual(self.client.delete(path).status_code, 404)
        self.assertEqual(self.client.post(path + '/stop').status_code, 404)
        self.user['username'] = 'ai-admin'
        self.assertEqual(self.client.delete(path).status_code, 200)
        self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(len(self.client.get('/api/ai/conversations').json()), 1)

    def test_running_conversation_cannot_be_deleted_or_renamed(self):
        conversation = self.conversation()
        path = '/api/ai/conversations/' + conversation['id']
        self.assertEqual(self.client.delete(path).status_code, 409)
        self.assertEqual(self.client.patch(path, json={'title': '新标题'}).status_code, 409)

    def test_stream_progress_persisted_before_completion(self):
        conversation = self.conversation()
        def complete(config, messages, tools, on_update):
            on_update('', '模型提供的分析 private-ai-key')
            snapshot = self.client.get('/api/ai/conversations/' + conversation['id']).json()
            self.assertEqual(snapshot['status'], 'running')
            self.assertIn('模型提供的分析', snapshot['turns'][-1]['reasoning_content'])
            self.assertNotIn('private-ai-key', json.dumps(snapshot))
            on_update('部分回复 private-ai-', '')
            self.assertNotIn('private-ai-', conversation['turns'][-1]['content'])
            on_update('部分回复', '模型提供的分析')
            return {'role': 'assistant', 'content': '完整回复', 'reasoning_content': '模型提供的分析'}
        with patch.object(ai, 'complete', side_effect=complete):
            ai_router._run(conversation, self.config)
        result = self.client.get('/api/ai/conversations/' + conversation['id']).json()
        self.assertEqual(result['turns'][-1]['content'], '完整回复')
        self.assertEqual(result['turns'][-1]['status'], 'completed')

    def test_stop_preserves_partial_reply_and_prevents_tools(self):
        conversation = self.conversation()
        def complete(config, messages, tools, on_update):
            on_update('已收到的回复', '')
            self.client.post('/api/ai/conversations/' + conversation['id'] + '/stop')
            return tool_call('list_presets', {})
        with patch.object(ai, 'complete', side_effect=complete), patch.object(ai_tools, 'execute') as execute:
            ai_router._run(conversation, self.config)
            execute.assert_not_called()
        self.assertEqual(conversation['status'], 'stopped')
        self.assertEqual(conversation['turns'][-1]['content'], '已收到的回复')
        self.assertNotIn(conversation['id'], ai_router._active)

    def test_tool_history_retained_and_attached_to_reply(self):
        conversation = self.conversation()
        with patch.object(ai_tools, 'execute', return_value=[]):
            first = self.run_reply(conversation, [tool_call('list_presets', {}), {'role': 'assistant', 'content': '已查看'}])
        turn_id = first['turns'][-1]['id']
        self.assertEqual(first['steps'][0]['turn_id'], turn_id)
        with patch.object(ai_router, '_start_analysis'):
            response = self.client.post('/api/ai/chat', json={'conversation_id': conversation['id'], 'message': '继续'})
        second = response.json()
        self.assertEqual(second['steps'][0]['turn_id'], turn_id)
        saved = storage._read_json(ai_router._path(conversation['id']), None)
        self.run_reply(saved, [{'role': 'assistant', 'content': '下一次回复'}])
        self.assertEqual(len(saved['turns']), 4)

    def test_legacy_conversation_has_title_and_turn_ids(self):
        conversation = self.conversation('旧对话')
        conversation.pop('title')
        conversation['turns'][0].pop('id')
        ai_router._save(conversation)
        result = self.client.get('/api/ai/conversations/' + conversation['id']).json()
        self.assertEqual(result['title'], '旧对话')
        self.assertEqual(result['turns'][0]['id'], 'legacy-0')

    def test_skills_add_edit_delete_and_restore_persist(self):
        source = '---\nname: local-rule\ndescription: Test rule\n---\n\nKeep verified metadata.\n'
        self.assertEqual(self.client.put('/api/ai/skills', json={'source': source}).status_code, 200)
        self.assertEqual(self.client.get('/api/ai/skills/local-rule').json()['source'], source)
        self.assertEqual(len(self.client.get('/api/ai/skills').json()), 6)
        edited = source.replace('Keep verified metadata.', 'Preserve existing fields.')
        self.client.put('/api/ai/skills', json={'source': edited})
        self.assertIn('Preserve existing', ai_tools.execute('read_skill', {'name': 'local-rule'})['instructions'])
        self.assertEqual(self.client.delete('/api/ai/skills/local-rule').status_code, 200)
        self.assertEqual(self.client.get('/api/ai/skills/local-rule').status_code, 404)
        self.client.delete('/api/ai/skills/javsp-scrape')
        self.assertNotIn('javsp-scrape', [item['name'] for item in ai_tools.skill_catalog()])
        self.client.post('/api/ai/skills/restore-defaults')
        self.assertIn('javsp-scrape', [item['name'] for item in ai_tools.skill_catalog()])
        self.assertEqual(self.client.put('/api/ai/skills', json={'source': 'not a skill'}).status_code, 400)

    def test_metadata_preview_preserves_fields_and_tracks_changes(self):
        task = {'status': 'succeeded', 'progress': {'metadata': {'dvdid': 'TEST-001', 'title': 'old', 'actress': ['Actor']}}}
        with patch.object(self.server, 'task', return_value=task):
            proposal = ai_tools.prepare_action('update_metadata', {'task_id': 'task', 'title': 'new'})
            self.assertEqual(proposal['arguments']['actress'], ['Actor'])
            self.assertEqual(proposal['arguments']['dvdid'], 'TEST-001')
            task['progress']['metadata']['title'] = 'changed'
            updated = ai_tools.prepare_action('update_metadata', proposal['arguments'])
            self.assertNotEqual(proposal['snapshot'], updated['snapshot'])

    def test_changed_preset_requires_new_preview(self):
        preset = {"id": "default", "name": "默认", "form_values": {"crawler": {"required_keys": ["cover", "title"]}}, "task_concurrency": 1}
        with patch.object(ai_tools, "_preset", return_value=preset), patch.object(self.server, "_prepare_preset"):
            conversation = self.conversation()
            result = self.run_reply(conversation, [tool_call("change_preset", {"preset_id": "default", "changes": {"crawler": {"required_keys": ["title"]}}}), {"role": "assistant", "content": "待确认"}])
            action = result["actions"][0]
            preset["name"] = "其他修改"
            path = f"/api/ai/conversations/{conversation['id']}/actions/{action['id']}"
            with patch.object(self.server, "update_preset") as update:
                self.assertEqual(self.client.post(path, json={"approve": True}).status_code, 409)
                update.assert_not_called()

    def test_preset_patch_preserves_existing_keys(self):
        preset = {"name": "默认", "form_values": {"network": {"proxy_server": "http://localhost:7890"}, "translator": {"engine": {"api_key": "existing-secret"}}, "summarizer": {"move_files": True}}, "task_concurrency": 2}
        with patch.object(ai_tools, "_preset", return_value=preset), patch.object(self.server, "update_preset", return_value={"id": "default", "name": "默认"}) as update:
            ai_tools.execute("change_preset", {"preset_id": "default", "changes": {"summarizer": {"move_files": False}}}, confirmed=True)
        updated = update.call_args.args[1]
        self.assertEqual(updated.form["translator"]["engine"]["api_key"], "existing-secret")
        self.assertFalse(updated.form["summarizer"]["move_files"])
        self.assertEqual(updated.task_concurrency, 2)


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.config = dict(provider="compatible", base_url="https://llm.test/v1", model="demo", api_key="private-key", timeout=60)

    def response(self, data, status=200):
        response = Mock()
        response.status_code = status
        response.iter_content.return_value = [json.dumps(data).encode()]
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=False)
        return context

    def test_openai_tool_protocol_and_no_redirect(self):
        raw = {"choices": [{"message": tool_call("list_presets", {})}]}
        with patch.object(ai.requests, "post", return_value=self.response(raw)) as post:
            result = ai.complete(self.config, [{"role": "user", "content": "test"}], [{"type": "function"}])
        self.assertEqual(result["tool_calls"][0]["function"]["name"], "list_presets")
        self.assertEqual(post.call_args.args[0], "https://llm.test/v1/chat/completions")
        self.assertFalse(post.call_args.kwargs["allow_redirects"])
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer private-key")

    def test_anthropic_multiple_tool_results(self):
        messages = [{"role": "system", "content": "rules"}, {"role": "user", "content": "test"}, tool_call("list_presets", {}),
                    {"role": "tool", "tool_call_id": "call-1", "content": "[]"},
                    {"role": "tool", "tool_call_id": "call-2", "content": "[]"}]
        raw = {"content": [{"type": "text", "text": "完成"}]}
        with patch.object(ai.requests, "post", return_value=self.response(raw)) as post:
            result = ai.complete(self.config | {"provider": "anthropic"}, messages)
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["system"], "rules")
        self.assertEqual(len(payload["messages"][-1]["content"]), 2)
        self.assertEqual(result["content"], "完成")
        self.assertNotIn("Authorization", post.call_args.kwargs["headers"])

    def test_upstream_error_body_not_exposed(self):
        with patch.object(ai.requests, "post", return_value=self.response({"error": "private-key"}, 401)):
            with self.assertRaises(ai.AIError) as raised:
                ai.complete(self.config, [])
        self.assertNotIn("private-key", str(raised.exception))
        self.assertIn("401", str(raised.exception))

    def test_truncated_or_invalid_json_rejected(self):
        for data in ({"choices": []}, {"choices": [{"finish_reason": "length", "message": {"content": "half"}}]}, {"choices": [{"message": {"content": None}}]}):
            with self.subTest(data=data), patch.object(ai.requests, "post", return_value=self.response(data)):
                with self.assertRaises(ai.AIError):
                    ai.complete(self.config, [])

    def test_invalid_endpoint_rejected(self):
        for url in ("file:///etc/passwd", "https://user:pass@host/v1", "https://host/v1?api_key=secret"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                ai.AISettings(base_url=url)

    def stream_response(self, events):
        response = Mock(status_code=200, headers={'Content-Type': 'text/event-stream; charset=utf-8'})
        response.iter_lines.return_value = [b'data: ' + (json.dumps(event).encode() if isinstance(event, dict) else event) for event in events]
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=False)
        return context

    def test_stream_reasoning_text_and_split_tool_arguments(self):
        events = [
            {'choices': [{'delta': {'reasoning_content': '检查预设'}}]},
            {'choices': [{'delta': {'content': '正在查询'}}]},
            {'choices': [{'delta': {'tool_calls': [{'index': 0, 'id': 'call-1', 'function': {'name': 'get_preset', 'arguments': '{"preset_'}}]}}]},
            {'choices': [{'delta': {'tool_calls': [{'index': 0, 'function': {'arguments': 'id":"default"}'}}]}, 'finish_reason': 'tool_calls'}]},
            b'[DONE]',
        ]
        updates = []
        with patch.object(ai.requests, 'post', return_value=self.stream_response(events)) as post:
            result = ai.complete(self.config, [], on_update=lambda content, reasoning: updates.append((content, reasoning)))
        self.assertTrue(post.call_args.kwargs['json']['stream'])
        self.assertEqual(updates[0], ('', '检查预设'))
        self.assertEqual(result['content'], '正在查询')
        self.assertEqual(json.loads(result['tool_calls'][0]['function']['arguments']), {'preset_id': 'default'})

    def test_anthropic_stream_thinking_signature_and_tool(self):
        events = [
            {'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'thinking', 'thinking': ''}},
            {'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'thinking_delta', 'thinking': '模型分析'}},
            {'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'signature_delta', 'signature': 'signed'}},
            {'type': 'content_block_start', 'index': 1, 'content_block': {'type': 'text', 'text': ''}},
            {'type': 'content_block_delta', 'index': 1, 'delta': {'type': 'text_delta', 'text': '查询预设'}},
            {'type': 'content_block_start', 'index': 2, 'content_block': {'type': 'tool_use', 'id': 'call-1', 'name': 'list_presets', 'input': {}}},
            {'type': 'content_block_delta', 'index': 2, 'delta': {'type': 'input_json_delta', 'partial_json': '{}'}},
            {'type': 'message_stop'},
        ]
        with patch.object(ai.requests, 'post', return_value=self.stream_response(events)):
            result = ai.complete(self.config | {'provider': 'anthropic'}, [], on_update=Mock())
        self.assertEqual(result['reasoning_content'], '模型分析')
        self.assertEqual(result['content'], '查询预设')
        converted = ai._anthropic_messages([result])
        self.assertEqual(converted[0]['content'][0]['signature'], 'signed')
        self.assertEqual(result['tool_calls'][0]['function']['arguments'], '{}')

    def test_stream_interruption_and_truncation_fail(self):
        for events in ([{'choices': [{'delta': {'content': '一部分'}}]}],
                       [{'choices': [{'delta': {}, 'finish_reason': 'length'}]}],
                       [{'error': {'message': 'private-key'}}]):
            with self.subTest(events=events), patch.object(ai.requests, 'post', return_value=self.stream_response(events)):
                with self.assertRaises(ai.AIError) as raised:
                    ai.complete(self.config, [], on_update=Mock())
                self.assertNotIn('private-key', str(raised.exception))

    def test_stream_request_accepts_json_from_nonstreaming_provider(self):
        context = self.response({'choices': [{'message': {'content': '完整回复'}}]})
        context.__enter__.return_value.headers = {'Content-Type': 'application/json'}
        with patch.object(ai.requests, 'post', return_value=context):
            result = ai.complete(self.config, [], on_update=Mock())
        self.assertEqual(result['content'], '完整回复')


if __name__ == "__main__":
    unittest.main()
