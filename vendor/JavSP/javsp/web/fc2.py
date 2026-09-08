"""从FC2官网抓取数据"""
import logging
import re
import requests


from javsp.web.base import get_html, request_get, resp2html
from javsp.web.exceptions import *
from javsp.config import Cfg
from javsp.lib import strftime_to_minutes
from javsp.datatype import MovieInfo
from javsp.web.parsing import first, class_xpath, detail_container


logger = logging.getLogger(__name__)
base_url = 'https://adult.contents.fc2.com'


def get_movie_score(fc2_id):
    """通过评论数据来计算FC2的影片评分（10分制），无法获得评分时返回None"""
    html = get_html(f'{base_url}/article/{fc2_id}/review')
    review_tags = html.xpath("//ul[@class='items_comment_headerReviewInArea']/li")
    reviews = {}
    for tag in review_tags:
        score_text = first(tag, "div/span/text()", "")
        vote_text = ''.join(tag.xpath("span//text()"))
        if not score_text.isdigit() or not vote_text.isdigit():
            continue
        score = int(score_text)
        vote = int(vote_text)
        reviews[score] = vote
    total_votes = sum(reviews.values())
    if (total_votes >= 2):   # 至少也该有两个人评价才有参考意义一点吧
        summary = sum([k*v for k, v in reviews.items()])
        final_score = summary / total_votes * 2   # 乘以2转换为10分制
        return final_score


def parse_data(movie: MovieInfo):
    """解析指定番号的影片数据"""
    # 去除番号中的'FC2'字样
    id_uc = movie.dvdid.upper()
    if not id_uc.startswith('FC2-'):
        raise ValueError('Invalid FC2 number: ' + movie.dvdid)
    fc2_id = id_uc.replace('FC2-', '')
    # 抓取网页
    url = f'{base_url}/article/{fc2_id}/'
    resp = request_get(url)
    if '/id.fc2.com/' in resp.url:
        raise SiteBlocked('FC2要求当前IP登录账号才可访问，请尝试更换为日本IP')
    html = resp2html(resp)
    container = detail_container(html, f"//div[{class_xpath('items_article_left')}]", 'fc2', movie.dvdid)
    # FC2 标题增加反爬乱码，使用数组合并标题
    title_arr = container.xpath(f".//div[{class_xpath('items_article_headerInfo')}]/h3/text()")
    title = ''.join(title_arr).strip()
    if not title:
        raise WebsiteError('fc2: 页面缺少影片标题，无法确认有效资料')
    thumb_tag = first(container, f".//div[{class_xpath('items_article_MainitemThumb')}]", container)
    thumb_pic = first(thumb_tag, "span/img/@src")
    duration_str = first(thumb_tag, f"span/p[{class_xpath('items_article_info')}]/text()", "")
    # FC2没有制作商和发行商的区分，作为个人市场，影片页面的'by'更接近于制作商
    producer = first(container, ".//li[normalize-space(text())='by']/a/text()")
    genre = container.xpath("//a[@class='tag tagTag']/text()")
    date_str = ' '.join(container.xpath(f".//*[{class_xpath('items_article_Releasedate')}]//text()"))
    date_match = re.search(r'\d{4}[/-]\d{2}[/-]\d{2}', date_str)
    publish_date = date_match.group().replace('/', '-') if date_match else None
    preview_pics = container.xpath("//ul[@data-feed='sample-images']/li/a/@href")

    if Cfg().crawler.hardworking:
        # 通过评论数据来计算准确的评分
        try:
            score = get_movie_score(fc2_id)
            if score:
                movie.score = f'{score:.2f}'
        except (requests.exceptions.RequestException, CrawlerError, ValueError):
            logger.debug('FC2 可选评分获取失败', exc_info=True)
        # 预览视频是动态加载的，不在静态网页中
        desc_frame_url = first(container, f".//section[{class_xpath('items_article_Contents')}]/iframe/@src")
        if desc_frame_url:
            key = desc_frame_url.split('=')[-1]
            api_url = f'{base_url}/api/v2/videos/{fc2_id}/sample?key={key}'
            try:
                result = request_get(api_url).json()
                if isinstance(result, dict):
                    movie.preview_video = result.get('path')
            except (requests.exceptions.RequestException, CrawlerError, ValueError):
                logger.debug('FC2 可选预览视频获取失败', exc_info=True)
    else:
        # 获取影片评分。影片页面的评分只能粗略到星级，且没有分数，要通过类名来判断，如'items_article_Star5'表示5星
        score_tag_attr = first(container, f".//a[{class_xpath('items_article_Stars')}]/p/span/@class", "")
        score_match = re.search(r'items_article_Star([0-5])\b', score_tag_attr)
        if score_match:
            movie.score = f'{int(score_match.group(1)) * 2:.2f}'

    movie.dvdid = id_uc
    movie.url = url
    movie.title = title
    movie.genre = genre
    movie.producer = producer
    if duration_str:
        try:
            movie.duration = str(strftime_to_minutes(duration_str))
        except ValueError:
            logger.debug('FC2 时长格式无法解析: %s', duration_str)
    movie.publish_date = publish_date
    movie.preview_pics = preview_pics
    # FC2的封面是220x220的，和正常封面尺寸、比例都差太多。如果有预览图片，则使用第一张预览图作为封面
    if movie.preview_pics:
        movie.cover = preview_pics[0]
    else:
        movie.cover = thumb_pic


if __name__ == "__main__":
    import pretty_errors
    pretty_errors.configure(display_link=True)
    logger.root.handlers[1].level = logging.DEBUG

    movie = MovieInfo('FC2-718323')
    try:
        parse_data(movie)
        print(movie)
    except CrawlerError as e:
        logger.error(e, exc_info=1)
