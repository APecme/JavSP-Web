"""Cookie管理器，统一管理CookieCloud和浏览器cookies"""
import logging
from typing import Dict, List, Optional

from javsp.chromium import get_browsers_cookies
from javsp.cookiecloud import get_cookiecloud_cookies

logger = logging.getLogger(__name__)


class CookieManager:
    """Cookie管理器，统一管理CookieCloud和浏览器cookies"""
    
    def __init__(self):
        self._browser_cookies_pool: Optional[List[Dict]] = None
        self._cookiecloud_cookies: Optional[Dict[str, Dict[str, str]]] = None
    
    def get_cookies_for_domain(self, domain: str, prefer_cookiecloud: bool = True) -> Optional[Dict[str, str]]:
        """
        获取指定域名的cookies
        
        Args:
            domain: 域名，例如: javdb.com
            prefer_cookiecloud: 是否优先使用CookieCloud的cookies
            
        Returns:
            cookies字典，如果找不到则返回None
        """
        # 优先尝试CookieCloud
        if prefer_cookiecloud:
            cookiecloud_cookies = self._get_cookiecloud_cookies()
            if cookiecloud_cookies:
                # 尝试精确匹配
                for cookie_domain, cookies in cookiecloud_cookies.items():
                    if domain in cookie_domain or cookie_domain in domain:
                        logger.debug(f'从CookieCloud获取到 {domain} 的cookies')
                        return cookies
        
        # 尝试浏览器cookies
        browser_cookies = self._get_browser_cookies()
        if browser_cookies:
            for item in browser_cookies:
                site = item.get('site', '')
                if domain in site or site in domain:
                    cookies = item.get('cookies', {})
                    if cookies:
                        logger.debug(f'从浏览器获取到 {domain} 的cookies (来源: {item.get("profile", "unknown")})')
                        return cookies
        
        return None
    
    def get_all_cookies_for_domain(self, domain: str) -> List[Dict[str, str]]:
        """
        获取指定域名的所有可用cookies（包括CookieCloud和浏览器）
        
        Args:
            domain: 域名，例如: javdb.com
            
        Returns:
            cookies字典列表
        """
        result = []
        
        # CookieCloud的cookies
        cookiecloud_cookies = self._get_cookiecloud_cookies()
        if cookiecloud_cookies:
            for cookie_domain, cookies in cookiecloud_cookies.items():
                if domain in cookie_domain or cookie_domain in domain:
                    result.append(cookies)
        
        # 浏览器cookies
        browser_cookies = self._get_browser_cookies()
        if browser_cookies:
            for item in browser_cookies:
                site = item.get('site', '')
                if domain in site or site in domain:
                    cookies = item.get('cookies', {})
                    if cookies:
                        result.append(cookies)
        
        return result
    
    def _get_cookiecloud_cookies(self) -> Dict[str, Dict[str, str]]:
        """获取CookieCloud的cookies（带缓存）"""
        if self._cookiecloud_cookies is None:
            self._cookiecloud_cookies = get_cookiecloud_cookies()
        return self._cookiecloud_cookies
    
    def _get_browser_cookies(self) -> List[Dict]:
        """获取浏览器cookies（带缓存）"""
        if self._browser_cookies_pool is None:
            try:
                self._browser_cookies_pool = get_browsers_cookies()
            except (PermissionError, OSError) as e:
                logger.warning(f"无法从浏览器Cookies文件获取登录凭据({e})，可能是安全软件在保护浏览器Cookies文件", exc_info=True)
                self._browser_cookies_pool = []
            except Exception as e:
                logger.warning(f"获取浏览器登录凭据时出错({e})", exc_info=True)
                self._browser_cookies_pool = []
        return self._browser_cookies_pool
    
    def clear_cache(self):
        """清除缓存，强制下次重新获取"""
        self._browser_cookies_pool = None
        self._cookiecloud_cookies = None


# 全局cookie管理器实例
_cookie_manager: Optional[CookieManager] = None


def get_cookie_manager() -> CookieManager:
    """获取全局cookie管理器实例"""
    global _cookie_manager
    if _cookie_manager is None:
        _cookie_manager = CookieManager()
    return _cookie_manager

