"""Fall back only from a configured mirror to its known canonical site."""
import logging
from urllib.parse import urlsplit, urlunsplit

from requests.exceptions import SSLError
from javsp.progress import emit


def get_with_mirror_fallback(get, url, mirror, canonical, **kwargs):
    try:
        return get(url, **kwargs)
    except SSLError:
        source, configured, target = urlsplit(url), urlsplit(mirror), urlsplit(canonical)
        if source.netloc != configured.netloc or source.netloc == target.netloc or target.scheme != 'https':
            raise
        # Rebuild the request so the regular cookie selector uses the new host.
        fallback = urlunsplit((target.scheme, target.netloc, source.path, source.query, ''))
        message = f'{configured.hostname} 证书验证失败，改用官网 {target.hostname}'
        logging.getLogger(__name__).warning(message)
        emit('notice', message=message)
        return get(fallback, **kwargs)
