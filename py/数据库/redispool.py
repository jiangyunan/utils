import redis
import threading


class RedisPoolFactory:
    """
    连接池工厂
    """
    _instances = {}
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls, url):
        if url not in cls._instances:
            with cls._lock:
                if url not in cls._instances:
                    try:
                        cls._instances[url] = redis.ConnectionPool.from_url(url, decode_responses=True)
                    except Exception as e:
                        raise RuntimeError(f"Failed to create Redis connection pool: {e}")
        return cls._instances[url]

    @classmethod
    def get_redis_conn(cls, url):
        pool = cls.get_instance(url)
        return redis.Redis(connection_pool=pool, decode_responses=True)

    @classmethod
    def destroy_instance(cls, url):
        """销毁指定 URL 对应的连接池"""
        with cls._lock:
            if url in cls._instances:
                pool = cls._instances.pop(url)
                # 主动断开连接池里的所有连接
                pool.disconnect()

    @classmethod
    def destroy_all(cls):
        """销毁所有连接池"""
        with cls._lock:
            for pool in cls._instances.values():
                pool.disconnect()
            cls._instances.clear()