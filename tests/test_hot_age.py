import copy
import socket
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient

from javsp_web import hot, hot_age as age, hot_network as network, hot_router
from javsp_web.auth import current_user

GATES = {
 'dmm': ('https://www.dmm.co.jp/age_check/', '<title>年齢認証</title><a href="https://www.dmm.co.jp/age_check/=/declared=yes/?rurl=https%3A%2F%2Fvideo.dmm.co.jp%2F">はい</a>'),
 'fanza': ('https://www.dmm.co.jp/age_check/', '<title>年齢認証</title><a href="https://www.dmm.co.jp/age_check/=/declared=yes/?rurl=https%3A%2F%2Fwww.dmm.co.jp%2Ftop%2F">はい</a>'),
 'giga': ('https://www.giga-web.jp/top.php', '<p>あなたは18歳以上ですか？</p><a href="/cookie_set.php">はい</a>'),
 'xcity': ('https://xcity.jp/', '<p>18歳未満の方は退出</p><a href="/?over18=ok&r=%2F">はい</a>'),
 'javbus': ('https://www.javbus.com/doc/driver-verify?referer=https%3A%2F%2Fwww.javbus.com%2F', '<title>Age Verification</title><form id="form1" method="post" action=""><label><input type="checkbox">我已經成年</label><input type="submit" name="Submit" value="確認"></form>'),
 'aventertainments': ('https://www.aventertainments.com/', '<p>18歳以上の方のみ</p><a href="/dvd/index?lang=2&cat=29">DVD販売に入場する</a>'),
}


class AgeTests(unittest.TestCase):
 def setUp(self):
  self.enterContext(patch.object(age, '_sessions', {}))
  self.enterContext(patch.object(age, '_jobs', {}))
  self.enterContext(patch('javsp_web.storage.get_cookiecloud_settings',return_value={'enabled':False}))

 def run_flow(self,id='giga',final='ok'):
  age._jobs[id]={'running':True,'started':0}
  session=requests.Session()
  session.cookies.set('adult','yes',domain=next(iter(age._hosts(id))),path='/')
  session.cookies.set('evil','do-not-store',domain='evil.invalid',path='/')
  session.cookies.set('supercookie','blocked',domain='jp',path='/')
  url,page=GATES[id]
  normal=(200,age.BY_ID[id]['url'],'<title>Catalogue</title><p>Release list</p>')
  blocked=(200,url,page) if final=='age_gate' else (403,url,'<title>Just a moment...</title>')
  responses=[(200,url,page),normal,normal] if final=='ok' else [(200,url,page),blocked,blocked]
  callback=MagicMock()
  with patch.object(age.requests,'Session',return_value=session),patch.object(age,'read_html',side_effect=responses) as read:
   age._run(id,callback)
  return read,callback

 def test_start_requires_explicit_confirmation_and_fixed_supported_source(self):
  with patch.object(age.threading,'Thread') as thread:
   for id,confirmed in [('giga',False),('unknown',True),('avbase',True)]:
    with self.assertRaises(ValueError):age.start(id,confirmed,MagicMock())
   thread.assert_not_called()
   result=age.start('giga',True,MagicMock());self.assertTrue(result['running'])
   age.start('giga',True,MagicMock());self.assertEqual(thread.call_count,1)
   age._jobs['giga']['running']=False
   with self.assertRaisesRegex(ValueError,'冷却'):age.start('giga',True,MagicMock())

 def test_all_six_known_flows_must_be_observed_on_page(self):
  for id,(url,page) in GATES.items():
   with self.subTest(id=id):
    flow=age.action(id,url,page);self.assertIsNotNone(flow)
    self.assertIn(flow[0],('GET','POST'))
    self.assertIsNone(age.action(id,url,'<p>unknown workflow</p>'))

 def test_rejects_form_login_captcha_identity_extra_fields_or_cross_site(self):
  url,page=GATES['javbus']
  for extra in ['<input name="password" type="password">','<input name="captcha">','<input type="file">']:
   self.assertIsNone(age.action('javbus',url,page.replace('</form>',extra+'</form>')))
  self.assertIsNone(age.action('javbus',url,page.replace('action=""','action="https://evil.invalid/"')))
  self.assertIsNone(age.action('dmm',GATES['dmm'][0],GATES['dmm'][1].replace('video.dmm.co.jp','evil.invalid')))
  self.assertIsNone(age.action('giga',GATES['giga'][0],GATES['giga'][1].replace('/cookie_set.php','https://evil.invalid/cookie_set.php')))

 def test_submission_rechecks_source_before_reporting_success_and_scopes_cookie(self):
  read,callback=self.run_flow()
  self.assertEqual(read.call_count,3)
  self.assertEqual(read.call_args_list[-1].args[0],age.BY_ID['giga']['url'])
  result=callback.call_args.args[1];self.assertEqual(result['state'],'ok')
  jar=age.cookies('giga');self.assertEqual(len(jar),1)
  self.assertEqual(jar.get('adult'),'yes')
  self.assertNotIn('do-not-store',str(age.status('giga')))
  self.assertEqual(len(age.cookies('javbus')),0)
  jar.clear();self.assertEqual(len(age.cookies('giga')),1)

 def test_javbus_uses_verified_post_fields_not_generic_checkbox_hack(self):
  read,callback=self.run_flow('javbus')
  action=read.call_args_list[1]
  self.assertEqual(action.kwargs['request_method'],'POST')
  self.assertEqual(action.kwargs['form_data'],{'Submit':'確認'})
  self.assertEqual(action.kwargs['allowed_hosts'],{'www.javbus.com'})

 def test_still_age_gate_is_not_success_and_does_not_store_cookies(self):
  read,callback=self.run_flow(final='age_gate')
  self.assertEqual(callback.call_args.args[1]['state'],'age_gate')
  self.assertEqual(len(age.cookies('giga')),0)

 def test_challenge_is_not_bypassed_or_retried_and_no_cookie_persisted(self):
  read,callback=self.run_flow(final='challenge')
  self.assertEqual(read.call_count,2)
  self.assertEqual(callback.call_args.args[1]['state'],'challenge')
  self.assertEqual(len(age.cookies('giga')),0)

 def test_missing_action_and_network_failure_leave_no_false_success(self):
  age._jobs['giga']={'running':True}
  cb=MagicMock()
  with patch.object(age,'read_html',return_value=(200,GATES['giga'][0],'<p>あなたは18歳以上ですか？</p>')) as read:
   age._run('giga',cb)
  self.assertEqual(read.call_count,1);self.assertEqual(cb.call_args.args[1]['state'],'age_gate')
  with patch.object(age,'read_html',side_effect=network.NetworkError('timeout','Timed out')):
   age._run('giga',cb)
  self.assertEqual(cb.call_args.args[1]['state'],'timeout');self.assertFalse(age.status('giga')['running'])

 def test_cookie_jar_expires_and_is_process_local(self):
  self.run_flow()
  with patch.object(age.time,'monotonic',return_value=10**12):self.assertEqual(len(age.cookies('giga')),0)

 def test_cookiecloud_is_optional_and_age_cookie_used_for_normal_source_reads(self):
  self.run_flow()
  with patch.object(hot,'read_html',return_value=(200,'url','page')) as read:
   hot._read_source(age.BY_ID['giga']['url'],'giga')
   self.assertEqual(read.call_args.kwargs['session'].cookies.get('adult'),'yes')


class NetworkAndRemovalTests(unittest.TestCase):
 def rows(self,*ips):
  return [(socket.AF_INET if ':' not in ip else socket.AF_INET6,socket.SOCK_STREAM,0,'',(ip,443)) for ip in ips]

 def test_mixed_public_ipv4_and_bad_ipv6_selects_public_only(self):
  with patch.object(socket,'getaddrinfo',return_value=self.rows('2001::1234','210.157.79.202')):
   self.assertEqual(network.resolve_public('https://faleno.jp/')[1],'210.157.79.202')
  with patch.object(socket,'getaddrinfo',return_value=self.rows('192.168.0.1','8.8.8.8')):
   self.assertEqual(network.resolve_public('https://example.invalid/')[1],'8.8.8.8')

 def test_private_only_and_multicast_dns_are_distinct_from_unsafe_redirect(self):
  for ip in ['127.0.0.1','169.254.169.254','192.168.0.1','2001::1234','224.0.0.1']:
   with patch.object(socket,'getaddrinfo',return_value=self.rows(ip)):
    with self.assertRaises(network.NetworkError) as cm:network.resolve_public('https://example.invalid/')
    self.assertEqual(cm.exception.state,'dns_blocked')

 def test_confirm_redirects_cannot_leave_first_party_or_replay_post(self):
  response=MagicMock(status_code=307,headers={'Location':'https://evil.invalid/receive'})
  response.__enter__.return_value=response
  with patch.object(network.requests.Session,'post',return_value=response) as post:
   with self.assertRaises(network.NetworkError) as cm:
    network.read_html('https://www.javbus.com/doc/driver-verify',request_method='POST',form_data={'Submit':'確認'},allowed_hosts={'www.javbus.com'})
  self.assertEqual(cm.exception.state,'unsafe_redirect');post.assert_called_once()
  with patch.object(network.requests.Session,'get') as get:
   with self.assertRaises(network.NetworkError):
    network.read_html('https://evil.invalid/',allowed_hosts={'www.javbus.com'})
   get.assert_not_called()

 def test_html_url_over18_does_not_keep_successful_confirmation_marked_as_gate(self):
  self.assertEqual(network.classify(200,'https://xcity.jp/?over18=ok&r=/','<p>Available releases catalogue</p>')[0],'ok')

 def test_admin_permission_and_false_confirmation_and_clash_404(self):
  app=FastAPI();app.include_router(hot_router.router)
  with TestClient(app) as client:
   self.assertEqual(client.post('/api/hot/age/giga',json={'confirmed':True}).status_code,401)
   app.dependency_overrides[current_user]=lambda:{'role':'operator'}
   self.assertEqual(client.post('/api/hot/age/giga',json={'confirmed':True}).status_code,403)
   app.dependency_overrides[current_user]=lambda:{'role':'admin'}
   self.assertEqual(client.post('/api/hot/age/giga',json={'confirmed':False}).status_code,400)
   with patch.object(hot,'confirm_age',return_value={'running':True}) as confirm:
    response=client.post('/api/hot/age/giga',json={'confirmed':True})
    self.assertEqual(response.status_code,202);confirm.assert_called_once_with('giga',True)
    self.assertEqual(response.headers['Cache-Control'],'no-store')
   for method,path in [('GET','/api/hot/clash'),('POST','/api/hot/clash'),('POST','/api/hot/clash/cancel'),('POST','/api/hot/clash/export')]:
    self.assertEqual(client.request(method,path,json={}).status_code,404)

 def test_ui_and_build_no_clash_and_removed_paragraph(self):
  root=Path(__file__).resolve().parents[1]
  for name in ['javsp_web/web/index.html','javsp_web/web/assets/hot.js','scripts/build_demo.py']:
   text=(root/name).read_text()
   self.assertNotIn('hot-clash',text);self.assertNotIn('Firefox：官方说明为自行编译',text)
  self.assertFalse((root/'javsp_web/hot_clash.py').exists())


if __name__=='__main__':unittest.main()
