"""Real HTTP/cookie pipeline with fake TLS transport; no external declarations."""
import copy
import socket
import tempfile
import threading
import unittest
from http.client import HTTPMessage
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient

from javsp_web import hot, hot_age as age, hot_network as network, hot_router, hot_settings
from javsp_web.auth import current_user


class Raw:
    def __init__(self, body, cookies=()):
        self.body=body; self.sent=False
        message=HTTPMessage()
        for cookie in cookies:message.add_header('Set-Cookie',cookie)
        self._original_response=SimpleNamespace(msg=message)
    def read1(self,n,decode_content=True):
        if self.sent:return b''
        self.sent=True;return self.body
    def close(self):pass
    def release_conn(self):pass


def response(body,status=200,location=None,cookies=()):
    r=requests.Response();r.status_code=status
    r.headers={'Content-Type':'text/html; charset=utf-8'}
    if location:r.headers['Location']=location
    r.raw=Raw(body.encode(),cookies);return r


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(age,'_sessions',{}));self.enterContext(patch.object(age,'_jobs',{}))
        self.enterContext(patch('javsp_web.storage.get_cookiecloud_settings',return_value={'enabled':False}))
        self.enterContext(patch.object(age,'network_options',return_value={'proxy_url':None,'timeout_seconds':20}))
        def resolved(url):return network.urlsplit(url),'8.8.8.8'
        self.enterContext(patch.object(network,'resolve_public',side_effect=resolved))
        self.enterContext(patch.object(network,'public_candidates',return_value=['8.8.8.8']))

    def test_giga_real_redirect_cookie_capture_and_original_source_verification(self):
        age._jobs['giga']={'running':True}
        seen=[]
        def send(adapter,request,**kwargs):
            seen.append((request.url,request.headers.get('Cookie','')))
            path=network.urlsplit(request.url).path
            if path=='/cookie_set.php':
                return response('',302,'/top.php',['adult=yes; Domain=.giga-web.jp; Path=/; Secure; HttpOnly'])
            if 'adult=yes' not in request.headers.get('Cookie',''):
                return response('<p>あなたは18歳以上ですか？</p><a href="/cookie_set.php">はい</a>')
            return response('<title>GIGA</title><p>Current releases catalogue</p>')
        callback=MagicMock()
        with patch.object(network.PinnedTLSAdapter,'send',autospec=True,side_effect=send):age._run('giga',callback)
        result=callback.call_args.args[1]
        self.assertEqual(result['state'],'ok')
        self.assertTrue(age.status('giga')['success'])
        self.assertTrue(age.cookies('giga').get('adult'))
        self.assertEqual(len(seen),4)
        self.assertIn('adult=yes',seen[-1][1])
        self.assertEqual(age.status('giga')['phase'],'finished')

    def test_javbus_post_has_referer_origin_and_cookie_recheck(self):
        age._jobs['javbus']={'running':True};posts=[]
        def send(adapter,request,**kwargs):
            if request.method=='POST':
                posts.append(request)
                return response('',302,'/',['adult=1; Path=/; Secure'])
            if 'adult=1' in request.headers.get('Cookie',''):
                return response('<p>Current works catalogue</p>')
            if network.urlsplit(request.url).path=='/':
                return response('',302,'/doc/driver-verify?referer=https%3A%2F%2Fwww.javbus.com%2F')
            return response('<title>Age Verification JavBus</title><form id="form1" method="post"><input type="checkbox">我已經成年<input type="submit" name="Submit" value="確認"></form>')
        callback=MagicMock()
        with patch.object(network.PinnedTLSAdapter,'send',autospec=True,side_effect=send):age._run('javbus',callback)
        self.assertEqual(len(posts),1)
        self.assertIn('Submit=',posts[0].body)
        self.assertEqual(posts[0].headers['Origin'],'https://www.javbus.com')
        self.assertIn('driver-verify',posts[0].headers['Referer'])
        self.assertEqual(callback.call_args.args[1]['state'],'ok')

    def test_permanent_av_landing_verifies_entry_not_root(self):
        age._jobs['aventertainments']={'running':True}
        urls=[]
        def send(adapter,request,**kwargs):
            urls.append(request.url)
            if network.urlsplit(request.url).path=='/':
                return response('<p>18歳以上の方のみ</p><a href="/dvd/index?lang=2&amp;cat=29">入場</a>')
            return response('<p>Product catalogue releases</p>')
        callback=MagicMock()
        with patch.object(network.PinnedTLSAdapter,'send',autospec=True,side_effect=send):age._run('aventertainments',callback)
        self.assertEqual(callback.call_args.args[1]['state'],'ok')
        self.assertEqual(age.source_url('aventertainments'),'https://www.aventertainments.com/dvd/index?lang=2&cat=29')
        self.assertEqual(network.urlsplit(urls[-1]).path,'/dvd/index')

    def test_cookiecloud_does_not_shadow_parent_domain_confirmed_cookie(self):
        with requests.Session() as session:
            session.cookies.set('adult','new',domain='.giga-web.jp',path='/')
            sent=[]
            def send(adapter,request,**kwargs):
                sent.append(request.headers.get('Cookie',''));return response('<p>Catalogue</p>')
            with patch.object(network.PinnedTLSAdapter,'send',autospec=True,side_effect=send):
                network.read_html('https://www.giga-web.jp/',session=session,cookie_domains={'.giga-web.jp':{'adult':'old'}})
            self.assertIn('adult=new',sent[0]);self.assertNotIn('adult=old',sent[0])

    def test_get_tries_next_validated_ip_but_post_does_not_replay(self):
        with patch.object(network,'public_candidates',return_value=['8.8.8.8','1.1.1.1']):
            with patch.object(network.PinnedTLSAdapter,'send',side_effect=[requests.exceptions.ConnectTimeout(),response('<p>ok</p>')]) as send:
                self.assertEqual(network.read_html('https://test.invalid/')[0],200)
                self.assertEqual(send.call_count,2)
        with patch.object(network.PinnedTLSAdapter,'send',side_effect=requests.exceptions.ConnectTimeout()) as send:
            with self.assertRaises(network.NetworkError):network.read_html('https://test.invalid/',request_method='POST',form_data={'yes':'1'})
            self.assertEqual(send.call_count,1)

    def test_configured_proxy_and_longer_timeout_apply_without_echoing_secret(self):
        with patch.object(network.PinnedTLSAdapter,'send',return_value=response('<p>ok</p>')) as send:
            network.read_html('https://test.invalid/',proxy_url='http://user:private@proxy.invalid:7890',timeout_seconds=25)
            self.assertEqual(send.call_args.kwargs['proxies']['https'],'http://user:private@proxy.invalid:7890')
            self.assertGreater(send.call_args.kwargs['timeout'][1],3)
        with patch.object(network.PinnedTLSAdapter,'send',side_effect=requests.exceptions.ProxyError('private')):
            with self.assertRaises(network.NetworkError) as cm:network.read_html('https://test.invalid/')
            self.assertEqual(cm.exception.state,'proxy_error');self.assertNotIn('private',str(cm.exception))


class SettingAndStateTests(unittest.TestCase):
    def test_default_preset_network_merges_base_and_redacts_credentials(self):
        with patch.object(hot_settings,'load_base_config',return_value={'network':{'timeout':'PT5S','proxy_server':None}}),patch.object(hot_settings,'get_preset',return_value={'mode':'form','form':{'network':{'proxy_server':'http://name:private@127.0.0.1:7890','timeout':'PT30S'}}}):
            self.assertEqual(hot_settings.network_options()['timeout_seconds'],30)
            public=hot_settings.public_network()
            self.assertEqual(public['mode'],'proxy');self.assertNotIn('private',str(public));self.assertNotIn('127.0.0.1',str(public))
        with patch.object(hot_settings,'load_base_config',return_value={}),patch.object(hot_settings,'get_preset',return_value={'mode':'yaml','content':'network:\n  timeout: PT2M\n  proxy_server: null'}):
            self.assertEqual(hot_settings.network_options()['timeout_seconds'],60)
        with patch.object(hot_settings,'load_base_config',return_value={'network':{'proxy_server':'file:///private'}}),patch.object(hot_settings,'get_preset',return_value=None):
            with self.assertRaises(network.NetworkError):hot_settings.network_options()

    def test_js_shell_means_http_connected_not_rendered(self):
        state,message=network.classify(200,'https://test.invalid','<div id="root"></div><script src="app.js"></script>')
        self.assertEqual(state,'js_shell');self.assertIn('HTTP 已连通',message)
        self.assertEqual(network.classify(403,'https://test.invalid/age_check/','<title>Just a moment...</title>')[0],'challenge')

    def test_single_source_retry_is_authenticated_bounded_and_fixed(self):
        app=FastAPI();app.include_router(hot_router.router)
        with TestClient(app) as client:
            self.assertEqual(client.post('/api/hot/connections/giga',json={}).status_code,401)
            app.dependency_overrides[current_user]=lambda:{'role':'operator'}
            self.assertEqual(client.post('/api/hot/connections/giga',json={}).status_code,403)
            app.dependency_overrides[current_user]=lambda:{'role':'admin'}
            with patch.object(hot,'retry_source',return_value={'sources':[]}) as retry:
                self.assertEqual(client.post('/api/hot/connections/giga',json={}).status_code,202)
                retry.assert_called_once_with('giga')
            self.assertEqual(client.post('/api/hot/connections/giga',json={'url':'http://internal'}).status_code,422)

    def test_stale_connection_batch_cannot_overwrite_age_result(self):
        for field in ['_checks','_check','_check_revisions']:
            self.enterContext(patch.object(hot,field,{}))
        hot._check['completed']=0
        def probe(source):
            with hot._LOCK:
                hot._check_revisions[source['id']]=1
                hot._checks[source['id']]={'state':'ok','message':'age success','checked_at':'same timestamp'}
            return {'state':'age_gate','checked_at':'same timestamp'}
        with patch.object(hot,'_probe',side_effect=probe):hot._run_checks()
        self.assertTrue(all(item['state']=='ok' for item in hot._checks.values()))


if __name__=='__main__':unittest.main()
