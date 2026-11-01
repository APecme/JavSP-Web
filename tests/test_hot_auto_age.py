import unittest
from unittest.mock import MagicMock,patch

from javsp_web import hot,hot_age as age,hot_network as network


class AutoAgeTests(unittest.TestCase):
 def setUp(self):
  self.enterContext(patch.object(age,'_sessions',{}))
  self.enterContext(patch.object(age,'_jobs',{}))
  self.enterContext(patch('javsp_web.storage.get_cookiecloud_settings',return_value={'enabled':False}))
  self.enterContext(patch.object(hot,'network_options',return_value={'proxy_url':None,'timeout_seconds':20}))

 def test_normal_source_read_automatically_submits_observed_declaration(self):
  page='<p>あなたは18歳以上ですか？</p><a href="/cookie_set.php">はい</a>'
  with patch.object(hot,'read_html',side_effect=[(200,'https://www.giga-web.jp/top.php',page),(200,'https://www.giga-web.jp/top.php','<p>Catalogue</p>'),(200,'https://www.giga-web.jp/top.php','<p>Catalogue</p>')]) as read:
   result=hot._read_source('https://www.giga-web.jp/top.php','giga')
  self.assertEqual(read.call_count,3)
  self.assertEqual(read.call_args_list[1].args[0],'https://www.giga-web.jp/cookie_set.php')
  self.assertEqual(result[2],'<p>Catalogue</p>')
  self.assertTrue(age.status('giga')['success'])

 def test_get_status_does_not_submit_or_create_jobs(self):
  with patch.object(age,'read_html') as read:
   for _ in range(3):hot.connections()
  read.assert_not_called();self.assertEqual(age._jobs,{})

 def test_unadapted_login_captcha_or_region_is_not_submitted(self):
  for page in ['<title>Just a moment...</title>','<title>Age Verification</title><form><input name="password"></form>','<p>not available in your country</p>']:
   age._jobs.clear()
   with patch.object(hot,'read_html',return_value=(200,'https://www.giga-web.jp/',page)) as read:
    try:hot._read_source('https://www.giga-web.jp/','giga')
    except network.NetworkError:pass
   self.assertEqual(read.call_count,1)

 def test_failed_auto_declaration_has_cooldown_without_repeated_submission(self):
  page='<p>あなたは18歳以上ですか？</p><a href="/cookie_set.php">はい</a>'
  with patch.object(hot,'read_html',return_value=(200,'https://www.giga-web.jp/top.php',page)) as read:
   hot._read_source('https://www.giga-web.jp/top.php','giga')
   self.assertEqual(read.call_count,3)
   hot._read_source('https://www.giga-web.jp/top.php','giga')
   self.assertEqual(read.call_count,4)
  self.assertFalse(age.status('giga')['success'])

 def test_exact_fanza_hosts_and_safe_return_targets(self):
  self.assertIn('www.fanza.jp',age._hosts('fanza'))
  self.assertIn('fanza.jp',age._hosts('fanza'))
  for target in ['https://www.fanza.jp/top/','https://www.dmm.co.jp/top/']:
   from urllib.parse import quote
   page='<a href="https://www.dmm.co.jp/age_check/=/declared=yes/?rurl='+quote(target,safe='')+'">はい</a>'
   self.assertIsNotNone(age.action('fanza','https://www.dmm.co.jp/age_check/',page))
  for target in ['https://evil.fanza.jp/top/','https://www.fanza.jp.evil.invalid/top/','https://www.fanza.jp/redirect?url=evil','http://www.fanza.jp/top/']:
   from urllib.parse import quote
   page='<a href="https://www.dmm.co.jp/age_check/=/declared=yes/?rurl='+quote(target,safe='')+'">はい</a>'
   self.assertIsNone(age.action('fanza','https://www.dmm.co.jp/age_check/',page))

 def test_fanza_read_chain_allows_only_exact_first_party_hosts(self):
  import requests
  import io
  from http.client import HTTPMessage
  from types import SimpleNamespace
  seen=[]
  def response(body,status=200,location=None,cookie=None):
   class Raw:
    def __init__(self):
     self.buffer=io.BytesIO(body.encode());message=HTTPMessage()
     if cookie:message.add_header('Set-Cookie',cookie)
     self._original_response=SimpleNamespace(msg=message)
    def read1(self,n,decode_content=True):return self.buffer.read(n)
    def close(self):pass
    def release_conn(self):pass
   r=requests.Response();r.status_code=status;r.headers={'Content-Type':'text/html'};r.raw=Raw()
   if location:r.headers['Location']=location
   return r
  def send(adapter,request,**kwargs):
   host=request.headers['Host'];path=network.urlsplit(request.url).path;seen.append(host)
   if host=='www.fanza.jp':return response('',302,'https://www.dmm.co.jp/top/')
   if path.startswith('/age_check/=/declared=yes/'):
    return response('',302,'https://www.fanza.jp/top/','age=yes; Domain=.dmm.co.jp; Path=/; Secure')
   if 'age=yes' in request.headers.get('Cookie',''):return response('<p>FANZA catalogue</p>')
   return response('<title>年齢認証</title><a href="https://www.dmm.co.jp/age_check/=/declared=yes/?rurl=https%3A%2F%2Fwww.fanza.jp%2Ftop%2F">はい</a>')
  with patch.object(network,'resolve_public',side_effect=lambda url:(network.urlsplit(url),'8.8.8.8')),patch.object(network,'public_candidates',return_value=['8.8.8.8']),patch.object(network.PinnedTLSAdapter,'send',autospec=True,side_effect=send):
   result=hot._read_source('https://www.fanza.jp/','fanza')
  self.assertEqual(network.classify(*result)[0],'ok')
  self.assertEqual(set(seen),{'www.fanza.jp','www.dmm.co.jp'})
  self.assertTrue(age.status('fanza')['success'])


if __name__=='__main__':unittest.main()
