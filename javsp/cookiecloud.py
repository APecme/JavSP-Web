"""CookieCloud客户端，用于从CookieCloud服务器获取cookies"""
import logging
import requests
from typing import Dict, List, Optional
from urllib.parse import urljoin

from javsp.config import Cfg

logger = logging.getLogger(__name__)


class CookieCloudClient:
    """CookieCloud客户端"""
    
    def __init__(self, server_url: str, uuid: str, password: str):
        """
        初始化CookieCloud客户端
        
        Args:
            server_url: CookieCloud服务器地址，例如: http://localhost:8088
            uuid: CookieCloud的UUID
            password: CookieCloud的密码
        """
        self.server_url = server_url.rstrip('/')
        self.uuid = uuid
        self.password = password
        self._cookies_cache: Optional[Dict[str, Dict[str, str]]] = None
    
    def get_cookies(self, domain: str = None) -> Dict[str, Dict[str, str]]:
        """
        从CookieCloud获取cookies
        
        Args:
            domain: 可选，指定域名过滤cookies
            
        Returns:
            字典，格式为 {domain: {cookie_name: cookie_value}}
        """
        if self._cookies_cache is not None:
            # 使用缓存
            if domain:
                return {k: v for k, v in self._cookies_cache.items() if domain in k}
            return self._cookies_cache
        
        try:
            # CookieCloud API: GET /get/{uuid}/{password}
            api_url = urljoin(self.server_url, f'/get/{self.uuid}/{self.password}')
            response = requests.get(api_url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # CookieCloud返回格式: {"cookie_data": [{"domain": "...", "cookies": {...}}]}
            if data.get('status') == 'success' and 'cookie_data' in data:
                cookies_dict = {}
                for item in data['cookie_data']:
                    item_domain = item.get('domain', '')
                    item_cookies = item.get('cookies', {})
                    if item_cookies:
                        cookies_dict[item_domain] = item_cookies
                
                self._cookies_cache = cookies_dict
                logger.info(f'成功从CookieCloud获取到 {len(cookies_dict)} 个域名的cookies')
                
                if domain:
                    return {k: v for k, v in cookies_dict.items() if domain in k}
                return cookies_dict
            else:
                error_msg = data.get('message', '未知错误')
                logger.warning(f'CookieCloud返回错误: {error_msg}')
                return {}
                
        except requests.exceptions.RequestException as e:
            logger.warning(f'无法连接到CookieCloud服务器 ({self.server_url}): {e}')
            return {}
        except Exception as e:
            logger.warning(f'从CookieCloud获取cookies时出错: {e}', exc_info=True)
            return {}
    
    def get_cookies_for_domain(self, domain: str) -> Dict[str, str]:
        """
        获取指定域名的cookies
        
        Args:
            domain: 域名，例如: javdb.com
            
        Returns:
            字典，格式为 {cookie_name: cookie_value}
        """
        all_cookies = self.get_cookies()
        
        # 精确匹配
        if domain in all_cookies:
            return all_cookies[domain]
        
        # 模糊匹配（包含该域名的）
        for cookie_domain, cookies in all_cookies.items():
            if domain in cookie_domain or cookie_domain in domain:
                return cookies
        
        return {}
    
    def clear_cache(self):
        """清除缓存，强制下次重新获取"""
        self._cookies_cache = None


def get_cookiecloud_cookies(domain: str = None) -> Dict[str, Dict[str, str]]:
    """
    从配置的CookieCloud服务器获取cookies
    
    Args:
        domain: 可选，指定域名过滤cookies
        
    Returns:
        字典，格式为 {domain: {cookie_name: cookie_value}}
    """
    cfg = Cfg()
    cookiecloud = cfg.network.cookiecloud
    
    if not cookiecloud.enabled:
        return {}
    
    if not cookiecloud.server_url or not cookiecloud.uuid or not cookiecloud.password:
        logger.debug('CookieCloud未完整配置（缺少server_url、uuid或password）')
        return {}
    
    try:
        client = CookieCloudClient(
            server_url=cookiecloud.server_url,
            uuid=cookiecloud.uuid,
            password=cookiecloud.password
        )
        return client.get_cookies(domain=domain)
    except Exception as e:
        logger.warning(f'初始化CookieCloud客户端失败: {e}', exc_info=True)
        return {}

