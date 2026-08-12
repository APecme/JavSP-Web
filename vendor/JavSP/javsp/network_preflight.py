"""Exit-IP checks for crawlers with known geographic access restrictions."""

from __future__ import annotations

import logging
from collections.abc import Iterable

import requests

from javsp.config import Cfg, CrawlerID
from javsp.progress import emit as progress_event


logger = logging.getLogger(__name__)

_GEO_ENDPOINTS = ("https://ipwho.is/", "https://ipapi.co/json/")
_JAPAN_REQUIRED: dict[CrawlerID, tuple[str, tuple[str, ...]]] = {
    CrawlerID.mgstage: ("MGStage", ("mgstage.com",)),
    CrawlerID.prestige: ("Prestige", ("prestige-av.com",)),
    CrawlerID.fc2: ("FC2", ("adult.contents.fc2.com",)),
    CrawlerID.fanza: ("FANZA", ("dmm.co.jp",)),
}


def _enabled_crawlers() -> set[CrawlerID]:
    selected: set[CrawlerID] = set()
    for _, crawlers in Cfg().crawler.selection.items():
        selected.update(crawlers)
    return selected


def _geo_ip(proxies: dict[str, str] | None) -> dict[str, str] | None:
    """Resolve one route's public IP and ISO country code without env proxies."""
    timeout = max(2, min(6, int(Cfg().network.timeout.total_seconds())))
    session = requests.Session()
    session.trust_env = False
    if proxies:
        session.proxies.update(proxies)
    for endpoint in _GEO_ENDPOINTS:
        try:
            response = session.get(endpoint, timeout=timeout, headers={"Accept": "application/json"})
            response.raise_for_status()
            data = response.json()
            country = str(data.get("country_code") or data.get("country") or "").upper()
            address = str(data.get("ip") or "").strip()
            if country:
                return {"ip": address, "country": country}
        except (requests.RequestException, ValueError, TypeError):
            continue
    return None


def _clash_mihomo_hint(domains: Iterable[str]) -> str:
    rules = "\n".join(f"  - DOMAIN-SUFFIX,{domain},JP" for domain in sorted(set(domains)))
    return (
        "Clash/Mihomo 覆写提示（先确保存在名为 JP 的日本策略组）：\n"
        "rules:\n"
        f"{rules}\n"
        "JavSP 的 network.proxy_server 必须指向运行环境可访问的 Clash/Mihomo HTTP 或 SOCKS5 端口；"
        "Docker 内请填写容器可访问的服务名或宿主机地址，不能默认使用 127.0.0.1。"
    )


def warn_restricted_crawler_network() -> None:
    """Warn, but never block, when selected crawlers need a Japanese exit IP."""
    enabled = _enabled_crawlers()
    restricted = {crawler: details for crawler, details in _JAPAN_REQUIRED.items() if crawler in enabled}
    if not restricted:
        return

    proxy_url = Cfg().network.proxy_server
    routes: list[tuple[str, dict[str, str] | None]] = [("直连", _geo_ip(None))]
    if proxy_url:
        proxy_value = str(proxy_url)
        routes.append(("配置代理", _geo_ip({"http": proxy_value, "https": proxy_value})))

    site_names = "、".join(details[0] for details in restricted.values())
    progress_event("network_preflight", status="running", sites=site_names, proxy_configured=bool(proxy_url))
    for route_name, result in routes:
        if result:
            logger.info("网络预检：%s出口 IP %s，地区 %s", route_name, result.get("ip") or "未知", result["country"])
        else:
            logger.warning("网络预检：无法查询%s出口地区；将继续执行刮削。", route_name)

    active_route_name, active_result = routes[-1]
    if active_result and active_result["country"] == "JP":
        progress_event("network_preflight", status="passed", sites=site_names, route=active_route_name)
        return

    route_text = (
        f"{active_route_name}出口为 {active_result['country']}"
        if active_result
        else f"无法查询{active_route_name}出口地区"
    )
    domains = [domain for _, crawler_domains in restricted.values() for domain in crawler_domains]
    warning = (
        f"网络预检警告：已启用的 {site_names} 存在日本地区访问限制，但{route_text}。"
        "这些爬虫可能返回 403、登录页或地区限制页面；刮削会继续，其他爬虫不受影响。"
    )
    logger.warning(warning)
    logger.warning(_clash_mihomo_hint(domains))
    progress_event("network_preflight", status="warning", sites=site_names, routes=route_text)
