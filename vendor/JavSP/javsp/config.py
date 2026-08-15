import re
from argparse import ArgumentParser, RawTextHelpFormatter
from enum import Enum
from typing import Dict, List, Literal, TypeAlias, Union
from confz import BaseConfig, CLArgSource, EnvSource, FileSource
from pydantic import ByteSize, Field, NonNegativeInt, PositiveInt, model_validator
from pydantic_extra_types.pendulum_dt import Duration
from pydantic_core import Url
from pathlib import Path

from javsp.lib import resource_path


class MediaType(BaseConfig):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    name: str = Field(min_length=1, max_length=80)
    priority: int = 0
    identifier_kind: Literal["dvdid", "cid"] = "dvdid"
    pattern: str = ""
    avid_format: str = "{avid}"
    fallback: bool = False

    @model_validator(mode="after")
    def validate_pattern(self):
        if self.fallback:
            return self
        if not self.pattern and not (self.id == "cid" and self.identifier_kind == "cid"):
            raise ValueError("影片分类必须配置识别规则，只有兜底分类可以留空")
        if not self.pattern:
            return self
        if "(?P<avid>" not in self.pattern:
            raise ValueError("影片分类识别规则必须包含命名捕获组 (?P<avid>...)")
        if "{avid}" not in self.avid_format:
            raise ValueError("影片分类的番号格式必须包含 {avid}")
        try:
            re.compile(self.pattern)
        except re.error as exc:
            raise ValueError(f"影片分类识别规则无效: {exc}") from exc
        return self


def default_media_types() -> list[MediaType]:
    return [
        MediaType(id="fc2", name="FC2", priority=100, pattern=r"FC2[^A-Z\d]{0,5}(?:PPV[^A-Z\d]{0,5})?(?P<avid>\d{5,7})", avid_format="FC2-{avid}"),
        MediaType(id="getchu", name="Getchu", priority=90, pattern=r"GETCHU[-_]*(?P<avid>\d+)", avid_format="GETCHU-{avid}"),
        MediaType(id="gyutto", name="Gyutto", priority=90, pattern=r"GYUTTO[-_]*(?P<avid>\d+)", avid_format="GYUTTO-{avid}"),
        MediaType(id="cid", name="CID", priority=80, identifier_kind="cid"),
        MediaType(id="normal", name="普通影片", priority=0, fallback=True),
    ]

class Scanner(BaseConfig):
    ignored_id_pattern: List[str]
    input_directory: Path | None = None
    filename_extensions: List[str]
    ignored_folder_name_pattern: List[str]
    minimum_size: ByteSize
    skip_nfo_dir: bool
    manual: bool
    media_types: List[MediaType] = Field(default_factory=default_media_types)

    @model_validator(mode="after")
    def validate_media_types(self):
        ids = [item.id for item in self.media_types]
        if len(ids) != len(set(ids)):
            raise ValueError("影片分类 ID 不能重复")
        if sum(item.fallback for item in self.media_types) != 1:
            raise ValueError("必须且只能保留一个兜底影片分类")
        return self

class CrawlerID(str, Enum):
    airav = 'airav'
    avsox = 'avsox'
    avwiki = 'avwiki'
    dl_getchu = 'dl_getchu'
    fanza = 'fanza'
    fc2 = 'fc2'
    fc2fan = 'fc2fan'
    fc2ppvdb = 'fc2ppvdb'
    gyutto = 'gyutto'
    jav321 = 'jav321'
    javbus = 'javbus'
    javdb = 'javdb'
    javlib = 'javlib'
    javmenu = 'javmenu'
    mgstage = 'mgstage'
    njav = 'njav'
    prestige = 'prestige'
    arzon = 'arzon'
    arzon_iv = 'arzon_iv'

class Network(BaseConfig):
    proxy_server: Url | None
    retry: NonNegativeInt = 3
    timeout: Duration
    proxy_free: Dict[CrawlerID, Url]

class CrawlerSelect(BaseConfig):
    def items(self) -> List[tuple[str, list[str]]]:
        return [
            ('normal', self.normal),
            ('fc2', self.fc2),
            ('cid', self.cid),
            ('getchu', self.getchu),
            ('gyutto', self.gyutto),
        ]

    def __getitem__(self, index) -> list[str]:
        match index:
            case 'normal':
                return self.normal
            case 'fc2':
                return self.fc2
            case 'cid':
                return self.cid
            case 'getchu':
                return self.getchu
            case 'gyutto':
                return self.gyutto
        raise Exception("Unknown crawler type")

    normal: list[str]
    fc2: list[str]
    cid: list[str]
    getchu: list[str]
    gyutto: list[str]

class MovieInfoField(str, Enum):
    dvdid = 'dvdid'
    cid = 'cid'
    url = 'url'
    plot = 'plot'
    cover = 'cover'
    big_cover = 'big_cover'
    genre = 'genre'
    genre_id = 'genre_id'
    genre_norm = 'genre_norm'
    score = 'score'
    title = 'title'
    ori_title = 'ori_title'
    magnet = 'magnet'
    serial = 'serial'
    actress = 'actress'
    actress_pics = 'actress_pics'
    director = 'director'
    duration = 'duration'
    producer = 'producer'
    publisher = 'publisher'
    uncensored = 'uncensored'
    publish_date = 'publish_date'
    preview_pics = 'preview_pics'
    preview_video = 'preview_video'

class UseJavDBCover(str, Enum):
    yes = "yes"
    no = "no"
    fallback = "fallback"

class Crawler(BaseConfig):
    selection: Dict[str, List[str]]
    required_keys: list[MovieInfoField]
    hardworking: bool
    respect_site_avid: bool
    fc2fan_local_path: Path | None
    sleep_after_scraping: Duration
    use_javdb_cover: UseJavDBCover
    normalize_actress_name: bool

class MovieDefault(BaseConfig):
    title: str
    actress: str
    series: str
    director: str
    producer: str
    publisher: str

class PathSummarize(BaseConfig):
    output_folder_pattern: str
    basename_pattern: str
    length_maximum: PositiveInt
    length_by_byte: bool
    max_actress_count: PositiveInt = 10
    hard_link: bool

class TitleSummarize(BaseConfig):
    remove_trailing_actor_name: bool

class NFOSummarize(BaseConfig):
    basename_pattern: str
    title_pattern: str
    custom_genres_fields: list[str]
    custom_tags_fields: list[str]

class ExtraFanartSummarize(BaseConfig):
    enabled: bool
    scrap_interval: Duration

class SlimefaceEngine(BaseConfig):
    name: Literal['slimeface']

class CoverCrop(BaseConfig):
  engine: SlimefaceEngine | None
  on_id_pattern: list[str]

class CoverSummarize(BaseConfig):
    basename_pattern: str
    highres: bool
    google_search_fallback: bool = False
    add_label: bool
    crop: CoverCrop

class FanartSummarize(BaseConfig):
    basename_pattern: str

class Summarizer(BaseConfig):
    default: MovieDefault
    censor_options_representation: list[str]
    title: TitleSummarize
    move_files: bool = True
    path: PathSummarize
    nfo: NFOSummarize
    cover: CoverSummarize
    fanart: FanartSummarize
    extra_fanarts: ExtraFanartSummarize

class BaiduTranslateEngine(BaseConfig):
    name: Literal['baidu']
    app_id: str
    api_key: str

class BingTranslateEngine(BaseConfig):
    name: Literal['bing']
    api_key: str

class ClaudeTranslateEngine(BaseConfig):
    name: Literal['claude']
    api_key: str

class OpenAITranslateEngine(BaseConfig):
    name: Literal['openai']
    url: Url
    api_key: str
    model: str

class GoogleTranslateEngine(BaseConfig):
    name: Literal['google']

TranslateEngine: TypeAlias = Union[
        BaiduTranslateEngine,
        BingTranslateEngine,
        ClaudeTranslateEngine,
        OpenAITranslateEngine,
        GoogleTranslateEngine,
        None]

class TranslateField(BaseConfig):
    title: bool
    plot: bool

class Translator(BaseConfig):
    engine: TranslateEngine = Field(..., discriminator='name')
    fields: TranslateField

class Other(BaseConfig):
    interactive: bool
    check_update: bool
    auto_update: bool

def get_config_source():
    parser = ArgumentParser(prog='JavSP', description='汇总多站点数据的AV元数据刮削器', formatter_class=RawTextHelpFormatter)
    parser.add_argument('-c', '--config', help='使用指定的配置文件')
    args, _ = parser.parse_known_args()
    sources = []
    if args.config is None:
        args.config = resource_path('config.yml')
    sources.append(FileSource(file=args.config))
    sources.append(EnvSource(prefix='JAVSP_', allow_all=True))
    sources.append(CLArgSource(prefix='o'))
    return sources

class Cfg(BaseConfig):
    scanner: Scanner
    network: Network
    crawler: Crawler
    summarizer: Summarizer
    translator: Translator
    other: Other
    CONFIG_SOURCES=get_config_source()

    @model_validator(mode="after")
    def validate_crawler_categories(self):
        category_ids = {item.id for item in self.scanner.media_types}
        selected_ids = set(self.crawler.selection)
        missing = category_ids - selected_ids
        unknown = selected_ids - category_ids
        if missing:
            raise ValueError("下列影片分类尚未配置爬虫: " + ", ".join(sorted(missing)))
        if unknown:
            raise ValueError("爬虫配置引用了不存在的影片分类: " + ", ".join(sorted(unknown)))
        return self
