"""Read-only TLS diagnostics; HTTP denial and certificate failures are distinct."""
from concurrent.futures import ThreadPoolExecutor
import os
import ssl
from urllib.parse import urlsplit

import requests


def check(url):
    host = urlsplit(url).hostname
    try:
        with requests.get(url, timeout=20, stream=True) as response:
            return f'{host}: TLS verified, HTTP {response.status_code}'
    except requests.exceptions.SSLError:
        return f'{host}: TLS certificate validation failed'
    except requests.exceptions.RequestException as error:
        return f'{host}: {type(error).__name__}'


if __name__ == '__main__':
    bundle = os.environ.get('REQUESTS_CA_BUNDLE') or requests.certs.where()
    context = ssl.create_default_context(cafile=bundle)
    assert context.cert_store_stats()['x509_ca'] > 0, 'No trusted CA certificates'
    print('CA bundle:', bundle, '| trusted CAs:', context.cert_store_stats()['x509_ca'])
    urls = ['https://javdb368.com/search?q=BBAN-601', 'https://www.seedmm.help/BBAN-601',
            'https://javdb.com/search?q=BBAN-601', 'https://www.javbus.com/BBAN-601']
    with ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(check, urls):
            print(result)
