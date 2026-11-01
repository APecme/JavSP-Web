"""Anonymous, size/time-limited public HTML reads for fixed hot-page sources.

No environment proxies or challenge solvers. Optional domain-scoped
CookieCloud and explicitly confirmed age-session cookies; redirects are checked and DNS pinned.
"""
from __future__ import annotations

import ipaddress
import re
import socket
import time
from urllib.parse import urljoin, urlsplit, urlunsplit

import lxml.html
import requests
from requests.adapters import HTTPAdapter
from urllib3.exceptions import ReadTimeoutError, SSLError as Urllib3SSLError

MAX_BYTES = 1_500_000
MAX_SECONDS = 20
MAX_REDIRECTS = 4


class NetworkError(Exception):
    def __init__(self, state, message):
        self.state, self.message = state, message
        super().__init__(message)


def resolve_public(url):
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.port not in (None, 443)):
            raise NetworkError('unsafe_redirect', '仅允许公开 HTTPS 网页，已阻止不安全跳转')
        addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
        public = [row[4][0] for row in addresses if ipaddress.ip_address(row[4][0]).is_global
                  and not ipaddress.ip_address(row[4][0]).is_multicast]
        if not public:
            raise NetworkError('dns_blocked', '服务端 DNS 未返回可连接的公网地址，请检查 DNS/代理设置；不代表网站无法在浏览器打开')
        # Mixed DNS results can include unusable tunnel/fake IPv6. Connect only
        # the validated public address, prefer IPv4; never fall back to LAN IPs.
        public.sort(key=lambda address: ipaddress.ip_address(address).version)
        return parsed, public[0]
    except socket.gaierror:
        raise NetworkError('dns_error', '域名解析失败') from None
    except ValueError:
        raise NetworkError('unsafe_redirect', '网页地址无效') from None


class PinnedTLSAdapter(HTTPAdapter):
    def __init__(self, hostname):
        self.hostname = hostname
        super().__init__(max_retries=0)

    def init_poolmanager(self, connections, maxsize, block=False, **kwargs):
        super().init_poolmanager(connections, maxsize, block, assert_hostname=self.hostname,
                                 server_hostname=self.hostname, **kwargs)

    def proxy_manager_for(self, proxy, **kwargs):
        return super().proxy_manager_for(proxy, assert_hostname=self.hostname,
                                         server_hostname=self.hostname, **kwargs)


class PublicAdapter(HTTPAdapter):
    def __init__(self):
        super().__init__(max_retries=0)
        self.transports = {}

    def send(self, request, **kwargs):
        parsed, address = resolve_public(request.url)
        wire = request.copy()
        host = f'[{address}]' if ':' in address else address
        wire.url = urlunsplit(('https', host, parsed.path or '/', parsed.query, ''))
        wire.headers['Host'] = parsed.netloc
        key = (parsed.hostname, address)
        if key not in self.transports:
            self.transports[key] = PinnedTLSAdapter(parsed.hostname)
        response = self.transports[key].send(wire, **kwargs)
        response.url, response.request = request.url, request
        return response

    def close(self):
        for adapter in self.transports.values():
            adapter.close()
        super().close()


def read_html(url, *, cookie_domains=None, session=None, request_method="GET", form_data=None, allowed_hosts=None):
    """Return (HTTP code, final URL, decoded HTML); errors contain no remote text."""
    deadline = time.monotonic() + MAX_SECONDS
    from contextlib import nullcontext
    try:
        with (nullcontext(session) if session is not None else requests.Session()) as session:
            session.trust_env = False
            if not isinstance(session.get_adapter('https://'), PublicAdapter):
                session.mount('https://', PublicAdapter())
            # An HTTPS -> HTTP redirect must not fall back to requests' default
            # unguarded HTTP transport. The same adapter rejects non-HTTPS.
            if not isinstance(session.get_adapter('http://'), PublicAdapter):
                session.mount('http://', PublicAdapter())
            session.headers.update({'User-Agent': 'Mozilla/5.0 JavSP-Web/Hot-Connectivity',
                                    'Accept': 'text/html,application/xhtml+xml',
                                    'Accept-Encoding': 'gzip, deflate'})
            for hop in range(MAX_REDIRECTS + 1):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise NetworkError('timeout', '网页读取超时')
                if allowed_hosts is not None and urlsplit(url).hostname not in allowed_hosts:
                    raise NetworkError('unsafe_redirect', '原站确认跳转离开已适配域名，请在原站手动操作')
                # PublicAdapter validates/pins EVERY hop, even with a hostile Location.
                # Keep only scoped requests.CookieJar state for supplied sessions.
                # New anonymous sessions have no persistent cookies.
                host = (urlsplit(url).hostname or '').lower()
                for domain, values in sorted((cookie_domains or {}).items(), key=lambda pair: len(pair[0])):
                    clean = domain.lstrip('.').lower()
                    if host == clean or host.endswith('.' + clean):
                        for name, value in values.items():
                            if name not in session.cookies.get_dict(domain=host):
                                session.cookies.set(name, value, domain=host, path='/', secure=True)
                options = dict(stream=True, allow_redirects=False,
                               timeout=(min(5, remaining), min(3, remaining)))
                request = (session.post(url, data=form_data, **options) if request_method == 'POST'
                           else session.get(url, **options))
                with request as response:
                    code = response.status_code
                    if code in (301, 302, 303, 307, 308):
                        location = response.headers.get('Location')
                        if not location or hop == MAX_REDIRECTS:
                            raise NetworkError('redirect_error', '跳转无效或次数过多')
                        destination = urljoin(url, location)
                        if request_method == 'POST' and code in (307, 308):
                            if urlsplit(destination).netloc != urlsplit(url).netloc:
                                raise NetworkError('unsafe_redirect', '已阻止跨站重放确认表单')
                        elif request_method == 'POST':
                            request_method, form_data = 'GET', None
                        url = destination
                        continue
                    ctype = response.headers.get('Content-Type', '').lower()
                    if ctype and not any(t in ctype for t in ('text/html', 'application/xhtml+xml', 'text/plain')):
                        raise NetworkError('not_html', '响应不是 HTML 网页')
                    chunks, size = [], 0
                    response.raw.decode_content = True
                    # read1 returns available data rather than waiting for an entire
                    # chunk, so a slowly dripping response cannot hide the deadline.
                    while True:
                        if time.monotonic() > deadline:
                            raise NetworkError('timeout', '网页读取超时')
                        chunk = response.raw.read1(16384, decode_content=True)
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > MAX_BYTES:
                            raise NetworkError('too_large', '网页超过读取上限')
                        chunks.append(chunk)
                    data = b''.join(chunks)
                    charset = re.search(r'charset\s*=\s*["\']?([\w-]+)', ctype)
                    if not charset:
                        charset = re.search(br'charset=["\s\']*([\w-]+)', data[:12000])
                    encoding = charset.group(1) if charset else 'utf-8'
                    if isinstance(encoding, bytes):
                        encoding = encoding.decode('ascii', errors='ignore')
                    try:
                        text = data.decode(encoding, errors='replace')
                    except LookupError:
                        text = data.decode('utf-8', errors='replace')
                    return code, url, text
    except NetworkError:
        raise
    except (requests.exceptions.SSLError, Urllib3SSLError):
        raise NetworkError('tls_error', 'TLS 证书验证失败') from None
    except (requests.exceptions.Timeout, ReadTimeoutError, TimeoutError):
        raise NetworkError('timeout', '连接或读取超时') from None
    except Exception:
        # Do not echo exceptions: they can contain URLs, proxy auth or HTML.
        raise NetworkError('network_error', '连接失败或响应中断') from None


def classify(code, url, text):
    """HTTP 200 may be a gate or parking page, never imply list availability."""
    try:
        tree = lxml.html.fromstring(text[:MAX_BYTES])
        title = ' '.join(tree.xpath('//title/text()')).lower()
        for node in tree.xpath('//script|//style|//noscript'):
            node.drop_tree()
        visible = ' '.join(tree.text_content().split()).lower()
    except (ValueError, lxml.etree.ParserError):
        title, visible = '', ''
    if re.search(r'forsale\.min\.js|domain.{0,20}for sale', text, re.I):
        return 'parking', '疑似域名停放，不能作为影片数据源'
    if re.search(r'一時停止のお知らせ|臨時サーバーメンテナンス|temporarily unavailable.*maintenance', visible):
        return 'maintenance', '站点维护中'
    if re.search(r'access to this site is prohibited in the country|not available in your (country|region)|禁止了你的網路所在國家', visible):
        return 'region_blocked', '已响应，但当前地区受限'
    if (re.search(r'age[_-]?check|driver-verify', url, re.I)
            or re.search(r'年齢認証|age verification', title)
            or (len(visible) < 1600 and re.search(r'あなたは18歳以上|18歳以上の方のみ|18歳未満の方は', visible))):
        return 'age_gate', '已响应，需在原站确认年龄'
    if (re.search(r'just a moment|attention required|access denied', title)
            or (code == 403 and re.search(r'cloudflare|captcha', visible))):
        return 'challenge', '已响应，但被验证或访问策略拦截'
    if code in (401, 403):
        return 'denied', f'已响应，但拒绝访问（HTTP {code}）'
    if code == 429:
        return 'rate_limited', '站点限制请求频率（HTTP 429）'
    if not 200 <= code < 300:
        return 'http_error', f'HTTP {code}'
    if not visible:
        return 'js_shell', '仅有前端空壳或空响应，内容可用性未确认'
    if len(visible) < 80 and re.search(r'javu-site-index|id=["\'](?:app|root|__nuxt)', text):
        return 'js_shell', '已响应，内容依赖前端脚本'
    return 'ok', '网页可达；不代表影片列表已接入'
