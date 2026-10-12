from __future__ import annotations

import sys
from typing import Any

import yaml

from .storage import VENDOR_DIR, read_config


_FIELD_LABELS = {
    "scanner": "扫描器", "network": "网络", "crawler": "爬虫", "summarizer": "整理", "translator": "翻译器", "other": "其他设置",
    "ignored_id_pattern": "番号识别忽略规则", "input_directory": "扫描目录", "input_files": "输入文件", "filename_extensions": "视频文件扩展名",
    "ignored_folder_name_pattern": "忽略目录规则", "minimum_size": "最小文件大小", "strm_ignore_minimum_size": "STRM 忽略最小文件大小",
    "only_match_media_types": "仅扫描匹配影片分类", "skip_nfo_dir": "跳过已有 NFO 的目录", "manual": "手动确认", "media_types": "影片分类",
    "id": "分类 ID", "name": "名称", "priority": "优先级", "detector": "识别方式", "identifier_kind": "编号类型",
    "pattern": "文件名识别规则", "avid_format": "番号格式", "fallback": "兜底分类",
    "proxy_server": "代理服务器", "proxy_free": "免代理站点", "retry": "重试次数", "timeout": "请求超时",
    "ai_enabled": "启用 AI", "ai_fallback_only": "仅刮削失败时使用 AI", "selection": "爬虫列表", "required_keys": "抓取成功必需字段",
    "hardworking": "深度抓取", "respect_site_avid": "使用网站返回的番号", "fc2fan_local_path": "FC2Fan 本地目录",
    "sleep_after_scraping": "每部影片刮削后等待时间", "use_javdb_cover": "JavDB 封面策略", "normalize_actress_name": "统一演员艺名",
    "move_files": "移动文件到整理目录", "existing_file_policy": "已有影片覆盖方式", "path": "文件路径", "output_folder_pattern": "整理输出目录模板", "basename_pattern": "文件名模板",
    "length_maximum": "最大文件路径长度", "length_by_byte": "按字节计算长度", "max_actress_count": "最多包含的演员人数", "hard_link": "使用硬链接",
    "title": "标题", "remove_trailing_actor_name": "移除标题末尾演员名", "default": "缺失信息替代文本", "actress": "演员",
    "series": "系列", "director": "导演", "producer": "制作商", "publisher": "发行商", "nfo": "NFO 文件",
    "title_pattern": "标题模板", "custom_genres_fields": "自定义分类字段", "custom_tags_fields": "自定义标签字段", "censor_options_representation": "码状态显示文本",
    "cover": "封面", "fanart": "横版封面", "extra_fanarts": "剧照", "enabled": "是否启用", "scrap_interval": "请求间隔",
    "highres": "优先下载高清封面", "google_search_fallback": "Google 搜索封面兜底", "add_label": "添加水印标签", "crop": "封面裁剪", "on_id_pattern": "启用裁剪的番号规则",
    "engine": "引擎配置", "fields": "翻译字段", "plot": "剧情简介", "app_id": "应用 ID", "api_key": "API 密钥", "url": "接口地址", "model": "模型名称",
    "interactive": "终端交互", "check_update": "检查更新", "auto_update": "自动下载更新",
    "openai": "OpenAI", "claude": "Claude", "google": "Google", "bing": "必应", "baidu": "百度", "slimeface": "Slimeface",
    "normal": "普通影片", "fc2": "FC2", "getchu": "Getchu", "gyutto": "Gyutto", "cid": "CID",
    "airav": "AirAV", "avsox": "Avsox", "avwiki": "AVWiki", "dl_getchu": "DL Getchu", "fanza": "FANZA",
    "fc2fan": "FC2Fan", "fc2ppvdb": "FC2PPVDB", "jav321": "Jav321", "javbus": "JavBus", "javdb": "JavDB",
    "javlib": "JavLibrary", "javmenu": "JavMenu", "mgstage": "MGStage", "njav": "NJav", "prestige": "Prestige", "arzon": "Arzon", "arzon_iv": "Arzon IV",
    "[key]": "配置项名称",
}
_TYPE_MESSAGES = {
    "missing": "此项不能为空", "extra_forbidden": "此配置项不受支持，请检查名称",
    "list_type": "请填写列表，例如 [第一项, 第二项]", "tuple_type": "请填写列表", "set_type": "请填写列表",
    "dict_type": "请按“配置项: 内容”的形式填写此组设置", "model_type": "请按“配置项: 内容”的形式填写此组设置",
    "model_attributes_type": "请按“配置项: 内容”的形式填写此组设置",
    "string_type": "请输入文本", "string_unicode": "文本编码无效，请使用 UTF-8 保存配置文件",
    "int_type": "请输入整数", "int_parsing": "请输入整数", "int_from_float": "请输入整数，不能包含小数",
    "float_type": "请输入数字", "float_parsing": "请输入数字", "finite_number": "请输入有限的数字",
    "bool_type": "请选择是或否；配置文件中填写 true 或 false", "bool_parsing": "请选择是或否；配置文件中填写 true 或 false",
    "literal_error": "请选择支持的选项", "enum": "请选择支持的选项",
    "union_tag_invalid": "不支持此引擎，请选择列表中的引擎", "union_tag_not_found": "请先选择引擎，或填写引擎的 name 配置项",
    "url_parsing": "请输入完整的网址，例如 https://example.com", "url_type": "请输入完整的网址，例如 https://example.com",
    "url_scheme": "网址协议不受支持，请检查地址开头",
    "byte_size": "请填写文件大小，例如 232MiB 或 1GB", "byte_size_unit": "文件大小单位无效，例如可填写 232MiB 或 1GB",
    "path_type": "请填写文件或文件夹路径", "path_not_directory": "请选择已有的文件夹", "path_not_file": "请选择已有的文件",
}
_MEDIA_RULE_MESSAGES = {
    "兜底分类必须使用 fallback 识别方式", "CID 识别方式只能用于 CID 编号", "正则识别方式必须配置文件名识别规则",
    "影片分类识别规则必须包含命名捕获组 (?P<avid>...)", "影片分类的番号格式必须包含 {avid}",
    "影片分类 ID 不能重复", "必须且只能保留一个兜底影片分类",
}


def _validation_message(error: dict) -> str:
    kind = error.get("type", "")
    location = error.get("loc", ())
    if kind.startswith("url_") and "proxy_server" in location:
        return "请输入完整的网址，例如 http://127.0.0.1:7890 或 socks5://127.0.0.1:7890"
    if kind == "string_pattern_mismatch" and "media_types" in location and location[-1:] == ("id",):
        return "请以小写字母开头，只使用小写字母、数字和下划线，最多 40 个字符"
    bounds = {
        "greater_than": ("gt", "请输入大于 {} 的数字"), "greater_than_equal": ("ge", "请输入不小于 {} 的数字"),
        "less_than": ("lt", "请输入小于 {} 的数字"), "less_than_equal": ("le", "请输入不大于 {} 的数字"),
        "multiple_of": ("multiple_of", "请输入 {} 的整数倍"),
        "string_too_short": ("min_length", "至少填写 {} 个字符"), "string_too_long": ("max_length", "最多填写 {} 个字符"),
        "too_short": ("min_length", "至少填写 {} 项"), "too_long": ("max_length", "最多填写 {} 项"),
    }
    if kind in bounds:
        key, template = bounds[kind]
        limit = error.get("ctx", {}).get(key)
        if isinstance(limit, (int, float)) and not isinstance(limit, bool):
            return template.format(limit)
    if kind in {"timedelta_type", "timedelta_parsing"} or (kind == "value_error" and any(key in location for key in ("timeout", "sleep_after_scraping", "scrap_interval"))):
        return "请填写有效时长，例如 PT10S 表示 10 秒、PT1M 表示 1 分钟"
    if kind == "value_error":
        # Only preserve known, fixed model messages. Other validation messages
        # can contain the submitted value (including credentials).
        message = str(error.get("msg", "")).removeprefix("Value error, ")
        if message in _MEDIA_RULE_MESSAGES:
            return message
        if "media_types" in location:
            return "影片分类规则无效，请检查文件名识别规则和番号格式"
    return _TYPE_MESSAGES.get(kind, "填写内容不符合要求，请检查此项的格式和取值")


def format_validation_errors(errors: list[dict], field_labels: dict[str, str] | None = None) -> str:
    """Describe validation failures without including submitted values."""
    labels = _FIELD_LABELS | (field_labels or {})
    details = []
    for error in errors:
        parts = [f"第 {part + 1} 项" if isinstance(part, int) else labels.get(part, "自定义配置项")
                 for part in error.get("loc", ())]
        location = " / ".join(parts) or "配置"
        details.append(f"{location}：{_validation_message(error)}")
    return "; ".join(details)


def yaml_error_message(error: yaml.YAMLError, section: str | None = None) -> str:
    """Use parser coordinates, never the exception's source excerpt."""
    prefix = f"{_FIELD_LABELS.get(section, '配置分组')}的 " if section is not None else ""
    mark = getattr(error, "problem_mark", None) or getattr(error, "context_mark", None)
    location = f"（第 {mark.line + 1} 行，第 {mark.column + 1} 列）" if mark is not None else ""
    return f"{prefix}YAML 格式错误{location}，请检查缩进、冒号、括号和特殊字符。"


def _merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def load_base_config() -> dict:
    defaults = {}
    try:
        defaults = yaml.safe_load((VENDOR_DIR / "config.yml").read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        pass
    try:
        local = yaml.safe_load(read_config()) or {}
    except yaml.YAMLError:
        local = {}
    return _merge(defaults if isinstance(defaults, dict) else {}, local if isinstance(local, dict) else {})


def validate_config_data(data: Any) -> None:
    """Validate a merged JavSP config with the embedded project's own model."""
    if not isinstance(data, dict):
        raise ValueError("配置文件最外层应按“配置项: 内容”填写，不能填写列表或单个值")
    vendor_path = str(VENDOR_DIR)
    if vendor_path not in sys.path:
        sys.path.insert(0, vendor_path)
    try:
        from javsp.config import Cfg
        from pydantic import ValidationError

        Cfg.model_validate(data)
    except ValidationError as exc:
        details = format_validation_errors(exc.errors(include_input=False, include_url=False))
        raise ValueError("配置校验失败: " + details) from exc
    except (ImportError, ModuleNotFoundError) as exc:
        raise ValueError(f"无法加载 JavSP 配置模型: {exc}") from exc
