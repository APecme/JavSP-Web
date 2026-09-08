"""Small, explicit guards for optional fields and changed detail pages."""
from javsp.web.exceptions import WebsiteError, SiteBlocked, MovieNotFoundError


def first(node, xpath, default=None):
    values = node.xpath(xpath)
    return values[0] if values else default


def class_xpath(name):
    return "contains(concat(' ', normalize-space(@class), ' '), ' " + name + " ')"


def detail_container(html, xpath, site, avid):
    node = first(html, xpath)
    if node is not None:
        return node
    text = html.text_content().lower()
    if any(token in text for token in ('just a moment', 'verify you are human', 'captcha', 'access denied')):
        raise SiteBlocked(f'{site}: 站点返回验证页，请检查代理出口及登录状态')
    if any(token in text for token in ('ページが見つかりません', '商品は見つかりません', '影片不存在', 'video not found')):
        raise MovieNotFoundError(site, avid)
    raise WebsiteError(f'{site}: 页面缺少影片信息区域，可能是页面结构变化或返回了异常页')
