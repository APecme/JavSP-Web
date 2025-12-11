import os
import re
import sys
import json
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
from pydantic import ValidationError
from pydantic_extra_types.pendulum_dt import Duration
import requests
import threading
import importlib
from datetime import datetime
from typing import Dict, List

sys.stdout.reconfigure(encoding='utf-8')

import colorama
import pretty_errors
from colorama import Fore, Style
from tqdm import tqdm


pretty_errors.configure(display_link=True)


from javsp.print import TqdmOut
from javsp.cropper import Cropper, get_cropper

# 将StreamHandler的stream修改为TqdmOut，以与Tqdm协同工作，并统一增加时间戳格式
root_logger = logging.getLogger()
for handler in root_logger.handlers:
    if type(handler) == logging.StreamHandler:
        handler.stream = TqdmOut
        if handler.formatter is None:
            handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))

logger = logging.getLogger('main')


from javsp.lib import resource_path
from javsp.nfo import write_nfo
from javsp.file import *
from javsp.func import *
from javsp.image import *
from javsp.datatype import Movie, MovieInfo
from javsp.web.base import download
from javsp.web.exceptions import *
from javsp.web.translate import translate_movie_info
from javsp.web.exceptions import MovieNotFoundError, MovieDuplicateError, SiteBlocked, SitePermissionError, CredentialError

from javsp.config import Cfg, CrawlerID
from javsp.prompt import prompt

actressAliasMap = {}


def _now_iso() -> str:
    """返回当前时间的 ISO 字符串，供结构化事件使用。"""
    try:
        # 使用 timezone-aware 的 datetime 替代已弃用的 utcnow()
        from datetime import timezone
        return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
    except Exception:
        return ''


def emit_event(kind: str, payload: Dict) -> None:
    """输出统一的结构化进度事件，供 Web 端解析。

    事件格式：
      JAVSP_EVENT {"type":"progress","kind":"movie|step|task", ...}
    """
    try:
        data = {"type": "progress", "kind": kind}
        data.update(payload)
        # 附加时间戳，便于前端在需要时展示事件时间线
        if "ts" not in data:
            data["ts"] = _now_iso()
        # 使用 tqdm.write 确保输出换行，避免与进度条混在一起
        try:
            from tqdm import tqdm
            tqdm.write("JAVSP_EVENT " + json.dumps(data, ensure_ascii=False), end='\n')
        except:
            print("JAVSP_EVENT " + json.dumps(data, ensure_ascii=False), flush=True)
    except Exception:
        logger.debug("emit_event failed", exc_info=True)


def emit_movie_event(index: int, total: int, movie: Movie) -> None:
    """输出当前影片的结构化信息，用于在 Web 端建立影片进度行。"""
    try:
        dvdid = getattr(movie, 'dvdid', None) or None
        cid = getattr(movie, 'cid', None) or None
        files = getattr(movie, 'files', []) or []
        first_file = files[0] if files else None
        payload = {
            "index": index,
            "total": total,
            "dvdid": dvdid,
            "cid": cid,
            "file": first_file,
        }
        # 使用 tqdm.write 确保输出换行，避免与进度条混在一起
        try:
            from tqdm import tqdm
            tqdm.write("JAVSP_MOVIE " + json.dumps(payload, ensure_ascii=False), end='\n')
        except:
            print("JAVSP_MOVIE " + json.dumps(payload, ensure_ascii=False), flush=True)
    except Exception:
        logger.debug("emit_movie_event failed", exc_info=True)


def resolve_alias(name):
    """将别名解析为固定的名字"""
    for fixedName, aliases in actressAliasMap.items():
        if name in aliases:
            return fixedName
    return name  # 如果找不到别名对应的固定名字，则返回原名


def import_crawlers():
    """按配置文件的抓取器顺序将该字段转换为抓取器的函数列表"""
    unknown_mods = []
    for _, mods in Cfg().crawler.selection.items():
        valid_mods = []
        for name in mods:
            try:
                # 导入fc2fan抓取器的前提: 配置了fc2fan的本地路径
                # if name == 'fc2fan' and (not os.path.isdir(Cfg().Crawler.fc2fan_local_path)):
                #     logger.debug('由于未配置有效的fc2fan路径，已跳过该抓取器')
                #     continue
                import_name = 'javsp.web.' + name
                __import__(import_name)
                valid_mods.append(import_name)  # 抓取器有效: 使用完整模块路径，便于程序实际使用
            except ModuleNotFoundError:
                unknown_mods.append(name)       # 抓取器无效: 仅使用模块名，便于显示
    if unknown_mods:
        logger.warning('配置的抓取器无效: ' + ', '.join(unknown_mods))


# 爬虫是IO密集型任务，可以通过多线程提升效率
def parallel_crawler(movie: Movie, tqdm_bar=None):
    """使用多线程抓取不同网站的数据"""
    def wrapper(parser, info: MovieInfo, retry):
        """对抓取器函数进行包装，便于更新提示信息和自动重试"""
        crawler_name = threading.current_thread().name
        crawler_short_name = crawler_name.replace('javsp.web.', '') if crawler_name.startswith('javsp.web.') else crawler_name
        # task_info = f'Crawler: {crawler_name}: {info.dvdid}'
        last_error = None
        for cnt in range(retry):
            try:
                parser(info)
                # 成功后设置标记
                setattr(info, 'success', True)
                logger.info(f'[{crawler_short_name}] 抓取成功')
                
                # 成功时不更新描述，以免覆盖掉其他线程正在显示的错误信息，或者只显示简短的成功
                # if isinstance(tqdm_bar, tqdm):
                #     tqdm_bar.set_description(f'{crawler_name}: 抓取成功')
                break
            except MovieNotFoundError as e:
                # 这种是正常业务流程，不是错误
                logger.info(f'[{crawler_short_name}] 未找到影片: {e}')
                last_error = f'未找到影片'
                logger.debug(e)
                break
            except MovieDuplicateError as e:
                logger.info(f'[{crawler_short_name}] 影片重复: {e}')
                last_error = f'影片重复'
                logger.debug(e)
                break
            except (SiteBlocked, SitePermissionError, CredentialError) as e:
                # 站点屏蔽/权限错误：更新进度条提示
                logger.info(f'[{crawler_short_name}] 访问被拒/需登录: {e}')
                last_error = f'访问被拒/需登录'
                if isinstance(tqdm_bar, tqdm):
                    tqdm_bar.set_description(f'{crawler_name}: 访问被拒/需登录')
                logger.debug(e)
                break
            except requests.exceptions.RequestException as e:
                # 网络错误：仅更新进度条，不打印 Traceback
                # 提取完整的错误信息，包括URL
                error_str = str(e)
                # 如果错误信息包含URL，保留完整URL
                if 'for url:' in error_str:
                    # 提取URL部分
                    url_part = error_str.split('for url:')[-1].strip()
                    last_error = f'网络错误: {error_str.split("for url:")[0].strip()} for url: {url_part}'
                else:
                    last_error = f'网络错误: {error_str}'
                logger.info(f'[{crawler_short_name}] 网络错误 ({cnt+1}/{retry}): {e}')
                if isinstance(tqdm_bar, tqdm):
                    tqdm_bar.set_description(f'{crawler_name}: 网络错误, 重试中 ({cnt+1}/{retry})')
                logger.debug(f'{crawler_name}: 网络错误: {e}')
            except Exception as e:
                # 其他严重错误 (如 WebsiteError, 页面结构异常)：
                # 1. 提取错误信息，保留完整信息用于日志
                err_msg = str(e)
                # 对于包含URL的错误，保留完整URL
                if 'for url:' in err_msg.lower() or 'url:' in err_msg.lower():
                    # 保留完整的错误信息，包括URL
                    last_error = err_msg
                elif '页面结构异常' in err_msg:
                    last_error = '页面结构异常'
                elif '反爬机制' in err_msg:
                    last_error = '触发反爬'
                else:
                    # 保留完整错误信息，不截断
                    last_error = err_msg
                
                # 日志中输出完整错误信息
                logger.info(f'[{crawler_short_name}] 发生异常 ({cnt+1}/{retry}): {err_msg}')
                
                # 2. 更新进度条描述（使用简短版本）
                if isinstance(tqdm_bar, tqdm):
                    display_msg = err_msg
                    if len(display_msg) > 30:
                        display_msg = display_msg[:27] + '...'
                    tqdm_bar.set_description(f'{crawler_name}: {display_msg} ({cnt+1}/{retry})')
                
                # 3. 详细堆栈只进 Debug 日志，不输出到控制台
                logger.debug(f'{crawler_name}: 发生异常: {e}', exc_info=True)
                # 注意：这里去掉了 logger.exception(e)，所以不会再刷屏 Traceback 了
        
        # 如果所有重试都失败，记录最终错误
        if not hasattr(info, 'success') and last_error:
            setattr(info, 'crawler_error', last_error)
            logger.warning(f'[{crawler_short_name}] 抓取失败: {last_error}')

    # 根据影片的数据源获取对应的抓取器
    crawler_mods: List[CrawlerID] = Cfg().crawler.selection[movie.data_src]

    all_info = {i.value: MovieInfo(movie) for i in crawler_mods}
    # 番号为cid但同时也有有效的dvdid时，也尝试使用普通模式进行抓取
    if movie.data_src == 'cid' and movie.dvdid:
        crawler_mods = crawler_mods + Cfg().crawler.selection.normal
        for i in all_info.values():
            i.dvdid = None
        for i in Cfg().crawler.selection.normal:
            all_info[i.value] = MovieInfo(movie.dvdid)
    thread_pool = []
    for mod_partial, info in all_info.items():
        mod = f"javsp.web.{mod_partial}"
        try:
            module = sys.modules.get(mod)
            if module is None:
                module = importlib.import_module(mod)
        except ModuleNotFoundError:
            logger.warning(f"抓取器模块未找到，已跳过: {mod}")
            continue

        parser = getattr(module, 'parse_data', None)
        if parser is None:
            logger.warning(f"抓取器模块缺少 parse_data，已跳过: {mod}")
            continue

        # 将all_info中的info实例传递给parser，parser抓取完成后，info实例的值已经完成更新
        # TODO: 抓取器如果带有parse_data_raw，说明它已经自行进行了重试处理，此时将重试次数设置为1
        retry_times = 1 if hasattr(module, 'parse_data_raw') else Cfg().network.retry
        th = threading.Thread(target=wrapper, name=mod, args=(parser, info, retry_times))
        th.start()
        thread_pool.append(th)
    # 等待所有线程结束
    timeout = Cfg().network.retry * Cfg().network.timeout.total_seconds()
    for th in thread_pool:
        th: threading.Thread
        th.join(timeout=timeout)
    # 根据抓取结果更新影片类型判定
    if movie.data_src == 'cid' and movie.dvdid:
        titles = [all_info[i].title for i in Cfg().crawler.selection[movie.data_src]]
        if any(titles):
            movie.dvdid = None
            all_info = {k: v for k, v in all_info.items() if k in Cfg().crawler.selection['cid']}
        else:
            logger.debug(f'自动更正影片数据源类型: {movie.dvdid} ({movie.cid}): normal')
            movie.data_src = 'normal'
            movie.cid = None
            all_info = {k: v for k, v in all_info.items() if k not in Cfg().crawler.selection['cid']}
    # 记录所有尝试的爬虫及其结果（在删除失败数据之前记录）
    attempted_crawlers = []
    failed_crawlers = []
    successful_crawlers = []
    for mod_partial, info in all_info.items():
        crawler_short_name = mod_partial
        attempted_crawlers.append(crawler_short_name)
        if hasattr(info, 'success'):
            if not hasattr(info, 'crawler_error'):
                successful_crawlers.append(crawler_short_name)
                logger.info(f'[{crawler_short_name}] 抓取成功')
        else:
            error_msg = getattr(info, 'crawler_error', '未知错误')
            failed_crawlers.append(f'{crawler_short_name}({error_msg})')
            logger.warning(f'[{crawler_short_name}] 抓取失败: {error_msg}')
    
    # 输出所有爬虫的执行结果汇总
    if successful_crawlers:
        logger.info(f'成功抓取的爬虫 ({len(successful_crawlers)}/{len(attempted_crawlers)}): {", ".join(successful_crawlers)}')
    if failed_crawlers:
        logger.info(f'失败的爬虫 ({len(failed_crawlers)}/{len(attempted_crawlers)}): {", ".join([f"{c}" for c in failed_crawlers])}')
    
    # 删除抓取失败的站点对应的数据
    all_info = {k:v for k,v in all_info.items() if hasattr(v, 'success')}
    # 记录成功使用的爬虫名称（从 all_info 的键中提取，因为键名是 'javsp.web.xxx'）
    used_crawlers = []
    for key in all_info.keys():
        if key.startswith('javsp.web.'):
            crawler_name = key.replace('javsp.web.', '')
            if crawler_name and crawler_name not in used_crawlers:
                used_crawlers.append(crawler_name)
    # 删除all_info中键名中的'web.'
    all_info = {k[4:]:v for k,v in all_info.items()}
    # 如果没有获取到，从 all_info 的键中提取（此时键名已经是 'xxx' 格式）
    if not used_crawlers:
        used_crawlers = list(all_info.keys())
    # 输出使用的爬虫信息到日志
    if used_crawlers:
        logger.info(f'使用的爬虫: {", ".join(used_crawlers)}')
    elif attempted_crawlers:
        # 如果所有爬虫都失败，输出详细信息
        logger.error(f'所有配置的{len(attempted_crawlers)}个抓取器均未获取到影片信息')
        logger.error(f'尝试的抓取器: {", ".join(attempted_crawlers)}')
        if failed_crawlers:
            logger.error(f'失败详情: {"; ".join(failed_crawlers)}')
    # 将爬虫信息附加到返回的字典中（临时存储）
    all_info['_used_crawlers'] = used_crawlers
    all_info['_attempted_crawlers'] = attempted_crawlers
    all_info['_failed_crawlers'] = failed_crawlers
    return all_info


def info_summary(movie: Movie, all_info: Dict[str, MovieInfo]):
    """汇总多个来源的在线数据生成最终数据"""
    final_info = MovieInfo(movie)
    ########## 部分字段配置了专门的选取逻辑，先处理这些字段 ##########
    # genre
    if 'javdb' in all_info and all_info['javdb'].genre:
        final_info.genre = all_info['javdb'].genre

    ########## 移除所有抓取器数据中，标题尾部的女优名 ##########
    if Cfg().summarizer.title.remove_trailing_actor_name:
        for name, data in all_info.items():
            # 确保标题为字符串，若爬虫返回列表则取第一个元素
            title_val = data.title
            if isinstance(title_val, list) and title_val:
                title_val = title_val[0]
            data.title = remove_trail_actor_in_title(title_val, data.actress)
    ########## 然后检查所有字段，如果某个字段还是默认值，则按照优先级选取数据 ##########
    # parser直接更新了all_info中的项目，而初始all_info是按照优先级生成的，已经符合配置的优先级顺序了
    # 按照优先级取出各个爬虫获取到的信息
    attrs = [i for i in dir(final_info) if not i.startswith('_')]
    covers, big_covers = [], []
    for name, data in all_info.items():
        absorbed = []
        # 遍历所有属性，如果某一属性当前值为空而爬取的数据中含有该属性，则采用爬虫的属性
        for attr in attrs:
            incoming = getattr(data, attr)
            current = getattr(final_info, attr)
            if attr == 'cover':
                if incoming and (incoming not in covers):
                    covers.append(incoming)
                    absorbed.append(attr)
            elif attr == 'big_cover':
                if incoming and (incoming not in big_covers):
                    big_covers.append(incoming)
                    absorbed.append(attr)
            elif attr == 'uncensored':
                if (current is None) and (incoming is not None):
                    setattr(final_info, attr, incoming)
                    absorbed.append(attr)
            else:
                if (not current) and (incoming):
                    setattr(final_info, attr, incoming)
                    absorbed.append(attr)
        if absorbed:
            logger.debug(f"从'{name}'中获取了字段: " + ' '.join(absorbed))
    # 使用网站的番号作为番号
    if Cfg().crawler.respect_site_avid:
        id_weight = {}
        for name, data in all_info.items():
            if data.title:
                if movie.dvdid:
                    id_weight.setdefault(data.dvdid, []).append(name)
                else:
                    id_weight.setdefault(data.cid, []).append(name)
        # 根据权重选择最终番号
        if id_weight:
            id_weight = {k:v for k, v in sorted(id_weight.items(), key=lambda x:len(x[1]), reverse=True)}
            final_id = list(id_weight.keys())[0]
            if movie.dvdid:
                final_info.dvdid = final_id
            else:
                final_info.cid = final_id
    # javdb封面有水印，优先采用其他站点的封面
    javdb_cover = getattr(all_info.get('javdb'), 'cover', None)
    if javdb_cover is not None:
        match Cfg().crawler.use_javdb_cover:
            case UseJavDBCover.fallback:
                covers.remove(javdb_cover)
                covers.append(javdb_cover)
            case UseJavDBCover.no:
                covers.remove(javdb_cover)

    setattr(final_info, 'covers', covers)
    setattr(final_info, 'big_covers', big_covers)
    # 对cover和big_cover赋值，避免后续检查必须字段时出错
    if covers:
        final_info.cover = covers[0]
    if big_covers:
        final_info.big_cover = big_covers[0]
    ########## 部分字段放在最后进行检查 ##########
    # 特殊的 genre
    if final_info.genre is None:
        final_info.genre = []
    if movie.hard_sub:
        final_info.genre.append('内嵌字幕')
    if movie.uncensored:
        final_info.genre.append('无码流出/破解')

    # 女优别名固定
    if Cfg().crawler.normalize_actress_name and bool(final_info.actress_pics):
        final_info.actress = [resolve_alias(i) for i in final_info.actress]
        if final_info.actress_pics:
            final_info.actress_pics = {
                resolve_alias(key): value for key, value in final_info.actress_pics.items()
            }

    # 检查是否所有必需的字段都已经获得了值
    for attr in Cfg().crawler.required_keys:
        if not getattr(final_info, attr, None):
            logger.error(f"所有抓取器均未获取到字段: '{attr}'，抓取失败")
            return False
    # 必需字段均已获得了值：将最终的数据附加到movie
    movie.info = final_info
    return True

def generate_names(movie: Movie):
    """按照模板生成相关文件的文件名"""

    def legalize_path(path: str):
        """
            Windows下文件名中不能包含换行 #467
            所以这里对文件路径进行合法化
        """
        return ''.join(c for c in path if c not in {'\n'})

    info = movie.info
    # 准备用来填充命名模板的字典
    d = info.get_info_dic()

    if info.actress and len(info.actress) > Cfg().summarizer.path.max_actress_count:
        logging.debug('女优人数过多，按配置保留了其中的前n个: ' + ','.join(info.actress))
        actress = info.actress[:Cfg().summarizer.path.max_actress_count] + ['…']
    else:
        actress = info.actress
    d['actress'] = ','.join(actress) if actress else Cfg().summarizer.default.actress

    # 保存label供后面判断裁剪图片的方式使用
    setattr(info, 'label', d['label'].upper())
    # 处理字段：替换不能作为文件名的字符，移除首尾的空字符
    for k, v in d.items():
        d[k] = replace_illegal_chars(v.strip())

    # 生成nfo文件中的影片标题
    nfo_title = Cfg().summarizer.nfo.title_pattern.format(**d)
    setattr(info, 'nfo_title', nfo_title)
    
    # 使用字典填充模板，生成相关文件的路径（多分片影片要考虑CD-x部分）
    cdx = '' if len(movie.files) <= 1 else '-CD1'
    if hasattr(info, 'title_break'):
        title_break = info.title_break
    else:
        title_break = split_by_punc(d['title'])
    if hasattr(info, 'ori_title_break'):
        ori_title_break = info.ori_title_break
    else:
        ori_title_break = split_by_punc(d['rawtitle'])
    copyd = d.copy()

    def legalize_info():
        if movie.save_dir != None:
            movie.save_dir = legalize_path(movie.save_dir)
        if movie.nfo_file != None:
            movie.nfo_file = legalize_path(movie.nfo_file)
        if movie.fanart_file != None:
            movie.fanart_file = legalize_path(movie.fanart_file)
        if movie.poster_file != None:
            movie.poster_file = legalize_path(movie.poster_file)
        if d['title'] != copyd['title']:
            logger.info(f"自动截短标题为:\n{copyd['title']}")
        if d['rawtitle'] != copyd['rawtitle']:
            logger.info(f"自动截短原始标题为:\n{copyd['rawtitle']}")
        return

    copyd['num'] = copyd['num'] + movie.attr_str
    longest_ext = max((os.path.splitext(i)[1] for i in movie.files), key=len)
    for end in range(len(ori_title_break), 0, -1):
        copyd['rawtitle'] = replace_illegal_chars(''.join(ori_title_break[:end]).strip())
        for sub_end in range(len(title_break), 0, -1):
            copyd['title'] = replace_illegal_chars(''.join(title_break[:sub_end]).strip())
            if Cfg().summarizer.move_files:
                save_dir = os.path.normpath(Cfg().summarizer.path.output_folder_pattern.format(**copyd)).strip()
                basename = os.path.normpath(Cfg().summarizer.path.basename_pattern.format(**copyd)).strip()
            else:
                # 如果不整理文件，则保存抓取的数据到当前目录
                save_dir = os.path.dirname(movie.files[0])
                filebasename = os.path.basename(movie.files[0])
                ext = os.path.splitext(filebasename)[1]
                basename = filebasename.replace(ext, '')
            long_path = os.path.join(save_dir, basename+longest_ext)
            remaining = get_remaining_path_len(os.path.abspath(long_path))
            if remaining > 0:
                movie.save_dir = save_dir
                movie.basename = basename
                movie.nfo_file = os.path.join(save_dir, Cfg().summarizer.nfo.basename_pattern.format(**copyd) + '.nfo')
                movie.fanart_file = os.path.join(save_dir, Cfg().summarizer.fanart.basename_pattern.format(**copyd) + '.jpg')
                movie.poster_file = os.path.join(save_dir, Cfg().summarizer.cover.basename_pattern.format(**copyd) + '.jpg')
                return legalize_info()
    else:
        # 以防万一，当整理路径非常深或者标题起始很长一段没有标点符号时，硬性截短生成的名称
        copyd['title'] = copyd['title'][:remaining]
        copyd['rawtitle'] = copyd['rawtitle'][:remaining]
        # 如果不整理文件，则保存抓取的数据到当前目录
        if not Cfg().summarizer.move_files:
            save_dir = os.path.dirname(movie.files[0])
            filebasename = os.path.basename(movie.files[0])
            ext = os.path.splitext(filebasename)[1]
            basename = filebasename.replace(ext, '')
        else:
            save_dir = os.path.normpath(Cfg().summarizer.path.output_folder_pattern.format(**copyd)).strip()
            basename = os.path.normpath(Cfg().summarizer.path.basename_pattern.format(**copyd)).strip()
        movie.save_dir = save_dir
        movie.basename = basename

        movie.nfo_file = os.path.join(save_dir, Cfg().summarizer.nfo.basename_pattern.format(**copyd) + '.nfo')
        movie.fanart_file = os.path.join(save_dir, Cfg().summarizer.fanart.basename_pattern.format(**copyd) + '.jpg')
        movie.poster_file = os.path.join(save_dir, Cfg().summarizer.cover.basename_pattern.format(**copyd) + '.jpg')

        return legalize_info()

def reviewMovieID(all_movies, root):
    """人工检查每一部影片的番号"""
    count = len(all_movies)
    logger.info('进入手动模式检查番号: ')
    for i, movie in enumerate(all_movies, start=1):
        id = repr(movie)[7:-2]
        print(f'[{i}/{count}]\t{Fore.LIGHTMAGENTA_EX}{id}{Style.RESET_ALL}, 对应文件:')
        relpaths = [os.path.relpath(i, root) for i in movie.files]
        print('\n'.join(['  '+i for i in relpaths]))
        s = prompt("回车确认当前番号，或直接输入更正后的番号（如'ABC-123'或'cid:sqte00300'）", "更正后的番号")
        if not s:
            logger.info(f"已确认影片番号: {','.join(relpaths)}: {id}")
        else:
            s = s.strip()
            s_lc = s.lower()
            if s_lc.startswith(('cid:', 'cid=')):
                new_movie = Movie(cid=s_lc[4:])
                new_movie.data_src = 'cid'
                new_movie.files = movie.files
            elif s_lc.startswith('fc2'):
                new_movie = Movie(s)
                new_movie.data_src = 'fc2'
                new_movie.files = movie.files
            else:
                new_movie = Movie(s)
                new_movie.data_src = 'normal'
                new_movie.files = movie.files
            all_movies[i-1] = new_movie
            new_id = repr(new_movie)[7:-2]
            logger.info(f"已更正影片番号: {','.join(relpaths)}: {id} -> {new_id}")
        print()


SUBTITLE_MARK_FILE = Image.open(os.path.abspath(resource_path('image/sub_mark.png')))
UNCENSORED_MARK_FILE = Image.open(os.path.abspath(resource_path('image/unc_mark.png')))

def process_poster(movie: Movie):
    cropper = get_cropper()
    fanart_image = Image.open(movie.fanart_file)
    fanart_cropped = cropper.crop(fanart_image)

    if Cfg().summarizer.cover.add_label:
        if movie.hard_sub:
            fanart_cropped = add_label_to_poster(fanart_cropped, SUBTITLE_MARK_FILE, LabelPostion.BOTTOM_RIGHT)
        if movie.uncensored:
            fanart_cropped = add_label_to_poster(fanart_cropped, UNCENSORED_MARK_FILE, LabelPostion.BOTTOM_LEFT)
    fanart_cropped.save(movie.poster_file)


def _download_extrafanart_pic(idx, pic_url, extrafanartdir):
    fanart_destination = f"{extrafanartdir}/{idx}.png"
    for _ in range(Cfg().network.retry):
        try:
            info = download(pic_url, fanart_destination)
            if valid_pic(fanart_destination):
                filesize = get_fmt_size(fanart_destination)
                width, height = get_pic_size(fanart_destination)
                elapsed = time.strftime("%M:%S", time.gmtime(info["elapsed"]))
                speed = get_fmt_size(info["rate"]) + "/s"
                logger.info(f"已下载剧照{pic_url} {idx}.png: {width}x{height}, {filesize} [{elapsed}, {speed}]")
                return True
        except Exception:
            continue
    logger.error(f"下载剧照{idx}: {pic_url}失败")
    return False

def RunNormalMode(all_movies):
    """普通整理模式"""

    def check_step(result, msg='步骤错误'):
        """检查一个整理步骤的结果，并负责更新tqdm的进度"""
        if result:
            inner_bar.update()
        else:
            raise Exception(msg + '\n')

    outer_bar = tqdm(all_movies, desc='整理影片', ascii=True, leave=False)

    # 预估本地整理流程的步骤总数，便于前端展示进度
    base_steps = 6
    if Cfg().translator.engine:
        base_steps += 1
    if Cfg().summarizer.extra_fanarts.enabled:
        base_steps += 1

    total_step = base_steps

    # 任务级事件：开始整理
    try:
        emit_event('task', {
            'status': 'RUNNING',
            'desc': '开始整理影片',
            'total': len(all_movies),
        })
    except Exception:
        logger.debug('emit task RUNNING event failed', exc_info=True)

    return_movies = []
    for idx, movie in enumerate(outer_bar, start=1):
        try:
            # 初始化本次循环要整理影片任务
            filenames = [os.path.split(i)[1] for i in movie.files]
            logger.info('正在整理: ' + ', '.join(filenames))
            outer_bar.set_description('正在整理: ' + ', '.join(filenames))
            # 输出当前影片事件，供 Web 端建立影片行
            emit_movie_event(idx, len(all_movies), movie)

            inner_bar = tqdm(total=total_step, desc='步骤', ascii=True, leave=False)
            # 依次执行各个步骤
            step_index = 1

            inner_bar.set_description('启动并发任务')
            emit_event('step', {
                'index': step_index,
                'total': total_step,
                'desc': '启动并发任务',
            })
            all_info = parallel_crawler(movie, inner_bar)
            # 提取使用的爬虫信息
            used_crawlers = all_info.pop('_used_crawlers', [])
            msg = f'为其配置的{len(Cfg().crawler.selection[movie.data_src])}个抓取器均未获取到影片信息'
            check_step(all_info, msg)

            step_index += 1
            inner_bar.set_description('汇总数据')
            emit_event('step', {
                'index': step_index,
                'total': total_step,
                'desc': '汇总数据',
            })
            has_required_keys = info_summary(movie, all_info)
            check_step(has_required_keys)

            if Cfg().translator.engine:
                step_index += 1
                inner_bar.set_description('翻译影片信息')
                emit_event('step', {
                    'index': step_index,
                    'total': total_step,
                    'desc': '翻译影片信息',
                })
                success = translate_movie_info(movie.info)
                check_step(success)

            step_index += 1
            emit_event('step', {
                'index': step_index,
                'total': total_step,
                'desc': '生成文件名',
            })
            generate_names(movie)
            check_step(movie.save_dir, '无法按命名规则生成目标文件夹')
            if not os.path.exists(movie.save_dir):
                os.makedirs(movie.save_dir)

            step_index += 1
            inner_bar.set_description('下载封面图片')
            emit_event('step', {
                'index': step_index,
                'total': total_step,
                'desc': '下载封面图片',
            })
            # 记录封面URL列表
            cover_urls = list(movie.info.covers) if hasattr(movie.info, 'covers') and movie.info.covers else []
            if Cfg().summarizer.cover.highres and hasattr(movie.info, 'big_covers') and movie.info.big_covers:
                cover_urls = list(movie.info.big_covers) + cover_urls
            
            cover_download_success = None  # 初始化为None，表示未知状态
            if not movie.info.covers:
                # 没有封面需要下载
                cover_download_success = None
                cover_dl = None
            else:
                if Cfg().summarizer.cover.highres:
                    cover_dl = download_cover(movie.info.covers, movie.fanart_file, movie.info.big_covers)
                else:
                    cover_dl = download_cover(movie.info.covers, movie.fanart_file)
                
                if not cover_dl:
                    # 封面下载失败：记录错误并跳过封面/海报处理，但不中断整个任务
                    cover_download_success = False
                    inner_bar.write('下载封面图片失败，将跳过封面与海报处理')
                    logger.error('下载封面图片失败，将跳过封面与海报处理')
                    # 当前设计中：下载封面 + 处理封面 各占一个步骤，这里直接推进两个进度
                    inner_bar.update()
                    inner_bar.update()
                else:
                    # 下载成功：封面下载步骤正常完成
                    check_step(True)
                    cover_download_success = True
                    # 使用inner_bar.write确保日志不被进度条覆盖
                    inner_bar.write('封面下载成功')
                    logger.info('封面下载成功')

                cover, pic_path = cover_dl
                # 确保实际下载的封面的url与即将写入到movie.info中的一致
                if cover != movie.info.cover:
                    movie.info.cover = cover
                # 根据实际下载的封面的格式更新fanart/poster等图片的文件名
                if pic_path != movie.fanart_file:
                    movie.fanart_file = pic_path
                    actual_ext = os.path.splitext(pic_path)[1]
                    movie.poster_file = os.path.splitext(movie.poster_file)[0] + actual_ext

                process_poster(movie)

                # 处理封面/海报步骤完成
                check_step(True)

            fanart_download_success = None
            fanart_download_count = 0
            fanart_download_failed_count = 0
            fanart_urls = []  # 记录剧照URL列表
            if Cfg().summarizer.extra_fanarts.enabled:
                step_index += 1
                inner_bar.set_description('下载剧照')
                emit_event('step', {
                    'index': step_index,
                    'total': total_step,
                    'desc': '下载剧照',
                })
                fanart_download_results = []  # 记录每个剧照的下载状态：[True, False, True, ...]
                if movie.info.preview_pics:
                    # 记录剧照URL列表
                    fanart_urls = list(movie.info.preview_pics)
                    extrafanartdir = movie.save_dir + '/extrafanart'
                    os.makedirs(extrafanartdir, exist_ok=True)  # <--- 这里添加了 exist_ok=True
                    max_workers = min(len(movie.info.preview_pics), 4)
                    results = []
                    with ThreadPoolExecutor(max_workers=max_workers) as executor:
                        futures = {}
                        for (id, pic_url) in enumerate(movie.info.preview_pics):
                            futures[executor.submit(_download_extrafanart_pic, id, pic_url, extrafanartdir)] = (id, pic_url)
                        for future in as_completed(futures):
                            ok = future.result()
                            results.append(ok)
                    if results:
                        fanart_download_results = results  # 保存每个剧照的下载结果
                        fanart_download_count = len([x for x in results if x])
                        fanart_download_failed_count = len([x for x in results if not x])
                        if fanart_download_failed_count > 0:
                            # 使用inner_bar.write确保日志不被进度条覆盖
                            inner_bar.write(f'下载剧照失败 {fanart_download_failed_count} 张，成功 {fanart_download_count} 张，将跳过失败的剧照')
                            logger.error(f'下载剧照失败 {fanart_download_failed_count} 张，成功 {fanart_download_count} 张，将跳过失败的剧照')
                            fanart_download_success = False
                        else:
                            # 使用inner_bar.write确保日志不被进度条覆盖
                            inner_bar.write(f'剧照下载成功，共 {fanart_download_count} 张')
                            logger.info(f'剧照下载成功，共 {fanart_download_count} 张')
                            fanart_download_success = True
                    else:
                        inner_bar.write('无剧照需要下载')
                        logger.info('无剧照需要下载')
                        fanart_download_success = None
                        fanart_download_results = []
                else:
                    fanart_download_success = None
                    fanart_download_results = []
                # 无论剧照下载是否全部成功，本步骤都视为完成，继续后续整理流程
                check_step(True)

            step_index += 1
            inner_bar.set_description('写入NFO')
            emit_event('step', {
                'index': step_index,
                'total': total_step,
                'desc': '写入NFO',
            })
            write_nfo(movie.info, movie.nfo_file)
            check_step(True)
            if Cfg().summarizer.move_files:
                step_index += 1
                inner_bar.set_description('移动影片文件')
                emit_event('step', {
                    'index': step_index,
                    'total': total_step,
                    'desc': '移动影片文件',
                })
                movie.rename_files(Cfg().summarizer.path.hard_link)
                check_step(True)
                
                # 【修改点】显式将进度条文字更新为 "整理完成"，这样 Web 端进度条就会定格在完成状态
                # 注意：这里使用了 movie.dvdid，如果你的版本中 movie 对象没有 dvdid 属性，可以用 movie.file_name 替代
                inner_bar.set_description(f'整理完成: {movie.dvdid}')
                
                # 【关键修复】使用 inner_bar.write() 替代 logger.info，防止日志被进度条刷新覆盖
                # 这样 "整理完成..." 的信息会打印在进度条上方，并被保留下来
                inner_bar.write(f'整理完成，相关文件已保存到: {movie.save_dir}')
            else:
                # 【修改点】同理，不移动文件模式下也更新状态
                inner_bar.set_description(f'刮削完成: {movie.dvdid}')
                
                # 【关键修复】同上，使用 write 确保日志显示
                inner_bar.write(f'刮削完成，相关文件已保存到: {movie.nfo_file}')

            # 输出当前影片的整理结果摘要事件，供 Web 端"刮削历史"使用
            try:
                extra_dir = None
                if Cfg().summarizer.extra_fanarts.enabled and movie.save_dir:
                    extra_dir = os.path.join(movie.save_dir, 'extrafanart')
                emit_event('movie', {
                    'type': 'summary',
                    'dvdid': getattr(movie, 'dvdid', None) or None,
                    'cid': getattr(movie, 'cid', None) or None,
                    'source_files': getattr(movie, 'files', []) or [],
                    'save_dir': getattr(movie, 'save_dir', None) or None,
                    'basename': getattr(movie, 'basename', None) or None,
                    'nfo_file': getattr(movie, 'nfo_file', None) or None,
                    'poster_file': getattr(movie, 'poster_file', None) or None,
                    'fanart_file': getattr(movie, 'fanart_file', None) or None,
                    'extrafanart_dir': extra_dir,
                    'cover_urls': cover_urls,
                    'cover_download_success': cover_download_success,
                    'cover_download_count': 1 if cover_download_success else 0,
                    'fanart_urls': fanart_urls,
                    'fanart_download_success': fanart_download_success,
                    'fanart_download_count': fanart_download_count,
                    'fanart_download_failed_count': fanart_download_failed_count,
                    'fanart_download_results': fanart_download_results,  # 每个剧照的下载状态列表
                    'used_crawlers': used_crawlers,
                })
            except Exception:
                logger.debug('emit movie summary event failed', exc_info=True)

            if movie != all_movies[-1] and Cfg().crawler.sleep_after_scraping > Duration(0):
                time.sleep(Cfg().crawler.sleep_after_scraping.total_seconds())
            return_movies.append(movie)
        finally:
            inner_bar.close()
    # 任务级事件：完成（无论成功失败，由调用方根据返回结果再细分）
    try:
        emit_event('task', {
            'status': 'SUCCEEDED',
            'desc': '整理影片结束',
            'total': len(return_movies),
        })
    except Exception:
        logger.debug('emit task SUCCEEDED event failed', exc_info=True)

    return return_movies


def download_cover(covers, fanart_path, big_covers=[]):
    """下载封面图片"""
    # 优先下载高清封面
    for url in big_covers:
        pic_path = get_pic_path(fanart_path, url)
        for _ in range(Cfg().network.retry):
            try:
                info = download(url, pic_path)
                if valid_pic(pic_path):
                    filesize = get_fmt_size(pic_path)
                    width, height = get_pic_size(pic_path)
                    elapsed = time.strftime("%M:%S", time.gmtime(info['elapsed']))
                    speed = get_fmt_size(info['rate']) + '/s'
                    logger.info(f"已下载高清封面: {width}x{height}, {filesize} [{elapsed}, {speed}]")
                    return (url, pic_path)
            except requests.exceptions.HTTPError:
                # HTTPError通常说明猜测的高清封面地址实际不可用，因此不再重试
                break
    # 如果没有高清封面或高清封面下载失败
    for url in covers:
        pic_path = get_pic_path(fanart_path, url)
        for _ in range(Cfg().network.retry):
            try:
                info = download(url, pic_path)
                if valid_pic(pic_path):
                    filesize = get_fmt_size(pic_path)
                    width, height = get_pic_size(pic_path)
                    elapsed = time.strftime("%M:%S", time.gmtime(info['elapsed']))
                    speed = get_fmt_size(info['rate']) + '/s'
                    logger.info(f"已下载封面: {width}x{height}, {filesize} [{elapsed}, {speed}]")
                    return (url, pic_path)
                else:
                    logger.debug(f"图片无效或已损坏: '{url}'，尝试更换下载地址")
                    break
            except Exception as e:
                logger.debug(e, exc_info=True)
    logger.error(f"下载封面图片失败")
    logger.debug('big_covers:'+str(big_covers) + ', covers'+str(covers))
    return None

def get_pic_path(fanart_path, url):
    fanart_base = os.path.splitext(fanart_path)[0]
    pic_extend = url.split('.')[-1]
    # 判断 url 是否带？后面的参数
    if '?' in pic_extend:
        pic_extend = pic_extend.split('?')[0]
        
    pic_path = fanart_base + "." + pic_extend
    return pic_path

def error_exit(success, err_info):
    """检查业务逻辑是否成功完成，如果失败则报错退出程序"""
    if not success:
        logger.error(err_info)
        sys.exit(1)


def entry():
    try:
        Cfg()
    except ValidationError as e:
        print(e.errors())
        exit(1)

    global actressAliasMap
    if Cfg().crawler.normalize_actress_name:
        actressAliasFilePath = resource_path("data/actress_alias.json")
        # 确保目录存在
        os.makedirs(os.path.dirname(actressAliasFilePath), exist_ok=True)
        # 如果文件不存在，创建一个空的 JSON 对象
        if not os.path.isfile(actressAliasFilePath):
            with open(actressAliasFilePath, "w", encoding="utf-8") as file:
                json.dump({}, file, ensure_ascii=False, indent=2)
            actressAliasMap = {}
        else:
            with open(actressAliasFilePath, "r", encoding="utf-8") as file:
                actressAliasMap = json.load(file)

    colorama.init(autoreset=True)

    # 检查更新
    version_info = 'JavSP ' + getattr(sys, 'javsp_version', '未知版本/从代码运行')
    logger.debug(version_info.center(60, '='))
    check_update(Cfg().other.check_update, Cfg().other.auto_update)
    root = get_scan_dir(Cfg().scanner.input_directory)
    error_exit(root, '未选择要扫描的文件夹')

    # 支持将单个影片文件路径作为输入：
    # - 若 root 为文件，则只扫描其所在目录，并仅保留包含该文件的 Movie；
    # - 若 root 为目录，则保持原有行为。
    if os.path.isfile(root):
        scan_root = os.path.dirname(root)
        print(f'扫描影片文件（单文件模式）...')
        recognized_all = scan_movies(scan_root)
        recognized = [m for m in recognized_all if root in getattr(m, 'files', [])]
    else:
        scan_root = root
        print(f'扫描影片文件...')
        recognized = scan_movies(scan_root)

    movie_count = len(recognized)
    recognize_fail = []
    error_exit(movie_count, '未找到影片文件')
    logger.info(f'扫描影片文件：共找到 {movie_count} 部影片')
    if Cfg().scanner.manual:
        reviewMovieID(recognized, root)
    RunNormalMode(recognized + recognize_fail)

    sys.exit(0)

if __name__ == "__main__":
    entry()
