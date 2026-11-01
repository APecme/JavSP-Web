"""Offline consistency checks for the preliminary research, not scraper tests."""
import json
from datetime import datetime
from pathlib import Path
import unittest
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'docs' / 'hot-sources'
EXPECTED = {
    'avbase': 'https://www.avbase.net/',
    'avsox': 'https://avsox.click/cn',
    'dahlia': 'https://dahlia-av.jp/',
    'dmm': 'https://video.dmm.co.jp/',
    'faleno': 'https://faleno.jp/top/',
    'fc2': 'https://adult.contents.fc2.com/',
    'fc2ppvdb': 'https://www.fc2ppvdb.com/',
    'freejavbt': 'https://freejavbt.com/ja/uncensored',
    'getchu': 'https://www.getchu.com/',
    'giga': 'https://www.giga-web.jp/top.php',
    'iqqtv': 'https://iqqtv.net/',
    'jav321': 'https://www.jav321.com/',
    'javbus': 'https://www.javbus.com/',
    'javdb': 'https://javdb.com/',
    'javlibrary': 'https://www.javlibrary.com',
    'minnano': 'https://www.minnano-av.com/',
    'prestige': 'https://www.prestige-av.com/',
    'r18dev': 'https://r18.dev/',
    'xcity': 'https://xcity.jp/',
    'fanza': 'https://www.fanza.jp/',
    'aventertainments': 'https://www.aventertainments.com/',
    'av-wiki': 'https://av-wiki.net/',
    'avwikidb': 'https://avwikidb.com/',
    'xcream': 'https://zh-hant.xcream.net/',
    'hanime1': 'https://hanime1.me/',
    'javrate': 'https://www.javrate.com/',
    'jvid': 'https://www.jvid.com/',
    'supjav': 'https://supjav.com/zh/',
    'fd2ppv': 'https://fd2ppv.cc/',
    'ouxiangdanganku': 'https://www.ouxiangdanganku.com/',
}


@unittest.skipUnless(RESEARCH.is_dir(), 'Research documentation is not shipped in runtime images')
class HotSourceResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((RESEARCH / 'catalog.json').read_text(encoding='utf-8'))
        cls.sources = {s['id']: s for s in cls.catalog['sources']}
        cls.evidence_document = json.loads(
            (RESEARCH / 'evidence-2026-10-30.json').read_text(encoding='utf-8'))
        cls.observations = cls.evidence_document['observations']
        cls.evidence = {e['id']: e for e in cls.observations}

    def test_all_thirty_requested_addresses_have_one_entry(self):
        self.assertEqual(self.catalog['schema_version'], 1)
        self.assertEqual(len(self.catalog['sources']), 30)
        self.assertEqual({s['id']: s['url'] for s in self.catalog['sources']}, EXPECTED)
        report = (RESEARCH / 'README.md').read_text(encoding='utf-8')
        for source in self.sources.values():
            self.assertIn(source['name'], report)
            self.assertTrue(source['description'])
            self.assertTrue(source['notes'])

    def test_evidence_has_timestamps_status_and_bounded_site_fragments(self):
        self.assertEqual(len(self.observations), 38)
        self.assertEqual(len(self.evidence), 38)
        for evidence in self.observations:
            with self.subTest(evidence=evidence['id']):
                checked = datetime.fromisoformat(evidence['checked_at'])
                self.assertIsNotNone(checked.tzinfo)
                self.assertEqual(checked.date().isoformat(), self.catalog['researched_at'])
                self.assertIn(evidence['status'], (200, 403))
                self.assertRegex(evidence['html_utf8_sha256'], r'^[a-f0-9]{64}$')
                self.assertFalse(evidence['truncated'])
                self.assertTrue(evidence['observed_fragments'])
                for fragment in evidence['observed_fragments']:
                    self.assertLessEqual(len(fragment), 200)
                for key in ('requested_url', 'final_url'):
                    url = urlsplit(evidence[key])
                    self.assertEqual(url.scheme, 'https')
                    self.assertTrue(url.hostname)
                    self.assertIsNone(url.username)
                    self.assertIsNone(url.password)

    def test_entries_are_backed_by_same_site_observations(self):
        for source in self.sources.values():
            with self.subTest(source=source['id']):
                self.assertEqual(source['evidence_ids'], [source['id']])
                self.assertEqual(self.evidence[source['id']]['requested_url'], source['url'])
                for entry in source['entries']:
                    self.assertIn(entry['verification'],
                                  ('page_checked', 'link_observed', 'section_observed'))
                    observation = self.evidence[entry['evidence_id']]
                    self.assertEqual(urlsplit(entry['url']).hostname,
                                     urlsplit(source['url']).hostname)
                    self.assertEqual(urlsplit(observation['requested_url']).hostname,
                                     urlsplit(source['url']).hostname)
                    if entry['verification'] in ('page_checked', 'section_observed'):
                        self.assertEqual(entry['url'], observation['requested_url'])
                        self.assertEqual(observation['status'], 200)

    def test_non_work_rankings_are_not_labeled_as_film_heat(self):
        self.assertEqual(self.sources['avbase']['ranking_signal'], 'performer_rank')
        self.assertEqual(self.sources['r18dev']['ranking_signal'], 'catalog_count_snapshot')
        self.assertIn('2025-01-24', self.sources['r18dev']['notes'])
        self.assertEqual(self.sources['getchu']['ranking_signal'], 'non_film_sales_rank')
        self.assertEqual(self.sources['av-wiki']['ranking_signal'], 'updates_not_rank')
        fd2 = {urlsplit(e['url']).path: e['kind']
               for e in self.sources['fd2ppv']['entries']}
        self.assertEqual(fd2['/ranking'], 'contributor_rank')
        self.assertEqual(fd2['/trending'], 'site_trending')

    def test_http_success_is_not_automatically_usable_content(self):
        for id, expected in {
            'avsox': 'js_shell', 'javdb': 'region_blocked',
            'dmm': 'age_gate', 'fanza': 'age_gate', 'javbus': 'age_gate',
            'xcream': 'general_catalog', 'ouxiangdanganku': 'parking_suspected',
        }.items():
            with self.subTest(source=id):
                self.assertEqual(self.sources[id]['access'], expected)
                self.assertEqual(self.evidence[id]['status'], 200)
        self.assertEqual(self.sources['prestige']['access'], 'maintenance')
        self.assertEqual(self.evidence['prestige']['status'], 403)
        self.assertEqual(self.sources['ouxiangdanganku']['recommended_role'], 'exclude')
        self.assertEqual(self.sources['javdb']['entries'], [])

    def test_existing_crawler_claims_have_files_and_keep_host_distinctions(self):
        for source in self.sources.values():
            for crawler in source['existing_crawlers']:
                self.assertTrue((ROOT / 'vendor' / 'JavSP' / 'javsp' / 'web' /
                                 (crawler + '.py')).is_file())
        self.assertEqual(self.sources['dmm']['source_group'],
                         self.sources['fanza']['source_group'])
        self.assertNotEqual(self.sources['av-wiki']['source_group'],
                            self.sources['avwikidb']['source_group'])
        self.assertEqual(self.sources['avwikidb']['existing_crawlers'], [])
        self.assertEqual(self.sources['getchu']['existing_crawlers'], ['dl_getchu'])
        self.assertEqual(self.sources['javlibrary']['existing_crawlers'], ['javlib'])

    def test_published_evidence_excludes_credentials_and_remote_payloads(self):
        # A deliberately small evidence schema: never dump headers or full HTML.
        expected_fields = {'id', 'requested_url', 'checked_at', 'status', 'final_url',
                           'title', 'content_type', 'truncated', 'html_utf8_sha256',
                           'observed_fragments'}
        for evidence in self.observations:
            self.assertEqual(set(evidence), expected_fields)
            for fragment in evidence['observed_fragments']:
                self.assertNotRegex(fragment.lower(),
                                    r'<script|<img|csrf|bearer |set-cookie|magnet:')
        self.assertEqual({p.name for p in RESEARCH.iterdir()},
                         {'README.md', 'catalog.json', 'evidence-2026-10-30.json'})


if __name__ == '__main__':
    unittest.main()
