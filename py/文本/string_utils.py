# 通用文本处理函数
"""
需要安装的库

tldextract
lxml
beautifulsoup4
dateparser
"""

import datetime
import hashlib
from bs4 import BeautifulSoup, SoupStrainer, Comment
from lxml import etree
import dateparser
import time
import re
from urllib.parse import urlparse, urlunparse
import tldextract
import pytz
import json
from html.parser import HTMLParser


def truncate(s: str, length: int = 40, end: str='...') -> str:
    """
    截断字符串

    Args:
        s (str): 需要截断的字符串
        length (int, optional): 截断长度. Defaults to 40.
        end (str, optional): 截断后追加的字符串. Defaults to '...'.

    Returns:
        str: 截断后的字符串
    """
    if len(s) > length:
        s = s[0: length] + end
    return s

def get_first_non_empty(*fields) -> any:
    """
    获取首个不为空的字段

    Args:
        *fields: 任意数量的字段

    Returns:
        any: 首个不为空的字段值，若所有字段为空则返回 None
    """
    return next(filter(bool, fields), None)

def md5(data: str) -> str:
    """
    计算字符串的 MD5 值

    Args:
        data (str): 需要计算 MD5 值的字符串

    Returns:
        str: 字符串的 MD5 值
    """
    return hashlib.md5(data.encode('utf-8')).hexdigest()

def remove_query_params(url):
    """
    移除 URL 中的查询参数

    Args:
        url (str): 需要移除查询参数的 URL

    Returns:
        str: 移除查询参数后的 URL
    """
    parsed_url = urlparse(url)
    return urlunparse(parsed_url._replace(query=""))


def parse_cookies(cookie_string, domain):
    """
    从字符串提取 cookies

    Args:
        cookie_string (str): 需要提取的 cookie 字符串
        domain (str): cookie 的域名

    Returns:
        list: 一个包含 cookie 信息的列表，结构如 {name, value, domain, path}
    """
    cookies = []
    for item in cookie_string.split('; '):
        name, value = item.split('=', 1)
        cookies.append({
            'name': name,
            'value': value,
            'domain': domain,  # 请根据实际情况替换
            'path': '/'
        })
    return cookies

class HTMLChecker(HTMLParser):
    def __init__(self):
        super().__init__()
        self.found_tag = False

    def handle_starttag(self, tag, attrs):
        self.found_tag = True

    def handle_startendtag(self, tag, attrs):
        self.found_tag = True

def looks_like_html(text):
    """
    判断是否是HTML
    """
    parser = HTMLChecker()
    try:
        parser.feed(text)
    except Exception:
        return False
    return parser.found_tag

def clean_html(html: str) -> dict:
    """
    清理HTML内容
    
    参数:
        html (str): 待清理的HTML字符串

    返回:
        dict: 包含清理后的HTML、纯文本、图片列表和视频列表的字典
    """
    strainer = SoupStrainer(['title', 'body', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'a', 'img', 'ul', 'ol', 'li', 'video', 'div'])
    soup = BeautifulSoup(html, 'html.parser', parse_only=strainer)

    imgs = []
    videos = []

    try:
        for i in soup.find_all(lambda tag: len(tag.get_text()) == 0 and tag.name not in ["img", "video", "br"]):
            for j in i.descendants:
                if hasattr(j, 'name') and j.name in ["img", "video", "br"]:
                    if j.name == 'img':
                        imgs.append(j.get('src'))
                    elif j.name == 'video':
                        videos.append(j.get('src'))
                    i.decompose()
                    break
            else:
                i.decompose()
    except AttributeError:
        pass

    for element in soup(text=lambda text: isinstance(text, Comment)):
        element.extract()
    
    text = soup.get_text()
    if not text:
        return {
            'html': html,
            'text': html,
            'imgs': [],
            'videos': []
        }
    
    cleaned_text = ' '.join(text.split())
    
    return {
        'html': str(soup),
        'text': cleaned_text,
        'imgs': imgs,
        'videos': videos
    }

def text_html(html_content: str) -> str:
    """
    清除HTML TAG
    
    Args:
        html_content (str): 待清理的HTML字符串
    
    Returns:
        str: 清理后的纯文本
    """
    # 如果不是HTML格式，直接返回
    if not looks_like_html(html_content):
        return html_content
    # 使用 lxml 解析器
    soup = BeautifulSoup(html_content, 'lxml')
    
    # 找到所有的换行相关标签，并在其后添加换行符
    for tag in soup.find_all(['p', 'div', 'br']):
        tag.insert_after('\n')
    
    # 获取纯文本
    text = soup.get_text()

    # 替换不间断空格
    text = text.replace('\xa0', ' ')
        
    # 将多个空格替换为单个空格
    text = re.sub(r'\s+', ' ', text)
    
    # 去掉多余的空白行
    clean_text = '\n'.join(line.strip() for line in text.splitlines() if line.strip())
    
    return clean_text


def str2timestamp(t, timezone='Asia/Shanghai', add_time=False, custom_format=None) -> int:
    """
    解析时间字符串为时间戳

    参数:
        t (str|int): 时间字符串或时间戳
        timezone (str): 时区信息，默认为'Asia/Shanghai'
        add_time (bool): 是否添加当前时间的秒数，默认为False
        custom_format (str): 自定义时间格式，默认为None

    返回:
        int: 时间戳

    异常:
        TypeError: 如果时间字符串为空
        ValueError: 如果时间字符串无法解析或格式不匹配
    """
    if isinstance(t, int):
        return t
    
    t = t.replace('&nbsp;', '').strip()
    if not t:
        raise TypeError("时间不能为空")
    
    if isinstance(t, int):
        length = len(str(t))
        if length == 13:
            return int(t / 1000)
        if length == 10:
            return t
        return 0

    if custom_format:
        try:
            date = datetime.datetime.strptime(t, custom_format)
            if timezone:
                tz = pytz.timezone(timezone)
                date = tz.localize(date)
            return int(date.timestamp())
        except ValueError:
            raise ValueError(f"无法解析时间: {t}，格式不匹配 {custom_format}")

    if re.search(r"\d+月\d+", t):
        t = t.replace("年", "/").replace("月", "/").replace("日", " ")
    if re.search(r'\d+时\d+', t):
        t = t.replace("时", ":").replace("分", ":").replace("秒", "")
    t = t.strip(": ")

    reference_date = datetime.datetime.now()
    settings = {'RELATIVE_BASE': reference_date}
    if timezone:
        settings['TIMEZONE'] = timezone
        settings['RETURN_AS_TIMEZONE_AWARE'] = True
    
    date = dateparser.parse(t, settings=settings, languages=['zh', 'en'])

    if not date:
        raise ValueError(f"无法解析时间: {t}")
    
    timestamp = int(date.timestamp())
    
    if add_time:
        tz = pytz.timezone(timezone)
        tz_time = datetime.datetime.now(tz)
        total_seconds = (tz_time.hour * 3600) + (tz_time.minute * 60) + tz_time.second - 20*60
        timestamp += total_seconds
    
    now = int(reference_date.timestamp())
    if timestamp > now:
        raise ValueError(f"大于现在时间: {t}")
    
    return timestamp
