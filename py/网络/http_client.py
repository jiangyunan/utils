import httpx
import asyncio
import socket
import time
import sqlite3
from typing import Dict, Tuple, Optional, ClassVar
import logging
from utils.logger import logger
# 关闭第三方库的 DEBUG 日志
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)

class PersistentDNSCache:
    """持久化 DNS 缓存管理器"""
    
    def __init__(self, db_path: str = "dns_cache.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dns_cache (
                hostname TEXT PRIMARY KEY,
                ip TEXT NOT NULL,
                expire_time REAL NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        conn.commit()
        conn.close()
        logger.info(f"✅ DNS 缓存数据库初始化完成: {self.db_path}")
    
    def get(self, hostname: str) -> Optional[str]:
        """获取缓存的 IP"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT ip, expire_time FROM dns_cache WHERE hostname = ?",
            (hostname,)
        )
        result = cursor.fetchone()
        conn.close()
        
        if result:
            ip, expire_time = result
            if time.time() < expire_time:
                logger.debug(f"✅ DNS 缓存命中 (数据库): {hostname} -> {ip}")
                return ip
            else:
                # 过期，删除
                self.delete(hostname)
                logger.info(f"⏰ DNS 缓存过期 (数据库): {hostname}")
        
        return None
    
    def set(self, hostname: str, ip: str, ttl: int):
        """设置 DNS 缓存"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        expire_time = time.time() + ttl
        now = time.time()
        
        cursor.execute("""
            INSERT OR REPLACE INTO dns_cache 
            (hostname, ip, expire_time, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (hostname, ip, expire_time, now, now))
        
        conn.commit()
        conn.close()
        logger.info(f"💾 DNS 缓存已保存 (数据库): {hostname} -> {ip} (TTL: {ttl}s)")
    
    def delete(self, hostname: str):
        """删除缓存"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM dns_cache WHERE hostname = ?", (hostname,))
        conn.commit()
        conn.close()
    
    def clear(self):
        """清空所有缓存"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM dns_cache")
        conn.commit()
        conn.close()
        logger.info("🧹 DNS 缓存已清空 (数据库)")
    
    def cleanup_expired(self):
        """清理过期缓存"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM dns_cache WHERE expire_time < ?", (time.time(),))
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        if deleted > 0:
            logger.info(f"🧹 清理了 {deleted} 条过期 DNS 缓存")
        return deleted
    
    def get_stats(self) -> dict:
        """获取缓存统计"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 总数
        cursor.execute("SELECT COUNT(*) FROM dns_cache")
        total = cursor.fetchone()[0]
        
        # 有效数量
        cursor.execute("SELECT COUNT(*) FROM dns_cache WHERE expire_time > ?", (time.time(),))
        valid = cursor.fetchone()[0]
        
        # 详细信息
        cursor.execute("SELECT hostname, ip, expire_time FROM dns_cache")
        domains = {}
        current_time = time.time()
        
        for hostname, ip, expire_time in cursor.fetchall():
            domains[hostname] = {
                "ip": ip,
                "expires_in": max(0, int(expire_time - current_time)),
                "is_valid": expire_time > current_time
            }
        
        conn.close()
        
        return {
            "total_cached": total,
            "valid_entries": valid,
            "expired_entries": total - valid,
            "domains": domains
        }



class HttpClient(httpx.AsyncClient):
    """带持久化 DNS 缓存和自动重试的 httpx.AsyncClient"""
    
    # 类级别的缓存管理器
    _dns_cache: ClassVar[Optional[PersistentDNSCache]] = None
    _global_lock: ClassVar[asyncio.Lock] = None
    
    def __init__(self, dns_ttl: int = 600, dns_cache_db: str = "dns_cache.db", *args, **kwargs):
        """
        Args:
            dns_ttl: DNS 缓存时间（秒），默认 10 分钟
            dns_cache_db: DNS 缓存数据库路径
        """
        super().__init__(*args, **kwargs)
        self.dns_ttl = dns_ttl
        
        # 初始化全局缓存管理器（只初始化一次）
        if HttpClient._dns_cache is None:
            HttpClient._dns_cache = PersistentDNSCache(dns_cache_db)
            HttpClient._dns_cache.cleanup_expired()  # 启动时清理过期缓存
        
        # 初始化全局锁
        if HttpClient._global_lock is None:
            HttpClient._global_lock = asyncio.Lock()
        
        stats = self._dns_cache.get_stats()
        logger.info(f"✅ HttpClient 初始化完成 (缓存: {stats['valid_entries']}/{stats['total_cached']} 条有效)")
    
    async def _resolve_dns(self, hostname: str) -> Optional[str]:
        """解析 DNS（使用持久化缓存）"""
        async with self._global_lock:
            # 检查缓存
            ip = self._dns_cache.get(hostname)
            if ip:
                return ip
            
            # DNS 解析（带重试）
            for attempt in range(3):
                try:
                    loop = asyncio.get_event_loop()
                    ip = await loop.run_in_executor(None, socket.gethostbyname, hostname)
                    
                    # 存入持久化缓存
                    self._dns_cache.set(hostname, ip, self.dns_ttl)
                    logger.info(f"🔍 DNS 解析成功: {hostname} -> {ip}")
                    return ip
                
                except socket.gaierror:
                    logger.warning(f"❌ DNS 解析失败 (尝试 {attempt+1}/3): {hostname}")
                    if attempt < 2:
                        await asyncio.sleep(2 ** attempt)
            
            return None
    
    async def request(self, method: str, url: str, max_retries: int = 3, 
                     retry_delay: float = 1.0, **kwargs) -> httpx.Response:
        """发送 HTTP 请求（带自动重试）"""
        from urllib.parse import urlparse, urlunparse
        
        parsed = urlparse(url)
        hostname = parsed.hostname
        
        # DNS 解析
        ip = await self._resolve_dns(hostname)
        if not ip:
            logger.error(f"❌ DNS 解析失败，使用原始 URL: {url}")
            target_url = url
        else:
            # 替换主机名为 IP
            target_url = urlunparse((
                parsed.scheme,
                f"{ip}:{parsed.port}" if parsed.port else ip,
                parsed.path,
                parsed.params,
                parsed.query,
                parsed.fragment
            ))
            # 设置 Host 头
            if 'headers' not in kwargs:
                kwargs['headers'] = {}
            kwargs['headers']['Host'] = hostname
        
        # 重试逻辑
        last_error = None
        for attempt in range(max_retries):
            try:
                logger.info(f"🚀 发送请求 (尝试 {attempt+1}/{max_retries}): {method} {target_url[:80]}...")
                response = await super().request(method, target_url, **kwargs)
                logger.info(f"✅ 请求成功: {response.status_code}")
                return response
            
            except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as e:
                last_error = e
                logger.warning(f"⚠️ 请求失败 (尝试 {attempt+1}/{max_retries}): {e}")
                
                if attempt < max_retries - 1:
                    delay = retry_delay * (2 ** attempt)
                    logger.info(f"⏳ 等待 {delay} 秒后重试...")
                    await asyncio.sleep(delay)
        
        logger.error(f"❌ 请求最终失败: {last_error}")
        raise last_error
    
    # 便捷方法
    async def get(self, url: str, **kwargs):
        return await self.request("GET", url, **kwargs)
    
    async def post(self, url: str, **kwargs):
        return await self.request("POST", url, **kwargs)
    
    async def put(self, url: str, **kwargs):
        return await self.request("PUT", url, **kwargs)
    
    async def delete(self, url: str, **kwargs):
        return await self.request("DELETE", url, **kwargs)
    
    @classmethod
    def clear_dns_cache(cls):
        """清空 DNS 缓存"""
        if cls._dns_cache:
            cls._dns_cache.clear()
    
    @classmethod
    def cleanup_expired_dns(cls):
        """清理过期 DNS 缓存"""
        if cls._dns_cache:
            return cls._dns_cache.cleanup_expired()
        return 0
    
    @classmethod
    def get_dns_stats(cls) -> dict:
        """获取 DNS 缓存统计"""
        if cls._dns_cache:
            return cls._dns_cache.get_stats()
        return {"total_cached": 0, "valid_entries": 0, "expired_entries": 0, "domains": {}}
