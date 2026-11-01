import unittest
from unittest.mock import patch, MagicMock
from javsp_web import hot, hot_network
from javsp_web.hot_catalog import merge_items


class MetadataAndCookieTests(unittest.TestCase):
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
        self.assertEqual(session.cookies.clear.call_count,0)

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


if __name__ == '__main__': unittest.main()
