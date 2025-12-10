import pymysql
from psycopg_pool import ConnectionPool
import threading
from threading import Lock
from config import settings

class ThreadSafeDBConnectionPool:
    _pools = {}
    _lock = Lock()

    def __new__(cls, identifier, *args, **kwargs):
        with cls._lock:
            if identifier not in cls._pools:
                instance = super().__new__(cls)
                instance._setup_connection(*args, **kwargs)
                cls._pools[identifier] = instance
        return cls._pools[identifier]

    def _setup_connection(self, host, user, password, db, port=3306, charset='utf8mb4'):
        # 用于初始化连接
        self._connection = pymysql.connect(
            host=host,
            user=user,
            password=password,
            db=db,
            port=port,
            charset=charset
        )

    def get_connection(self):
        # 获取当前连接
        return self._connection

    def close(self):
        # 关闭单个连接
        if self._connection:
            self._connection.close()

    @classmethod
    def close_all(cls):
        # 关闭所有连接并清理资源
        with cls._lock:
            for instance in cls._pools.values():
                instance.close()
            cls._pools.clear()

class PostgresConnectionPool:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, dsn, min_size=1, max_size=10, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init_pool(dsn, min_size, max_size, **kwargs)
        return cls._instance

    def _init_pool(self, dsn, min_size, max_size, **kwargs):
        self.pool = ConnectionPool(
            conninfo=dsn,
            min_size=min_size,
            max_size=max_size,
            **kwargs
        )
        print("✅ psycopg3 连接池初始化成功")

    def get_conn(self):
        return self.pool.getconn()

    def put_conn(self, conn):
        self.pool.putconn(conn)

    def close(self):
        self.pool.close()

def get_db_connection():
    config = settings.db.spider
    return PostgresConnectionPool(config.dns, 1, 10)

if __name__ == '__main__':
    db = get_db_connection()
    with db.pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT now();")
            print("当前时间:", cur.fetchone())
    """
    # 使用示例
    db1 = ThreadSafeDBConnectionPool('db1', host='localhost', user='user1', password='pass1', db='database1')
    db2 = ThreadSafeDBConnectionPool('db2', host='localhost', user='user2', password='pass2', db='database2')

    conn1 = db1.get_connection()
    conn2 = db2.get_connection()

    # 关闭单个连接
    db1.close()

    # 关闭所有连接
    ThreadSafeDBConnectionPool.close_all()
    """
