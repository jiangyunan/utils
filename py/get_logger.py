import logging.config
import requests
import logging
from datetime import datetime
import sys
import json
import traceback
from elasticsearch import Elasticsearch

class WxHandler(logging.Handler):
    """企业微信日志处理
    """
    def __init__(self, level) -> None:
        super().__init__(level)

    def mapLogRecord(self, record):
        """
        Default implementation of mapping the log record into a dict
        that is sent as the CGI data. Overwrite in your class.
        Contributed by Franz Glasner.
        """
        return record.__dict__
    
    def emit(self, record):
        data = dict(self.mapLogRecord(record))
        msg = self.format(record)
        formdata = {
            'labels':{
                'name': data['name'],
                'file': data['pathname'] + data['filename'],
                'line': data['lineno']
            },
            'annotations': {
                'file': data['pathname'] + data['filename'],
                'line': data['lineno'],
                'description': f"{msg}"
            },
            "datetime": int(datetime.now().timestamp()),
            "expire": 3600,
        }
        #todo 发送代码

class ElasticsearchHandler(logging.Handler):
    def __init__(self, es_host=["https://m7:9200", "https://m6:9200"], index="logs", username="elastic", password="carnoc", ca_certs='ca.crt'):
        super().__init__()
        self.es = Elasticsearch(es_host, basic_auth=(username, password), verify_certs=True, ca_certs=ca_certs)
        self.index = index

    def emit(self, record):
        try:
            log_entry = self.format(record)
            self.es.index(index=self.index, document=json.loads(log_entry))
        except Exception as e:
            print(f"Failed to send log to Elasticsearch: {e}")

class ElasticsearchFormatter(logging.Formatter):
    def format(self, record):
        try:
            log_entry = {
                "@timestamp": datetime.now().isoformat(),
                "level": record.levelname,
                "message": self.serialize_message(record.getMessage()),  # 存入 message
                "name": record.name,
                "pathname": record.pathname,
                "lineno": record.lineno,
                "funcName": record.funcName,
                "exception": self.get_traceback(record),  # 存入 exception
                "extra": self.serialize_extra(record.__dict__),  # 其他数据
            }
            return json.dumps(log_entry)
        except Exception as e:
            return json.dumps({"error": f"Failed to format log: {str(e)}"})

    def serialize_message(self, message):
        """确保 message 可序列化"""
        if isinstance(message, (dict, list, str, int, float, bool, type(None))):
            return message
        return str(message)  # 不能序列化的对象转换为字符串

    def serialize_extra(self, extra_dict):
        """确保额外的日志数据可序列化"""
        serializable_data = {}
        ignore_keys = {"args", "exc_info", "exc_text", "message"}  # 这些字段可能导致问题
        for key, value in extra_dict.items():
            if key not in ignore_keys:
                if isinstance(value, (dict, list, str, int, float, bool, type(None))):
                    serializable_data[key] = value
                else:
                    serializable_data[key] = str(value)  # 不能序列化的对象转换为字符串
        return serializable_data

    def get_traceback(self, record):
        """获取异常堆栈信息"""
        if record.exc_info:
            return "".join(traceback.format_exception(*record.exc_info))
        return None  # 没有异常时返回 None

LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': True, # 覆盖原日志处理
    'formatters': {
        'standard': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            'datefmt': '%Y-%m-%dT%H:%M:%S'
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'DEBUG',
            'formatter': 'standard',
            'stream': 'ext://sys.stdout'
        }
    },
    'root': {
        'level': 'INFO',
        'handlers': ['console'],
    },
    'loggers': {
        '*': {
            'level': 'INFO',
            'handlers': ['console'],
            'propagate': False
        }
    }
}

_loggers = {}

def get_logger(name):
    """生成logger

    Args:
        name (str): 程序名

    Returns:
        logger: _description_
    """
    if name in _loggers:
        return _loggers[name]
    
    logging.config.dictConfig(LOGGING_CONFIG)
    logger = logging.getLogger(name)
    #logger.addHandler(WxHandler(logging.ERROR))
    #es_handler = ElasticsearchHandler(settings.es.url.split(','), username=settings.es.user, #password=settings.es.password, ca_certs=settings.es.ca_cert)
    #es_handler.setLevel('ERROR')
    #es_handler.setFormatter(ElasticsearchFormatter())
    #logger.addHandler(es_handler)

    # 未处理的异常统一处理
    # 定义一个新的异常处理函数
    def handle_exception(exc_type, exc_value, exc_traceback):
        logger.error("未处理的异常", exc_info=(exc_type, exc_value, exc_traceback))

    # 将新的异常处理函数设置为 sys.excepthook
    sys.excepthook = handle_exception
    _loggers[name] = logger

    return logger
