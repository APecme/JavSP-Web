import concurrent.futures
import io
import threading
import time
import unittest
from collections import OrderedDict
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from lxml import html
from PIL import Image

from javsp_web import hot, hot_covers as covers, hot_router
from javsp_web.auth import current_user
from javsp_web.hot_catalog import merge_items
from javsp_web.hot_network import NetworkError


def png(size=(120,160)):
    output=io.BytesIO();Image.new('RGB',size,'steelblue').save(output,'PNG');return output.getvalue()


class CoverTests(unittest.TestCase):
    def setUp(self):
        for name in ['_registry','_cache']:
            self.enterContext(patch.object(covers,name,OrderedDict()))
        for name in ['_failures','_inflight']:
            self.enterContext(patch.object(covers,name,{}))
        self.enterContext(patch.object(covers,'network_options',return_value={'proxy_url':None,'timeout_seconds':20}))

    def register(self):
        return covers.register('test','https://cdn.invalid/product.jpg','https://source.invalid/')

    def test_url_rejects_scripts_credentials_private_ports_and_placeholders(self):
        for value in ['javascript:alert(1)','data:image/png;base64,x','http://cdn.invalid/a.jpg','https://user:pass@cdn.invalid/a.jpg','https://cdn.invalid:123/a.jpg','https://cdn.invalid/loading_3.gif','https://cdn.invalid/website_building.png']:
            self.assertEqual(covers.safe_image_url(value,'https://source.invalid/'),'')
        self.assertEqual(covers.safe_image_url('//cdn.invalid/a.jpg','https://source.invalid/'),'https://cdn.invalid/a.jpg')

    def test_registry_is_stable_bounded_and_no_arbitrary_url_fetch(self):
        first=self.register();self.assertEqual(first,self.register())
        with patch.object(covers,'_download') as fetch:
            for token in ['../a','https://example.invalid', 'f'*64]:
                with self.assertRaises(KeyError):covers.get_cover(token)
            fetch.assert_not_called()
        with patch.object(covers,'MAX_REGISTERED',1):
            covers.register('other','https://cdn.invalid/other.jpg','https://source.invalid/')
            self.assertEqual(len(covers._registry),1)
            with self.assertRaises(KeyError):covers.get_cover(first.split('/')[-1][:-4])

    def test_extract_lazy_img_and_fd2_text_cover_and_fallback_merge(self):
        card=html.fromstring('<div><img src="/loading_3.gif" data-src="https://cdn.invalid/cover.webp"></div>')
        url=covers.image_from_card('freejavbt',card,'https://source.invalid/')
        token=url.split('/')[-1][:-4];self.assertEqual(covers._registry[token][0],'https://cdn.invalid/cover.webp')
        fd2=html.fromstring('<div><img src="https://cdn.invalid/actress.jpg"><div class="work-photos hidden">https://cdn.invalid/main.webp\nhttps://cdn.invalid/extra.webp</div></div>')
        cover=covers.image_from_card('fd2ppv',fd2,'https://fd2ppv.cc/')
        self.assertEqual(covers._registry[cover.split('/')[-1][:-4]][0],'https://cdn.invalid/main.webp')
        groups=[]
        for source,image in [('a',''),('b',cover)]:
            groups.append({'label':'Latest','items':[{'id':source,'source_id':source,'source_name':source,'identifier':'ABC-123','category':'censored','title':'Test','date':'2026-11-02','url':'https://source.invalid/','cover':image}]})
        self.assertEqual(merge_items(groups,'latest')[0]['cover'],cover)

    def test_source_parsers_attach_only_verified_card_images(self):
        faleno='<a href="/top/works/fns003/"><img src="https://cdn.invalid/fns3.jpg" alt="A work"><div class="main_text">2026/11/02</div></a>'
        item=hot.parse_feed('faleno','censored','latest',faleno,'https://faleno.jp/top/')[0]
        self.assertTrue(item['cover'].startswith('/api/hot/covers/'))
        dahlia='<div class="ranking-box"><img src="https://cdn.invalid/rank.jpg"><div class="ranking-title"><a href="/works/dldss001/">Ranked work</a></div></div>'
        self.assertTrue(hot.parse_feed('dahlia','censored','hot',dahlia,'https://dahlia-av.jp/')[0]['cover'])
        free='<div class="card"><img data-src="https://cdn.invalid/free.jpg"><div class="card-body"><a href="/ja/ABC-123"><h5 class="card-title">ABC-123</h5><p class="card-text">Work</p></a></div></div>'
        self.assertTrue(hot.parse_feed('freejavbt','censored','latest',free,'https://freejavbt.com/')[0]['cover'])

    def test_reencoding_bounds_dimensions_and_strips_metadata(self):
        result=covers._jpeg(png((1800,1200)))
        with Image.open(io.BytesIO(result)) as image:
            self.assertEqual(image.format,'JPEG');self.assertLessEqual(image.width,640);self.assertLessEqual(image.height,800)
        for data in [b'<svg xmlns="http://www.w3.org/2000/svg"></svg>',b'<html>blocked</html>',b'not an image']:
            with self.assertRaises(covers.CoverError):covers._jpeg(data)
        with patch.object(covers,'MAX_PIXELS',100):
            with self.assertRaises(covers.CoverError):covers._jpeg(png())

    def test_single_flight_cache_and_failure_cooldown(self):
        token=self.register().split('/')[-1][:-4]
        def download(*args):time.sleep(.03);return b'jpeg'
        with patch.object(covers,'_download',side_effect=download) as fetch:
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
                results=list(pool.map(lambda _:covers.get_cover(token),range(5)))
            self.assertEqual(results,[b'jpeg']*5);fetch.assert_called_once()
            self.assertEqual(covers.get_cover(token),b'jpeg');fetch.assert_called_once()
        covers._cache.clear()
        with patch.object(covers,'_download',side_effect=covers.CoverError('unavailable')) as fetch:
            for _ in range(2):
                with self.assertRaises(covers.CoverError):covers.get_cover(token)
            fetch.assert_called_once()

    def session(self,responses):
        session=MagicMock();session.__enter__.return_value=session;prepared=[]
        for status,headers,data in responses:
            response=MagicMock(status_code=status,headers=headers);response.__enter__.return_value=response
            raw=io.BytesIO(data);response.raw.read1.side_effect=lambda n,decode_content=True,raw=raw:raw.read(n)
            prepared.append(response)
        session.get.side_effect=prepared;return session

    def test_network_size_type_redirects_and_no_cookiecloud(self):
        session=self.session([(200,{'Content-Type':'image/png'},png())])
        with patch.object(covers.requests,'Session',return_value=session):
            self.assertTrue(covers._download('https://cdn.invalid/a.png','https://source.invalid/').startswith(b'\xff\xd8'))
        self.assertFalse(session.trust_env);self.assertFalse(session.get.call_args.kwargs['allow_redirects'])
        self.assertNotIn('cookies',session.get.call_args.kwargs);self.assertEqual(session.get.call_args.kwargs['headers']['Referer'],'https://source.invalid/')
        for entries in [[(200,{'Content-Type':'text/html'},b'blocked')],[(302,{'Location':'http://127.0.0.1/a'},b'')],[(200,{'Content-Type':'image/jpeg','Content-Length':str(covers.MAX_BYTES+1)},b'x')]]:
            with patch.object(covers.requests,'Session',return_value=self.session(entries)):
                with self.assertRaises(covers.CoverError):covers._download('https://cdn.invalid/a.png','https://source.invalid/')
        with patch.object(covers.requests,'Session',return_value=self.session([(200,{'Content-Type':'image/png'},b'x'*20)])),patch.object(covers,'MAX_BYTES',10):
            with self.assertRaises(covers.CoverError):covers._download('https://cdn.invalid/a.png','https://source.invalid/')

    def test_route_requires_login_and_provides_etag_and_private_jpeg(self):
        app=FastAPI();app.include_router(hot_router.router)
        path=self.register()
        with TestClient(app) as client:
            with patch.object(covers,'_download') as fetch:
                self.assertEqual(client.get(path).status_code,401);fetch.assert_not_called()
            app.dependency_overrides[current_user]=lambda:{'username':'viewer','role':'operator'}
            with patch.object(covers,'_download',return_value=covers._jpeg(png())) as fetch:
                first=client.get(path);self.assertEqual(first.status_code,200)
                self.assertEqual(first.headers['content-type'],'image/jpeg')
                self.assertTrue(first.headers['cache-control'].startswith('private'))
                self.assertEqual(first.headers['x-content-type-options'],'nosniff')
                second=client.get(path,headers={'If-None-Match':first.headers['etag']});self.assertEqual(second.status_code,304)
                fetch.assert_called_once()
            self.assertEqual(client.get('/api/hot/covers/'+'f'*64+'.jpg').status_code,404)
            self.assertEqual(client.get(path+'?url=http://127.0.0.1').status_code,200)
            with patch.object(covers,'get_cover',side_effect=covers.CoverError('暂不可用')):
                failed=client.get(path);self.assertEqual(failed.status_code,503);self.assertEqual(failed.headers['cache-control'],'no-store')


if __name__=='__main__':unittest.main()
