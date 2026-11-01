"""Effective read-only network configuration for hot detection and age flows."""
from __future__ import annotations

import math
import re
from datetime import timedelta
from urllib.parse import urlsplit

from .config_validation import load_base_config
from .storage import get_preset


def network_options():
    network = dict(load_base_config().get('network') or {})
    preset = get_preset('default')
    if preset:
        if preset.get('mode') == 'yaml':
            import yaml
            try:
                data = yaml.safe_load(preset.get('content') or '')
                if isinstance(data, dict) and isinstance(data.get('network'), dict):
                    network.update(data['network'])
            except yaml.YAMLError:
                pass
        elif isinstance(preset.get('form'), dict):
            network.update(preset['form'].get('network') or {})
    raw_proxy = str(network.get('proxy_server') or '').strip()
    if raw_proxy.lower() in ('none', 'null', '~'):
        raw_proxy = ''
    if raw_proxy:
        try:
            parsed = urlsplit(raw_proxy)
            if parsed.scheme not in ('http', 'https', 'socks5', 'socks5h') or not parsed.hostname or parsed.fragment:
                raise ValueError()
            _ = parsed.port
        except ValueError:
            # Never echo a potentially credential-bearing proxy URL.
            from .hot_network import NetworkError
            raise NetworkError('proxy_error', '默认预设的代理地址无效，请检查刮削预设 → 网络') from None
    raw_timeout = network.get('timeout')
    seconds = raw_timeout.total_seconds() if isinstance(raw_timeout, timedelta) else None
    if seconds is None:
        match = re.fullmatch(r'PT(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?', str(raw_timeout or ''), re.I)
        if match:
            h, m, s = (float(x or 0) for x in match.groups())
            seconds = h * 3600 + m * 60 + s
    seconds = seconds if isinstance(seconds, (float, int)) and math.isfinite(seconds) and seconds > 0 else 20
    return {'proxy_url': raw_proxy or None, 'timeout_seconds': max(15, min(60, float(seconds)))}


def public_network():
    try:
        options = network_options()
        return {'mode': 'proxy' if options['proxy_url'] else 'direct',
                'label': '默认预设代理' if options['proxy_url'] else '服务端直连',
                'timeout_seconds': options['timeout_seconds'],
                'message': '浏览器与服务端可能使用不同网络、登录态与脚本环境；本检测不执行网页脚本。'}
    except Exception:
        return {'mode': 'error', 'label': '网络配置异常', 'timeout_seconds': None,
                'message': '请检查默认刮削预设中的网络配置'}
