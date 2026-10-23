"""与文件相关的各类功能"""
import os
from pathlib import Path
import re
import ctypes
import logging
import itertools
import json
from sys import platform
from typing import List


__all__ = ['scan_movies', 'get_fmt_size', 'get_remaining_path_len', 'replace_illegal_chars', 'get_failed_when_scan', 'find_subtitle_in_dir']


from javsp.avid import *
from javsp.config import Cfg
from javsp.datatype import Movie
from javsp.multipart import group_files, part_number

logger = logging.getLogger(__name__)
failed_items = []


def scan_movies(root: str) -> List[Movie]:
    """获取文件夹内的所有影片的列表（自动探测同一文件夹内的分片）"""
    dic = {}
    small_videos = {}
    ignore_folder_name_pattern = re.compile('|'.join(Cfg().scanner.ignored_folder_name_pattern))
    if Cfg().scanner.input_files is not None:
        selected = {}
        for value in Cfg().scanner.input_files:
            path = os.path.abspath(value)
            if not os.path.isfile(path):
                raise FileNotFoundError(f'分 P 文件不存在: {path}')
            selected.setdefault(os.path.dirname(path), []).append(os.path.basename(path))
        scan_entries = [(directory, [], names) for directory, names in selected.items()]
    elif os.path.isfile(root):
        scan_entries = [(os.path.dirname(root), [], [os.path.basename(root)])]
    else:
        scan_entries = os.walk(root)

    for dirpath, dirnames, filenames in scan_entries:
        for name in dirnames.copy():
            if ignore_folder_name_pattern.match(name):
                dirnames.remove(name)
            if Cfg().scanner.skip_nfo_dir and any(
                    file.lower().endswith('.nfo') for file in os.listdir(os.path.join(dirpath, name))
                    if isinstance(file, str)):
                print(f'skip file {name}')
                dirnames.remove(name)

        for name in filenames:
            ext = os.path.splitext(name)[1].lower()
            if ext not in Cfg().scanner.filename_extensions:
                continue
            fullpath = os.path.join(dirpath, name)
            filesize = os.path.getsize(fullpath)
            if (filesize < Cfg().scanner.minimum_size
                    and not (ext == '.strm' and Cfg().scanner.strm_ignore_minimum_size)):
                small_videos.setdefault(name, []).append(fullpath)
                continue
            configured = configured_media_type(fullpath)
            dvdid = configured[2] if configured and configured[1] == 'dvdid' else get_id(fullpath)
            cid = configured[2] if configured and configured[1] == 'cid' else ('' if configured else get_cid(fullpath))
            avid = cid if cid else dvdid
            if avid:
                dic.setdefault(avid, []).append(fullpath)
            else:
                fail = Movie('无法识别番号')
                fail.files = [fullpath]
                failed_items.append(fail)
                logger.error("无法提取影片番号: '%s'", fullpath)

    has_avid = {}
    for name in list(small_videos):
        configured = configured_media_type(name)
        dvdid = configured[2] if configured and configured[1] == 'dvdid' else get_id(name)
        cid = configured[2] if configured and configured[1] == 'cid' else ('' if configured else get_cid(name))
        avid = cid if cid else dvdid
        if avid in dic:
            dic[avid].extend(small_videos.pop(name))
        elif avid:
            has_avid[name] = avid
    small_videos = {key: sorted(value) for key, value in sorted(small_videos.items())}
    skipped_files = list(itertools.chain(*small_videos.values()))
    if skipped_files:
        if has_avid:
            logger.info('跳过了 %s 等%s个小于指定大小的视频文件', ', '.join(has_avid), len(skipped_files))
        else:
            logger.info('跳过了%s个小于指定大小的视频文件', len(skipped_files))
        logger.debug('跳过的视频文件如下:\n%s', '\n'.join(skipped_files))

    # Validate same-directory groups with the same rules used by Web task scans.
    validated = []
    for files in dic.values():
        dirs = {os.path.dirname(path) for path in files}
        if len(dirs) > 1:
            logger.error('同番号文件分布于不同目录，跳过整理: %s', '、'.join(files))
            continue
        try:
            validated.extend(group_files(files, Cfg().scanner))
        except ValueError as exc:
            logger.error('%s', exc)
    dic = validated

    movies: List[Movie] = []
    for files in sorted(dic, key=lambda paths: str(paths[0]).casefold()):
        files = list(map(str, files))
        configured = configured_media_type(files[0])
        avid = configured[2] if configured else (get_cid(files[0]) or get_id(files[0]))
        src = guess_av_type(avid, files[0])
        if not is_cid_media_type(src):
            mov = Movie(avid)
        else:
            mov = Movie(cid=avid)
            mov.dvdid = get_id(files[0])
        mov.files = files
        numbers = [part_number(path) for path in files]
        if all(number is not None for number in numbers):
            mov.part_numbers = numbers
        mov.data_src = src
        logger.debug('影片数据源类型: %s: %s', avid, src)
        movies.append(mov)
    return movies


def get_failed_when_scan():
    """获取扫描影片过程中无法自动识别番号的条目"""
    return failed_items


_PARDIR_REPLACE = re.compile(r'\.{2,}')
def replace_illegal_chars(name):
    """将不能用于文件名的字符替换为形近的字符"""
    # 非法字符列表 https://stackoverflow.com/a/31976060/6415337
    if platform == 'win32': 
        # http://www.unicode.org/Public/security/latest/confusables.txt
        charmap = {'<': '❮',
                   '>': '❯',
                   ':': '：',
                   '"': '″',
                   '/': '／',
                   '\\': '＼',
                   '|': '｜',
                   '?': '？',
                   '*': '꘎'}
        for c, rep in charmap.items():
            name = name.replace(c, rep)
    elif platform == "darwin":  # MAC OS X
        name = name.replace(':', '：')
    else:   # 其余都当做Linux处理
        name = name.replace('/', '／')
    # 处理连续多个英文句点.
    if os.pardir in name:
        name = _PARDIR_REPLACE.sub('…', name)
    return name


def is_remote_drive(path: str):
    """判断一个路径是否为远程映射到本地"""
    #TODO: 当前仅支持Windows平台
    if platform != 'win32':
        return False
    DRIVE_REMOTE = 0x4
    drive = os.path.splitdrive(os.path.abspath(path))[0] + os.sep
    result = ctypes.windll.kernel32.GetDriveTypeW(drive)
    return result == DRIVE_REMOTE


def get_remaining_path_len(path):
    """计算当前系统支持的最大路径长度与给定路径长度的差值"""
    #TODO: 支持不同的操作系统
    fullpath = os.path.abspath(path)
    # Windows: If the length exceeds ~256 characters, you will be able to see the path/files via Windows/File Explorer, but may not be able to delete/move/rename these paths/files
    length = len(fullpath.encode('utf-8')) if Cfg().summarizer.path.length_by_byte else len(fullpath)
    remaining = Cfg().summarizer.path.length_maximum - length
    return remaining


def get_fmt_size(file_or_size) -> str:
    """获取格式化后的文件大小

    Args:
        file_or_size (str or int): 文件路径或者文件大小

    Returns:
        str: e.g. 20.21 MiB
    """
    if file_or_size is None:
        size = 0
    elif isinstance(file_or_size, (int, float)):
        size = file_or_size
    else:
        size = os.path.getsize(file_or_size)
    for unit in ['','Ki','Mi','Gi','Ti']:
        # 1023.995: to avoid rounding bug when format str, e.g. 1048571 -> 1024.0 KiB
        if abs(size) < 1023.995:
            return f"{size:3.2f} {unit}B"
        size /= 1024.0


_sub_files = {}
SUB_EXTENSIONS = ('.srt', '.ass')
def find_subtitle_in_dir(folder: str, dvdid: str):
    """在folder内寻找是否有匹配dvdid的字幕"""
    folder_data = _sub_files.get(folder)
    if folder_data is None:
        # 此文件夹从未检查过时
        folder_data = {}
        for dirpath, dirnames, filenames in os.walk(folder):
            for file in filenames:
                basename, ext = os.path.splitext(file)
                if ext in SUB_EXTENSIONS:
                    match_id = get_id(basename)
                    if match_id:
                        folder_data[match_id.upper()] = os.path.join(dirpath, file)
        _sub_files[folder] = folder_data
    sub_file = folder_data.get(dvdid.upper())
    return sub_file


if __name__ == "__main__":
    p = "C:/Windows\\System32//PerceptionSimulation\\..\\Assets\\/ClosedHand.png"
    print(get_remaining_path_len(p))
