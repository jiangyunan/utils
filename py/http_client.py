import httpx
import time
from typing import Dict, Any, Optional, Tuple
from urllib.parse import urljoin
import logging
import asyncio
import re


class HttpClient:
    """
    基于 httpx 的可重用 HTTP 客户端类
    
    特性:
    - 自动重试失败的请求
    - 可配置的超时设置
    - 统一的错误处理
    - 支持 JSON 请求和响应
    - 支持请求和响应拦截器
    - 支持会话管理
    - 支持自定义基础 URL

    使用示例:
    # 创建一个基本的 HTTP 客户端
    client = HttpClient(
        base_url="https://api.example.com",
        timeout=10,
        max_retries=2
    )

    # 发送 GET 请求
    response = client.get("/users")
    print(f"状态码: {response.status_code}")
    print(f"响应内容: {response.text}")

    # 发送带参数的 GET 请求
    users = client.get_json("/users", params={"page": 1, "limit": 10})
    print(f"用户列表: {users}")

    # 发送 POST 请求
    response = client.post(
        "/users",
        json={"name": "John Doe", "email": "john@example.com"}
    )
    print(f"创建用户响应: {response.json()}")

    # 使用上下文管理器
    with HttpClient(base_url="https://api.example.com") as client:
        response = client.get("/status")
        print(f"API 状态: {response.text}")

    # 下载文件
    client.download_file("https://example.com/files/document.pdf", "document.pdf")
    """
    
    def __init__(
        self,
        base_url: str = "",
        timeout: int = 30,
        max_retries: int = 3,
        retry_delay: int = 1,
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None,
        verify_ssl: bool = True,
        http2: bool = False,
        follow_redirects: bool = True,
        proxies: Optional[str] = None,
        logger: Optional[logging.Logger] = None
    ):
        """
        初始化 HTTP 客户端
        
        参数:
            base_url (str): API 基础 URL
            timeout (int): 请求超时时间（秒）
            max_retries (int): 最大重试次数
            retry_delay (int): 重试间隔（秒）
            headers (Dict[str, str]): 默认请求头
            cookies (Dict[str, str]): 默认 cookies
            verify_ssl (bool): 是否验证 SSL 证书
            http2 (bool): 是否启用 HTTP/2
            follow_redirects (bool): 是否自动跟随重定向
            proxies (str): 代理设置，如 "http://proxy:8080
        """
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.default_headers = headers or {}
        self.default_cookies = cookies or {}
        self.verify_ssl = verify_ssl
        self.http2 = http2
        self.follow_redirects = follow_redirects
        self.proxies = proxies

        # 使用传入的 logger 或创建一个新的
        self.logger = logger or logging.getLogger(__name__)
        
        # 创建 httpx 客户端
        self.client = httpx.Client(
            timeout=timeout,
            headers=self.default_headers,
            cookies=self.default_cookies,
            verify=verify_ssl,
            http2=http2,
            follow_redirects=follow_redirects,
            proxy=proxies
        )
        
        # 请求和响应拦截器
        self.request_interceptors = []
        self.response_interceptors = []
    
    def __enter__(self):
        """支持上下文管理器模式"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文管理器时关闭客户端"""
        self.close()
    
    def close(self):
        """关闭 HTTP 客户端"""
        if self.client:
            self.client.close()
    
    def add_request_interceptor(self, interceptor):
        """
        添加请求拦截器
        
        拦截器函数应接受 (url, method, kwargs) 参数并返回修改后的 (url, method, kwargs)
        """
        self.request_interceptors.append(interceptor)
    
    def add_response_interceptor(self, interceptor):
        """
        添加响应拦截器
        
        拦截器函数应接受 (response) 参数并返回修改后的 response
        """
        self.response_interceptors.append(interceptor)
    
    def _prepare_url(self, url: str) -> str:
        """准备完整的 URL"""
        if url.startswith(('http://', 'https://')):
            return url
        return urljoin(self.base_url, url)
    
    def _apply_request_interceptors(self, url: str, method: str, kwargs: Dict[str, Any]) -> Tuple[str, str, Dict[str, Any]]:
        """应用所有请求拦截器"""
        for interceptor in self.request_interceptors:
            url, method, kwargs = interceptor(url, method, kwargs)
        return url, method, kwargs
    
    def _apply_response_interceptors(self, response: httpx.Response) -> httpx.Response:
        """应用所有响应拦截器"""
        for interceptor in self.response_interceptors:
            response = interceptor(response)
        return response
    
    def request(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        verify_ssl: Optional[bool] = None,
        follow_redirects: Optional[bool] = None,
        raise_for_status: bool = True,
        **kwargs
    ) -> httpx.Response:
        """
        发送 HTTP 请求
        
        参数:
            method (str): HTTP 方法 (GET, POST, PUT, DELETE 等)
            url (str): 请求 URL
            params (Dict[str, Any]): URL 查询参数
            data (Any): 请求体数据
            json (Dict[str, Any]): JSON 请求体
            headers (Dict[str, str]): 请求头
            cookies (Dict[str, str]): Cookies
            timeout (int): 请求超时时间（秒）
            verify_ssl (bool): 是否验证 SSL 证书
            follow_redirects (bool): 是否自动跟随重定向
            raise_for_status (bool): 是否为 HTTP 错误状态码抛出异常
            **kwargs: 传递给 httpx.request 的其他参数
            
        返回:
            httpx.Response: HTTP 响应对象
            
        抛出:
            httpx.RequestError: 请求错误
            httpx.HTTPStatusError: HTTP 状态错误（如果 raise_for_status=True）
        """
        # 准备请求参数
        full_url = self._prepare_url(url)
        request_kwargs = {
            'params': params,
            'data': data,
            'json': json,
            'headers': headers,
            'cookies': cookies,
            'timeout': timeout if timeout is not None else self.timeout,
            'follow_redirects': follow_redirects if follow_redirects is not None else self.follow_redirects,
            **kwargs
        }
        
        # 应用请求拦截器
        full_url, method, request_kwargs = self._apply_request_interceptors(full_url, method, request_kwargs)
        
        # 重试逻辑
        retries = 0
        last_error = None
        
        while retries <= self.max_retries:
            try:
                response = self.client.request(method, full_url, **request_kwargs)
                
                # 应用响应拦截器
                response = self._apply_response_interceptors(response)
                
                # 检查状态码
                if raise_for_status:
                    response.raise_for_status()
                
                return response
                
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                # 304 状态码不重试
                if e.response.status_code == 304:
                    return e.response
                last_error = e
                retries += 1
                
                # 如果达到最大重试次数，抛出最后一个错误
                if retries > self.max_retries:
                    self.logger.error(f"请求失败，已达到最大重试次数: {str(e)}")
                    raise
                
                # 记录重试信息
                self.logger.warning(f"请求失败，正在重试 ({retries}/{self.max_retries}): {str(e)}")
                
                # 重试延迟
                time.sleep(self.retry_delay)
    
    def get(self, url: str, **kwargs) -> httpx.Response:
        """发送 GET 请求"""
        return self.request('GET', url, **kwargs)
    
    def post(self, url: str, **kwargs) -> httpx.Response:
        """发送 POST 请求"""
        return self.request('POST', url, **kwargs)
    
    def put(self, url: str, **kwargs) -> httpx.Response:
        """发送 PUT 请求"""
        return self.request('PUT', url, **kwargs)
    
    def delete(self, url: str, **kwargs) -> httpx.Response:
        """发送 DELETE 请求"""
        return self.request('DELETE', url, **kwargs)
    
    def patch(self, url: str, **kwargs) -> httpx.Response:
        """发送 PATCH 请求"""
        return self.request('PATCH', url, **kwargs)
    
    def head(self, url: str, **kwargs) -> httpx.Response:
        """发送 HEAD 请求"""
        return self.request('HEAD', url, **kwargs)
    
    def options(self, url: str, **kwargs) -> httpx.Response:
        """发送 OPTIONS 请求"""
        return self.request('OPTIONS', url, **kwargs)
    
    def get_json(self, url: str, **kwargs) -> Any:
        """
        发送 GET 请求并返回 JSON 响应
        
        返回:
            Any: 解析后的 JSON 数据
        """
        response = self.get(url, **kwargs)
        return response.json()
    
    def post_json(self, url: str, json_data: Dict[str, Any], **kwargs) -> Any:
        """
        发送 JSON POST 请求并返回 JSON 响应
        
        参数:
            url (str): 请求 URL
            json_data (Dict[str, Any]): 要发送的 JSON 数据
            **kwargs: 其他请求参数
            
        返回:
            Any: 解析后的 JSON 数据
        """
        response = self.post(url, json=json_data, **kwargs)
        return response.json()
    
    def download_file(self, url: str, file_path: str, **kwargs) -> None:
        """
        下载文件并保存到指定路径
        
        参数:
            url (str): 文件 URL
            file_path (str): 保存文件的路径
            **kwargs: 其他请求参数
        """
        with self.get(url, **kwargs) as response:
            with open(file_path, 'wb') as f:
                for chunk in response.iter_bytes(chunk_size=8192):
                    f.write(chunk)
        
        self.logger.info(f"文件已下载到: {file_path}")
    
    def create_async_client(self) -> 'AsyncHttpClient':
        """
        创建具有相同配置的异步 HTTP 客户端
        
        返回:
            AsyncHttpClient: 异步 HTTP 客户端实例
        """
        from httpx import AsyncClient
        
        # 导入 AsyncHttpClient 类 (需要在文件末尾定义)
        return AsyncHttpClient(
            base_url=self.base_url,
            timeout=self.timeout,
            max_retries=self.max_retries,
            retry_delay=self.retry_delay,
            headers=self.default_headers,
            cookies=self.default_cookies,
            verify_ssl=self.verify_ssl,
            http2=self.http2,
            follow_redirects=self.follow_redirects,
            proxies=self.proxies
        )


class AsyncHttpClient:
    """
    基于 httpx 的异步 HTTP 客户端类
    
    特性与 HttpClient 类似，但支持异步操作
    """
    
    def __init__(
        self,
        base_url: str = "",
        timeout: int = 30,
        max_retries: int = 3,
        retry_delay: int = 1,
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None,
        verify_ssl: bool = True,
        http2: bool = False,
        follow_redirects: bool = True,
        proxies: Optional[str] = None
    ):
        """初始化异步 HTTP 客户端"""
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.default_headers = headers or {}
        self.default_cookies = cookies or {}
        self.verify_ssl = verify_ssl
        self.http2 = http2
        self.follow_redirects = follow_redirects
        self.proxies = proxies
        
        # 创建异步 httpx 客户端
        self.client = httpx.AsyncClient(
            timeout=timeout,
            headers=self.default_headers,
            cookies=self.default_cookies,
            verify=verify_ssl,
            http2=http2,
            follow_redirects=follow_redirects,
            proxy=proxies
        )
        
        # 请求和响应拦截器
        self.request_interceptors = []
        self.response_interceptors = []
    
    async def __aenter__(self):
        """支持异步上下文管理器模式"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """退出异步上下文管理器时关闭客户端"""
        await self.close()
    
    async def close(self):
        """关闭异步 HTTP 客户端"""
        if self.client:
            await self.client.aclose()
    
    def add_request_interceptor(self, interceptor):
        """添加请求拦截器"""
        self.request_interceptors.append(interceptor)
    
    def add_response_interceptor(self, interceptor):
        """添加响应拦截器"""
        self.response_interceptors.append(interceptor)
    
    def _prepare_url(self, url: str) -> str:
        """准备完整的 URL"""
        if url.startswith(('http://', 'https://')):
            return url
        return urljoin(self.base_url, url)
    
    def _apply_request_interceptors(self, url: str, method: str, kwargs: Dict[str, Any]) -> Tuple[str, str, Dict[str, Any]]:
        """应用所有请求拦截器"""
        for interceptor in self.request_interceptors:
            url, method, kwargs = interceptor(url, method, kwargs)
        return url, method, kwargs
    
    async def _apply_response_interceptors(self, response: httpx.Response) -> httpx.Response:
        """应用所有响应拦截器"""
        for interceptor in self.response_interceptors:
            if callable(getattr(interceptor, "__call__", None)):
                response = interceptor(response)
            elif callable(getattr(interceptor, "__await__", None)):
                response = await interceptor(response)
        return response
    
    async def request(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        verify_ssl: Optional[bool] = None,
        follow_redirects: Optional[bool] = None,
        raise_for_status: bool = True,
        **kwargs
    ) -> httpx.Response:
        """
        发送异步 HTTP 请求
        
        参数:
            method (str): HTTP 方法 (GET, POST, PUT, DELETE 等)
            url (str): 请求 URL
            params (Dict[str, Any]): URL 查询参数
            data (Any): 请求体数据
            json (Dict[str, Any]): JSON 请求体
            headers (Dict[str, str]): 请求头
            cookies (Dict[str, str]): Cookies
            timeout (int): 请求超时时间（秒）
            verify_ssl (bool): 是否验证 SSL 证书
            follow_redirects (bool): 是否自动跟随重定向
            raise_for_status (bool): 是否为 HTTP 错误状态码抛出异常
            **kwargs: 传递给 httpx.request 的其他参数
            
        返回:
            httpx.Response: HTTP 响应对象
            
        抛出:
            httpx.RequestError: 请求错误
            httpx.HTTPStatusError: HTTP 状态错误（如果 raise_for_status=True）
        """
        # 准备请求参数
        full_url = self._prepare_url(url)
        request_kwargs = {
            'params': params,
            'data': data,
            'json': json,
            'headers': headers,
            'cookies': cookies,
            'timeout': timeout if timeout is not None else self.timeout,
            'follow_redirects': follow_redirects if follow_redirects is not None else self.follow_redirects,
            **kwargs
        }
        
        # 应用请求拦截器
        full_url, method, request_kwargs = self._apply_request_interceptors(full_url, method, request_kwargs)
        
        # 重试逻辑
        retries = 0
        last_error = None
        
        while retries <= self.max_retries:
            try:
                response = await self.client.request(method, full_url, **request_kwargs)
                
                # 应用响应拦截器
                response = await self._apply_response_interceptors(response)
                
                # 检查状态码
                if raise_for_status:
                    response.raise_for_status()
                
                return response
                
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                # 304 状态码不重试
                if e.response.status_code == 304:
                    return e.response
                last_error = e
                retries += 1
                
                # 如果达到最大重试次数，抛出最后一个错误
                if retries > self.max_retries:
                    self.logger.error(f"请求失败，已达到最大重试次数: {str(e)}")
                    raise
                
                # 记录重试信息
                self.logger.warning(f"请求失败，正在重试 ({retries}/{self.max_retries}): {str(e)}")
                
                # 重试延迟
                await asyncio.sleep(self.retry_delay)
    
    async def get(self, url: str, **kwargs) -> httpx.Response:
        """发送异步 GET 请求"""
        return await self.request('GET', url, **kwargs)
    
    async def post(self, url: str, **kwargs) -> httpx.Response:
        """发送异步 POST 请求"""
        return await self.request('POST', url, **kwargs)
    
    async def put(self, url: str, **kwargs) -> httpx.Response:
        """发送异步 PUT 请求"""
        return await self.request('PUT', url, **kwargs)
    
    async def delete(self, url: str, **kwargs) -> httpx.Response:
        """发送异步 DELETE 请求"""
        return await self.request('DELETE', url, **kwargs)
    
    async def patch(self, url: str, **kwargs) -> httpx.Response:
        """发送异步 PATCH 请求"""
        return await self.request('PATCH', url, **kwargs)
    
    async def head(self, url: str, **kwargs) -> httpx.Response:
        """发送异步 HEAD 请求"""
        return await self.request('HEAD', url, **kwargs)
    
    async def options(self, url: str, **kwargs) -> httpx.Response:
        """发送异步 OPTIONS 请求"""
        return await self.request('OPTIONS', url, **kwargs)
    
    async def get_json(self, url: str, **kwargs) -> Any:
        """
        发送异步 GET 请求并返回 JSON 响应
        
        返回:
            Any: 解析后的 JSON 数据
        """
        response = await self.get(url, **kwargs)
        return response.json()
    
    async def post_json(self, url: str, json_data: Dict[str, Any], **kwargs) -> Any:
        """
        发送异步 JSON POST 请求并返回 JSON 响应
        
        参数:
            url (str): 请求 URL
            json_data (Dict[str, Any]): 要发送的 JSON 数据
            **kwargs: 其他请求参数
            
        返回:
            Any: 解析后的 JSON 数据
        """
        response = await self.post(url, json=json_data, **kwargs)
        return response.json()
    
    async def download_file(self, url: str, file_path: str, **kwargs) -> None:
        """
        异步下载文件并保存到指定路径
        
        参数:
            url (str): 文件 URL
            file_path (str): 保存文件的路径
            **kwargs: 其他请求参数
        """
        async with self.get(url, **kwargs) as response:
            with open(file_path, 'wb') as f:
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    f.write(chunk)
        
        self.logger.info(f"文件已下载到: {file_path}")

def normalize_etag(etag: str) -> str:
    """
    标准化 ETag 值，去掉结尾以 "-" 开头的任意字符串
    
    Args:
        etag: 原始 ETag 值，如 "W/\"abc123-tr\"" 或 "\"abc123-xyz\""
    
    Returns:
        标准化后的 ETag 值，如 "W/\"abc123\"" 或 "\"abc123\""
    """
    if not etag:
        return etag
    
    # 处理弱 ETag (以 W/ 开头)
    is_weak = etag.startswith('W/')
    
    # 提取实际的 ETag 值 (去掉 W/ 和引号)
    if is_weak:
        etag_value = etag[2:].strip('"')
    else:
        etag_value = etag.strip('"')
    
    # 使用正则表达式去掉结尾以 "-" 开头的字符串
    # 这会匹配字符串末尾的 "-" 及其后面的所有字符
    etag_value = re.sub(r'-[^-]*$', '', etag_value)
    
    # 重新组装 ETag
    if is_weak:
        return f'W/"{etag_value}"'
    else:
        return f'"{etag_value}"'