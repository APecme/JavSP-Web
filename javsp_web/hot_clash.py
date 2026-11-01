"""Admin-authorized Clash/Mihomo diagnostic, reversible switching and YAML export.

No credentials/config YAML are persisted. Only explicit user confirmation can
switch the live GLOBAL selector/mode. A failed restore is prominently reported.
"""
from __future__ import annotations

import copy
import ipaddress
import json
import re
import socket
import threading
import time
import uuid
from urllib.parse import urlsplit, urlunsplit

import requests
import yaml
from requests.adapters import HTTPAdapter

from .hot_sources import BY_ID
from .hot_network import NetworkError, classify, read_html

MAX_NODES = 100
MAX_JSON = 1_000_000
_LOCK = threading.RLock()
_job = {}
_cancel = threading.Event()
COOLDOWN = 30
MAX_DIAGNOSTIC_SECONDS = 900


class ClashError(Exception):
    pass


def endpoint(value, *, proxy=False):
    """Only user-designated controller/proxy may reach LAN; never redirects."""
    try:
        p = urlsplit(value.strip())
        if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password or p.query:
            raise ValueError()
        port = p.port or (443 if p.scheme == 'https' else 80)
        rows = socket.getaddrinfo(p.hostname, port, type=socket.SOCK_STREAM)
        ips = [ipaddress.ip_address(r[4][0]) for r in rows]
        if not ips or any(ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved for ip in ips):
            raise ValueError()
        if p.scheme == 'http' and any(ip.is_global for ip in ips):
            raise ClashError('公网控制器/代理请使用 HTTPS，避免明文传输密钥')
        if proxy and (p.scheme != 'http' or any(ip.is_global for ip in ips)):
            raise ClashError('诊断代理请使用本机/内网 HTTP 或 mixed 端口，暂不支持公网或 HTTPS 代理')
        if p.path not in ('', '/', '/ui', '/ui/'):
            raise ClashError('请填写控制器/API 地址或代理地址，不是面板页面/订阅地址')
        if proxy:
            # Pin the explicitly authorized LAN proxy as well; no DNS rebinding.
            ip = str(ips[0]); host = '[' + ip + ']' if ':' in ip else ip
            return urlunsplit(('http', host + ':' + str(port), '', '', ''))
        return urlunsplit((p.scheme, p.netloc, '', '', ''))
    except (ValueError, OSError):
        raise ClashError('地址无效或指向禁止访问的链路本地/保留地址') from None


class _ControlTLS(HTTPAdapter):
    def __init__(self, hostname):
        self.hostname = hostname
        super().__init__(max_retries=0)

    def init_poolmanager(self, connections, maxsize, block=False, **kwargs):
        super().init_poolmanager(connections, maxsize, block, assert_hostname=self.hostname,
                                 server_hostname=self.hostname, **kwargs)


class Controller:
    def __init__(self, url, secret):
        self.url = endpoint(url)
        self.secret = secret

    def request(self, method, path, body=None):
        # Resolve and pin each request, allow only this explicit controller origin.
        endpoint(self.url)
        p = urlsplit(self.url)
        port = p.port or (443 if p.scheme == 'https' else 80)
        rows = socket.getaddrinfo(p.hostname, port, type=socket.SOCK_STREAM)
        if (p.scheme == 'http' and any(ipaddress.ip_address(r[4][0]).is_global for r in rows)) or any(ipaddress.ip_address(r[4][0]).is_link_local or ipaddress.ip_address(r[4][0]).is_reserved
               or ipaddress.ip_address(r[4][0]).is_multicast or ipaddress.ip_address(r[4][0]).is_unspecified for r in rows):
            raise ClashError('控制器DNS发生变化，已阻止访问')
        address = rows[0][4][0]
        host = f'[{address}]' if ':' in address else address
        wire = urlunsplit((p.scheme, host + ':' + str(port), path, '', ''))
        try:
            with requests.Session() as session:
                session.trust_env = False
                if p.scheme == 'https':
                    session.mount('https://', _ControlTLS(p.hostname))
                headers = {'Host': p.netloc}
                if self.secret:
                    headers['Authorization'] = 'Bearer ' + self.secret
                with session.request(method, wire, headers=headers, json=body, timeout=(4, 6),
                                     allow_redirects=False, stream=True) as response:
                    if response.status_code >= 300:
                        raise ClashError(f'控制器返回 HTTP {response.status_code}，请检查地址、Secret 与权限')
                    data = bytearray()
                    deadline = time.monotonic() + 10
                    while True:
                        if time.monotonic() > deadline:
                            raise ClashError('控制器响应超时')
                        chunk = response.raw.read1(16384, decode_content=True)
                        if not chunk: break
                        data.extend(chunk)
                        if len(data) > MAX_JSON:
                            raise ClashError('控制器响应超过上限')
                    return json.loads(data) if data else {}
        except ClashError:
            raise
        except Exception:
            raise ClashError('无法连接控制器或响应无效；请检查服务端网络与 API 地址') from None


def _leaf_nodes(proxies):
    return [name for name, node in proxies.items() if isinstance(name, str) and isinstance(node, dict)
            and node.get('type') not in ('Selector', 'URLTest', 'Fallback', 'LoadBalance', 'Relay',
                                         'Direct', 'Reject', 'RejectDrop', 'Pass', 'Compatible')
            and not node.get('all') and name not in ('GLOBAL', 'DIRECT', 'REJECT', 'PASS')][:MAX_NODES]


def status():
    with _LOCK:
        return copy.deepcopy({k: v for k, v in _job.items() if k not in ('started_mono', 'controller', 'proxy')}) or {
            'running': False, 'results': [], 'completed': 0, 'total': 0, 'restore_state': 'not_needed'}


def start(controller_url, secret, proxy_url, source_ids, confirm):
    if not confirm:
        raise ClashError('必须确认临时切换 GLOBAL 会影响该 Clash 的全部流量')
    controller = Controller(controller_url, secret)
    proxy = endpoint(proxy_url, proxy=True)
    if not source_ids or len(source_ids) > 3 or any(id not in BY_ID for id in source_ids):
        raise ClashError('请选择 1–3 个固定站点测试，不能传入任意网址')
    global _cancel
    with _LOCK:
        if _job.get('running'):
            raise ClashError('已有诊断运行中，请等待或取消')
        if time.monotonic() - _job.get('started_mono', -COOLDOWN) < COOLDOWN:
            raise ClashError('请稍后再开始诊断，避免反复切换节点')
        _cancel = threading.Event()
        _job.clear()
        _job.update(id=uuid.uuid4().hex, running=True, completed=0, total=0, results=[],
                    message='连接控制器并读取节点…', restore_state='not_needed',
                    source_ids=list(source_ids), started_mono=time.monotonic())
        try:
            threading.Thread(target=_run, args=(controller, proxy, source_ids, _cancel),
                             name='hot-clash-diagnostic', daemon=True).start()
        except Exception:
            _job.update(running=False, message='无法启动诊断任务', restore_state='not_needed')
            raise ClashError('无法启动诊断任务，请重试') from None
        return status()


def cancel():
    with _LOCK:
        _cancel.set()
        if _job.get('running'):
            _job['message'] = '正在取消，等待当前请求结束后恢复 Clash 原状态…'
        return status()


def exit_info(proxy):
    """HTTPS IP service receives diagnostic traffic; explicitly disclosed in UI."""
    try:
        with requests.Session() as session:
            session.trust_env = False
            with session.get('https://ipapi.co/json/', proxies={'http': proxy, 'https': proxy},
                             timeout=(5, 8), stream=True, allow_redirects=False) as response:
                if response.status_code != 200:
                    raise ClashError('出口查询服务拒绝请求或限流')
                data = bytearray()
                deadline = time.monotonic() + 10
                while True:
                    if time.monotonic() > deadline: raise ClashError('出口查询超时')
                    chunk = response.raw.read1(4096, decode_content=True)
                    if not chunk: break
                    data.extend(chunk)
                    if len(data) > 32000:
                        raise ClashError('出口查询响应过大')
                obj = json.loads(data)
                address = ipaddress.ip_address(obj.get('ip', ''))
                if not address.is_global: raise ClashError('出口查询未返回公网 IP')
                ip = str(address)
                return {'ip': ip, 'country': str(obj.get('country_name') or '')[:80],
                        'country_code': str(obj.get('country_code') or '')[:8], 'error': ''}
    except Exception:
        return {'ip': '', 'country': '', 'country_code': '', 'error': '出口查询失败或被限流，不推断出口地区'}


def _run(controller, proxy, source_ids, stop):
    original_mode = original_global = None
    changed = False
    deadline = time.monotonic() + MAX_DIAGNOSTIC_SECONDS
    try:
        config = controller.request('GET', '/configs')
        proxies = controller.request('GET', '/proxies').get('proxies', {})
        original_mode = config.get('mode')
        global_node = proxies.get('GLOBAL', {})
        original_global = global_node.get('now')
        if original_mode not in ('rule', 'global', 'direct') or not original_global or global_node.get('type') != 'Selector':
            raise ClashError('控制器未提供可恢复的 mode/GLOBAL 选择器；不进行切换')
        nodes = [name for name in _leaf_nodes(proxies) if name in global_node.get('all', [])]
        if not nodes:
            raise ClashError('没有可由 GLOBAL 直接选择的叶子节点；不测试自动策略组')
        with _LOCK:
            _job.update(total=len(nodes), message='逐节点查询出口并检测选定站点', restore_state='pending')
        changed = True  # Even a timeout can occur AFTER a mutation was applied.
        controller.request('PATCH', '/configs', {'mode': 'global'})
        for name in nodes:
            if time.monotonic() > deadline: stop.set()
            if stop.is_set():
                break
            row = {'name': name, 'exit': {}, 'sites': [], 'error': ''}
            try:
                controller.request('PUT', '/proxies/GLOBAL', {'name': name})
                current = controller.request('GET', '/proxies/GLOBAL')
                if current.get('now') != name:
                    raise ClashError('节点切换校验失败')
                row['exit'] = exit_info(proxy)
                for id in source_ids:
                    if time.monotonic() > deadline: stop.set()
                    if stop.is_set():
                        break
                    try:
                        code, url, page = read_html(BY_ID[id]['url'], proxy_url=proxy)
                        state, message = classify(code, url, page)
                        row['sites'].append({'source_id': id, 'state': state, 'message': message,
                                             'http_status': code})
                    except NetworkError as error:
                        row['sites'].append({'source_id': id, 'state': error.state,
                                             'message': error.message, 'http_status': None})
            except Exception:
                row['error'] = '节点切换或测试失败，不视为可用节点'
            with _LOCK:
                _job['results'].append(row)
                _job['completed'] += 1
    except ClashError as error:
        with _LOCK:
            _job['message'] = str(error)
    except Exception:
        with _LOCK:
            _job['message'] = '诊断失败；请检查控制器与代理设置'
    finally:
        errors = []
        if changed:
            # Attempt both restores even if one fails; independently verify them.
            for method, path, payload in [('PUT', '/proxies/GLOBAL', {'name': original_global}),
                                          ('PATCH', '/configs', {'mode': original_mode})]:
                try:
                    controller.request(method, path, payload)
                except Exception:
                    errors.append(path)
            try:
                if controller.request('GET', '/configs').get('mode') != original_mode:
                    errors.append('mode')
                if controller.request('GET', '/proxies/GLOBAL').get('now') != original_global:
                    errors.append('GLOBAL')
            except Exception:
                errors.append('verify')
        with _LOCK:
            _job['restore_state'] = 'failed' if errors else ('restored' if changed else 'not_needed')
            _job['running'] = False
            if errors:
                _job['message'] = '警告：未能确认恢复 Clash 原状态，请立即在面板手动检查模式和 GLOBAL 节点'
            elif changed:
                _job['message'] = '已取消，原模式与 GLOBAL 节点已恢复' if stop.is_set() else '诊断完成，原模式与 GLOBAL 节点已恢复'


def _load_yaml(text):
    if len(text.encode()) > MAX_JSON:
        raise ClashError('原 YAML 超过 1 MB 上限')
    try:
        # Reject aliases and excessive parser events before constructing objects.
        depth = 0
        for count, event in enumerate(yaml.parse(text)):
            if isinstance(event, (yaml.MappingStartEvent, yaml.SequenceStartEvent)): depth += 1
            if isinstance(event, (yaml.MappingEndEvent, yaml.SequenceEndEvent)): depth -= 1
            if depth > 40: raise ClashError('YAML 嵌套过深')
            if count > 50000 or isinstance(event, yaml.AliasEvent):
                raise ClashError('YAML 结构过大或包含别名，请先展开后上传')
        doc = yaml.safe_load(text)
    except ClashError:
        raise
    except Exception:
        raise ClashError('YAML 无法安全解析') from None
    if not isinstance(doc, dict) or not isinstance(doc.get('proxy-groups', []), list) or not isinstance(doc.get('rules', []), list):
        raise ClashError('请上传完整 Clash 配置 YAML，不是节点列表或订阅链接')
    if not isinstance(doc.get('proxies', []), list) or not isinstance(doc.get('proxy-providers', {}), dict):
        raise ClashError('原配置 proxies/proxy-providers 格式无效')
    for row in doc.get('proxies', []) + doc.get('proxy-groups', []):
        if not isinstance(row, dict) or not isinstance(row.get('name'), str) or not row['name']:
            raise ClashError('原配置节点/策略组缺少有效名称')
    if any(not isinstance(k, str) or not isinstance(v, dict) for k, v in doc.get('proxy-providers', {}).items()):
        raise ClashError('原配置 provider 格式无效')
    if any(not isinstance(rule, str) for rule in doc.get('rules', [])):
        raise ClashError('原配置规则必须为字符串列表')
    return doc


def export_yaml(original_yaml, selected_nodes, job_id):
    doc = _load_yaml(original_yaml)
    with _LOCK:
        if _job.get('running') or _job.get('id') != job_id or _job.get('restore_state') != 'restored':
            raise ClashError('请先完成诊断并确认恢复成功，再导出该次结果')
        results = copy.deepcopy(_job.get('results', []))
    good = {r['name'] for r in results if not r.get('error') and r.get('exit', {}).get('ip')
            and any(s.get('state') == 'ok' for s in r.get('sites', []))}
    if not selected_nodes or len(selected_nodes) > MAX_NODES or not set(selected_nodes) <= good:
        raise ClashError('只能选择本次取得出口 IP 且至少一个目标网页可达的节点')
    names = [str(p.get('name')) for p in doc.get('proxies', []) if isinstance(p, dict)]
    providers = list(doc.get('proxy-providers', {}))
    if any(name not in names for name in selected_nodes) and not providers:
        raise ClashError('选中节点不在原 YAML 内，且没有 proxy-providers，无法生成完整替换配置')
    existing = set(names + [g.get('name') for g in doc.get('proxy-groups', []) if isinstance(g, dict)])
    rules = []
    available = sorted({s['source_id'] for r in results if r['name'] in selected_nodes
                        for s in r.get('sites', []) if s.get('state') == 'ok'})
    for id in available:
        group_name = 'JAVSP-HOT-' + id
        while group_name in existing:
            group_name += '-1'
        existing.add(group_name)
        # Every node offered for this domain actually passed THIS domain, not
        # merely a different target. A union of unrelated successes is unsafe.
        passed = [r['name'] for r in results if r['name'] in selected_nodes and
                  any(s['source_id'] == id and s.get('state') == 'ok' for s in r.get('sites', []))]
        group = {'name': group_name, 'type': 'select', 'proxies': [n for n in passed if n in names]}
        if providers and any(n not in names for n in passed):
            group['use'] = providers
            group['filter'] = '^(' + '|'.join(re.sub(r'([.\\+*?\[\]\^$(){}|])', r'\\\1', n) for n in passed) + ')$'
        doc.setdefault('proxy-groups', []).append(group)
        host = urlsplit(BY_ID[id]['url']).hostname
        rules.append(f'DOMAIN-SUFFIX,{host},{group_name}')
    doc['rules'] = rules + doc.get('rules', [])
    doc['mode'] = 'rule'
    # Preserve nodes/providers/DNS/controller/etc; output contains original secrets.
    # Caller returns as explicit no-store download, never logs or persists it.
    try:
        rendered = yaml.safe_dump(doc, allow_unicode=True, sort_keys=False)
        _load_yaml(rendered)
        return rendered
    except ClashError:
        raise
    except Exception:
        raise ClashError('配置无法导出，请检查原 YAML 的字段类型') from None
