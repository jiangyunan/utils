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
    
def remove_symbols(text):
    """
    去除字符串中的所有符号，包括中文符号。

    参数:
    text (str): 要处理的字符串

    返回:
    str: 去除符号后的字符串
    """
    # 使用 Unicode 属性匹配所有符号字符
    cleaned_text = re.sub(r'\p{P}|\p{S}', '', text)
    return cleaned_text

def is_loose_uuid(s):
    """
    判断字符串是否符合 UUID 格式
    """
    parts = s.split('-')
    
    # 要求有 5 段（UUID 的格式）
    if len(parts) != 5:
        return False

    # 每段的长度要求（宽松一点）
    expected_lengths = [6, 4, 4, 4, 6]
    for part, min_len in zip(parts, expected_lengths):
        if len(part) < min_len:
            return False
        if not all(c in '0123456789abcdefABCDEF' for c in part):
            return False

    return True

def is_chinese(text: str, threshold: float = 0.1) -> bool:
    """
    判断文本是否为中文,空返回Ture
    
    Args:
        text: 输入文本
        threshold: 中文字符占比阈值 (0.0-1.0)，默认0.1表示中文字符超过80%就算中文
    
    Returns:
        True: 是中文文本
        False: 不是中文文本
    """
    if not text or not text.strip():
        return True
    
    # 移除非文字
    text = re.sub(r'[^\w]+', '', text)
    
    if not text:
        return True
    
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # 表情符号
        "\U0001F300-\U0001F5FF"  # 符号和象形文字
        "\U0001F680-\U0001F6FF"  # 交通和地图符号
        "\U0001F1E0-\U0001F1FF"  # 旗帜
        "\U00002702-\U000027B0"  # 装饰符号
        #"\U000024C2-\U0001F251"  # 封闭字符包含汉字
        "\U0001F900-\U0001F9FF"  # 补充符号和象形文字
        "\U0001FA00-\U0001FA6F"  # 扩展A
        "\U0001FA70-\U0001FAFF"  # 扩展B
        "\U00002600-\U000026FF"  # 杂项符号
        "\U00002700-\U000027BF"  # 装饰符号
        "]+",
        flags=re.UNICODE
    )
    text = emoji_pattern.sub('', text)
    if not text:
        return True
    
    # 获取前30个字符
    text = text[:60]

    # 检查是否包含日语假名
    # 平假名: \u3040-\u309F
    # 片假名: \u30A0-\u30FF
    japanese_kana = re.findall(r'[\u3040-\u309F\u30A0-\u30FF]', text)
    
    # 如果包含假名,判断假名占比
    if japanese_kana:
        kana_ratio = len(japanese_kana) / len(text)
        # 如果假名占比超过10%,认为是日语
        if kana_ratio > 0.1:
            return False
    
    # 统计简体中文字符（常用汉字范围）和数字
    chinese_chars = re.findall(r'[\u4e00-\u9fa5\d]', text)
    
    # 计算中文字符占比
    chinese_ratio = len(chinese_chars) / len(text)
    
    return chinese_ratio >= threshold
