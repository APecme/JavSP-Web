import copy
import json
import socket
import threading
import unittest
from unittest.mock import patch, MagicMock

import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from javsp_web import hot_clash as clash, hot, hot_router, hot_network
from javsp_web.auth import current_user
from javsp_web.hot_catalog import merge_items


class ControllerFake:
    def __init__(self):
        self.mode, self.selected = 'rule', 'Original'
        self.calls = []
        self.fail_test = False
        self.fail_restore = False
    def request(self, method, path, body=None):
        self.calls.append((method, path, body))
        if method == 'GET' and path == '/configs': return {'mode': self.mode}
        if method == 'GET' and path == '/proxies':
            return {'proxies': {'GLOBAL': {'type': 'Selector', 'now': self.selected, 'all': ['Node A', 'Node B', 'Original']},
                                'Node A': {'type': 'Shadowsocks'}, 'Node B': {'type': 'Vmess'},
                                'Original': {'type': 'Selector'}, 'DIRECT': {'type': 'Direct'}}}
        if method == 'GET' and path == '/proxies/GLOBAL': return {'now': self.selected}
        if method == 'PATCH':
            if self.fail_restore and body['mode'] == 'rule': raise clash.ClashError('fail restore')
            self.mode = body['mode']; return {}
        if method == 'PUT':
            if self.fail_test and body['name'] == 'Node A': raise clash.ClashError('fail node')
            self.selected = body['name']; return {}


class ClashTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(clash, '_job', {}))
        self.enterContext(patch.object(clash, '_cancel', threading.Event()))

    def run_fake(self, fake=None, stop=None):
        fake = fake or ControllerFake()
        clash._job.update(id='job', results=[], completed=0, running=True)
        with patch.object(clash, 'exit_info', return_value={'ip': '1.1.1.1', 'country': 'Test', 'error': ''}), \
             patch.object(clash, 'read_html', return_value=(200, 'https://www.avbase.net/', '<p>Works</p>')):
            clash._run(fake, 'http://127.0.0.1:7890', ['avbase'], stop or threading.Event())
        return fake

    def test_confirm_required_and_secret_not_in_status(self):
        with self.assertRaisesRegex(clash.ClashError, '必须确认'):
            clash.start('anything', 'secret', 'anything', ['avbase'], False)
        with patch.object(clash, 'Controller'), patch.object(clash, 'endpoint', return_value='http://127.0.0.1:7890'), patch.object(clash.threading, 'Thread'):
            result = clash.start('http://localhost:9090', 'private-secret', 'http://localhost:7890', ['avbase'], True)
            self.assertNotIn('private-secret', str(result))
            self.assertTrue(result['running'])
            with self.assertRaisesRegex(clash.ClashError, '已有'):
                clash.start('http://localhost:9090', '', 'http://localhost:7890', ['avbase'], True)

    def test_only_fixed_targets_and_max_three(self):
        with patch.object(clash, 'Controller'), patch.object(clash, 'endpoint'):
            for ids in [[], ['http://arbitrary'], ['avbase']*4]:
                with self.assertRaises(clash.ClashError):
                    clash.start('http://localhost:9090', '', 'http://localhost:7890', ids, True)

    def test_switches_leaf_nodes_and_restores_both_mode_and_selection(self):
        fake = self.run_fake()
        self.assertEqual(fake.mode, 'rule')
        self.assertEqual(fake.selected, 'Original')
        status = clash.status()
        self.assertEqual(status['restore_state'], 'restored')
        self.assertEqual(status['completed'], 2)
        self.assertEqual([r['name'] for r in status['results']], ['Node A', 'Node B'])
        self.assertFalse(status['running'])

    def test_failure_on_node_still_restores_and_records_error(self):
        fake = ControllerFake(); fake.fail_test = True
        self.run_fake(fake)
        self.assertEqual(fake.mode, 'rule')
        self.assertEqual(fake.selected, 'Original')
        self.assertTrue(clash.status()['results'][0]['error'])
        self.assertEqual(clash.status()['restore_state'], 'restored')

    def test_cancel_restores_and_failed_restore_has_prominent_warning(self):
        stop = threading.Event(); stop.set()
        fake = self.run_fake(stop=stop)
        self.assertEqual(fake.mode, 'rule')
        self.assertEqual(clash.status()['completed'], 0)
        self.assertIn('已取消', clash.status()['message'])
        fake = ControllerFake();fake.fail_restore = True
        self.run_fake(fake)
        self.assertEqual(clash.status()['restore_state'], 'failed')
        self.assertIn('警告', clash.status()['message'])
        self.assertEqual(fake.selected, 'Original')

    def test_missing_recoverable_original_state_never_mutates(self):
        fake = ControllerFake()
        original = fake.request
        fake.request = lambda method, path, body=None: {} if path == '/configs' else original(method, path, body)
        self.run_fake(fake)
        self.assertFalse(any(method in ('PUT','PATCH') for method,_,_ in fake.calls))
        self.assertEqual(clash.status()['restore_state'], 'not_needed')

    def prepare_export(self):
        clash._job.update(id='job',running=False,restore_state='restored',results=[
            {'name':'Node A','error':'','exit':{'ip':'1.1.1.1'},'sites':[{'source_id':'avbase','state':'ok'},{'source_id':'javdb','state':'region_blocked'}]},
            {'name':'Node B','error':'','exit':{'ip':'8.8.8.8'},'sites':[{'source_id':'javdb','state':'ok'},{'source_id':'avbase','state':'region_blocked'}]},
        ])
        return {'proxies':[{'name':'Node A','type':'ss','password':'private'},{'name':'Node B','type':'ss'}],
                'proxy-groups':[{'name':'Original','type':'select','proxies':['Node A']}],
                'rules':['MATCH,Original'],'dns':{'enable':True},'secret':'original-secret'}

    def test_yaml_preserves_original_and_per_domain_only_passing_nodes(self):
        original = self.prepare_export()
        rendered = clash.export_yaml(yaml.safe_dump(original), ['Node A','Node B'], 'job')
        output = yaml.safe_load(rendered)
        self.assertEqual(output['proxies'],original['proxies'])
        self.assertEqual(output['secret'],'original-secret')
        self.assertEqual(output['dns'],original['dns'])
        self.assertEqual(output['rules'][-1],'MATCH,Original')
        groups={g['name']:g for g in output['proxy-groups']}
        self.assertEqual(groups['JAVSP-HOT-avbase']['proxies'],['Node A'])
        self.assertEqual(groups['JAVSP-HOT-javdb']['proxies'],['Node B'])
        self.assertIn('DOMAIN-SUFFIX,javdb.com,JAVSP-HOT-javdb',output['rules'])
        self.assertNotIn('faleno.jp',rendered)

    def test_export_rejects_wrong_job_failed_restore_unknown_node_aliases(self):
        original=self.prepare_export()
        for text,nodes,job in [(yaml.safe_dump(original),['bad'],'job'),(yaml.safe_dump(original),['Node A'],'wrong'),('a: &x [a]\nb: *x',['Node A'],'job'),('[]',['Node A'],'job')]:
            with self.assertRaises(clash.ClashError): clash.export_yaml(text,nodes,job)
        clash._job['restore_state']='failed'
        with self.assertRaises(clash.ClashError): clash.export_yaml(yaml.safe_dump(original),['Node A'],'job')

    def test_missing_original_node_requires_provider(self):
        original=self.prepare_export();original['proxies']=[]
        with self.assertRaises(clash.ClashError): clash.export_yaml(yaml.safe_dump(original),['Node A'],'job')
        original['proxy-providers']={'subscription':{'type':'http','url':'https://subscription.invalid/private'}}
        out=yaml.safe_load(clash.export_yaml(yaml.safe_dump(original),['Node A'],'job'))
        group=out['proxy-groups'][-1]
        self.assertEqual(group['use'],['subscription'])
        self.assertEqual(group['filter'],'^(Node A)$')

    def test_control_endpoint_rejects_metadata_public_http_and_credentials(self):
        def rows(ip):return [(socket.AF_INET,socket.SOCK_STREAM,0,'',(ip,9090))]
        for address in ['169.254.169.254','224.0.0.1','0.0.0.0','8.8.8.8']:
            with patch.object(socket,'getaddrinfo',return_value=rows(address)):
                with self.assertRaises(clash.ClashError):clash.endpoint('http://controller.invalid:9090')
        with patch.object(socket,'getaddrinfo',return_value=rows('192.168.1.2')):
            self.assertEqual(clash.endpoint('http://controller.invalid:9090/ui'),'http://controller.invalid:9090')
            for url in ['http://user:pass@controller.invalid','file:///tmp/key','http://controller.invalid/subscription?token=x']:
                with self.assertRaises(clash.ClashError):clash.endpoint(url)


class IntegrationTests(unittest.TestCase):
    def test_clash_routes_require_admin_and_confirmation(self):
        app=FastAPI();app.include_router(hot_router.router)
        with TestClient(app) as client:
            for method,path,body in [('GET','/api/hot/clash',None),('POST','/api/hot/clash/cancel',{})]:
                self.assertEqual(client.request(method,path,json=body).status_code,401)
            app.dependency_overrides[current_user]=lambda:{'role':'operator'}
            self.assertEqual(client.get('/api/hot/clash').status_code,403)
            app.dependency_overrides[current_user]=lambda:{'role':'admin'}
            with patch.object(clash,'start',side_effect=clash.ClashError('must confirm')):
                response=client.post('/api/hot/clash',json={'controller_url':'http://localhost:9090','proxy_url':'http://localhost:7890','source_ids':['avbase']})
            self.assertEqual(response.status_code,400)
            with patch.object(clash,'export_yaml',return_value='rules: []\n'):
                response=client.post('/api/hot/clash/export',json={'original_yaml':'rules: []','selected_nodes':['Node A'],'job_id':'job'})
            self.assertEqual(response.headers['Cache-Control'],'no-store')
            self.assertIn('attachment',response.headers['Content-Disposition'])

    def test_cookiecloud_read_is_optional_and_failures_not_silently_ignored(self):
        from javsp_web import storage,cookiecloud
        with patch.object(storage,'get_cookiecloud_settings',return_value={'enabled':True}),patch.object(cookiecloud,'get_synced_cookies',return_value={'example.invalid':{'session':'secret'}}),patch.object(hot,'read_html',return_value=(200,'url','html')) as read:
            hot._read_source('https://example.invalid/')
            self.assertEqual(read.call_args.kwargs['cookie_domains'],{'example.invalid':{'session':'secret'}})
        with patch.object(storage,'get_cookiecloud_settings',return_value={'enabled':True}),patch.object(cookiecloud,'get_synced_cookies',side_effect=cookiecloud.CookieCloudError('private')):
            with self.assertRaises(hot_network.NetworkError) as cm:hot._read_source('https://example.invalid/')
            self.assertNotIn('private',str(cm.exception))

    def test_cookiecloud_cookies_are_scoped_per_redirect_host(self):
        import io
        session=MagicMock();session.__enter__.return_value=session
        responses=[]
        for status,headers,data in [(302,{'Location':'https://other.invalid/'},b''),(200,{'Content-Type':'text/html'},b'ok')]:
            response=MagicMock(status_code=status,headers=headers);response.__enter__.return_value=response
            raw=io.BytesIO(data)
            response.raw.read1.side_effect=lambda n,decode_content=True,raw=raw:raw.read(n)
            responses.append(response)
        session.get.side_effect=responses
        with patch.object(hot_network.requests,'Session',return_value=session):
            hot_network.read_html('https://sub.example.invalid/',cookie_domains={
                '.example.invalid':{'session':'private'}, 'evil-example.invalid':{'evil':'no'},
                'other.invalid':{'other':'scoped'}})
        calls=session.cookies.set.call_args_list
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[0].args,('session','private'))
        self.assertEqual(calls[0].kwargs['domain'],'sub.example.invalid')
        self.assertEqual(calls[1].args,('other','scoped'))
        self.assertEqual(session.cookies.clear.call_count,2)

    def test_unified_merge_deduplicates_and_keeps_source_ranks(self):
        def group(source,identifier,rank,date):
            return {'label':'rank','source_id':source,'items':[{'id':source+identifier,'identifier':identifier,'source_id':source,'source_name':source,'url':'https://example.invalid','category':'censored','title':'Title','rank':rank,'date':date,'actors':[source]}]}
        groups=[group('a','ABC-123',2,'2026-10-01'),group('b','abc123',1,'2026-10-01'),group('c','XYZ-1',1,'2026-10-20')]
        merged=merge_items(groups,'latest')
        self.assertEqual(len(merged),2)
        self.assertEqual(merged[0]['identifier'],'XYZ-1')
        self.assertEqual(len(merged[1]['sources']),2)
        self.assertEqual(merged[1]['actors'],['a','b'])
        self.assertEqual([s['rank'] for s in merged[1]['sources']],[2,1])

    def test_fd2_metadata_and_unknown_category_not_guessed(self):
        page='''<div class="artist-card"><h3><a href="/articles/123456">123456</a></h3><div class="artist-content"><a>Test release</a></div><div class="artist-release"><span>2026-11-01</span></div><div class="artist-tags"><a>Tag A</a></div><div class="stats"><div class="stat-item"><span class="stat-value">42</span><i class="icon-remove_red_eye"></i></div></div></div>'''
        item=hot.parse_feed('fd2ppv','all','hot',page,'https://fd2ppv.cc/trending')[0]
        self.assertEqual(item['category'],'unknown')
        self.assertEqual(item['identifier'],'FC2-123456')
        self.assertEqual(item['views'],42)
        self.assertEqual(item['tags'],['Tag A'])
        self.assertEqual(item['date'],'2026-11-01')


if __name__=='__main__':unittest.main()
