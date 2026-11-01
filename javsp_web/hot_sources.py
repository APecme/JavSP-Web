"""Fixed, reviewable hot-page source allowlist (never user-supplied URLs)."""

# Keep separate from docs/: Docker and frozen builds ship this module.
SOURCES = (
    ('avbase', 'AvBase', 'https://www.avbase.net/'),
    ('avsox', 'AVSOX', 'https://avsox.click/cn'),
    ('dahlia', 'DAHLIA', 'https://dahlia-av.jp/'),
    ('dmm', 'DMM / FANZA 视频', 'https://video.dmm.co.jp/'),
    ('faleno', 'FALENO', 'https://faleno.jp/top/'),
    ('fc2', 'FC2', 'https://adult.contents.fc2.com/'),
    ('fc2ppvdb', 'FC2PPVDB', 'https://www.fc2ppvdb.com/'),
    ('freejavbt', 'FREE JAV BT', 'https://freejavbt.com/ja/uncensored'),
    ('getchu', 'Getchu', 'https://www.getchu.com/'),
    ('giga', 'GIGA', 'https://www.giga-web.jp/top.php'),
    ('iqqtv', 'iQQTV', 'https://iqqtv.net/'),
    ('jav321', 'JAV321', 'https://www.jav321.com/'),
    ('javbus', 'JavBus', 'https://www.javbus.com/'),
    ('javdb', 'JavDB', 'https://javdb.com/'),
    ('javlibrary', 'JAVLibrary', 'https://www.javlibrary.com'),
    ('minnano', 'Minnano', 'https://www.minnano-av.com/'),
    ('prestige', 'PRESTIGE', 'https://www.prestige-av.com/'),
    ('r18dev', 'R18.dev', 'https://r18.dev/'),
    ('xcity', 'XCITY', 'https://xcity.jp/'),
    ('fanza', 'FANZA', 'https://www.fanza.jp/'),
    ('aventertainments', 'AV Entertainment', 'https://www.aventertainments.com/'),
    ('av-wiki', 'av-wiki', 'https://av-wiki.net/'),
    ('avwikidb', 'AVWikiDB', 'https://avwikidb.com/'),
    ('xcream', 'XCREAM', 'https://zh-hant.xcream.net/'),
    ('hanime1', 'Hanime1', 'https://hanime1.me/'),
    ('javrate', 'Javrate', 'https://www.javrate.com/'),
    ('jvid', 'JVID', 'https://www.jvid.com/'),
    ('supjav', 'SupJav', 'https://supjav.com/zh/'),
    ('fd2ppv', 'FD2', 'https://fd2ppv.cc/'),
    ('ouxiangdanganku', '偶像档案库', 'https://www.ouxiangdanganku.com/'),
)
BY_ID = {id: {'id': id, 'name': name, 'url': url} for id, name, url in SOURCES}

# No data is inferred for the other 27 sites. These are HTML list adapters,
# not players, detail scrapers, or download providers.
FEEDS = (
    ('faleno', 'censored', 'latest', 'https://faleno.jp/top/', '片商新作 · 配信日期'),
    ('faleno', 'censored', 'hot', 'https://faleno.jp/top/', '品牌站内排名 · 周期未公布'),
    ('dahlia', 'censored', 'latest', 'https://dahlia-av.jp/', '片商新作 · 配信日期'),
    ('dahlia', 'censored', 'hot', 'https://dahlia-av.jp/', '品牌站内排名 · 周期未公布'),
    ('freejavbt', 'censored', 'latest', 'https://freejavbt.com/ja/censored', '来源最新列表 · 页面日期'),
    ('freejavbt', 'uncensored', 'latest', 'https://freejavbt.com/ja/uncensored', '来源最新列表 · 页面日期'),
    ('freejavbt', 'censored', 'hot', 'https://freejavbt.com/ja/rank/censored/day', '站内日榜 · 算法未公布'),
    ('freejavbt', 'uncensored', 'hot', 'https://freejavbt.com/ja/rank/uncensored/day', '站内日榜 · 算法未公布'),
)
