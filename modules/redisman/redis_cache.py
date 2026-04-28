"""异步 Redis 连接池管理与数据缓存模块。

本模块封装 ``redis.asyncio`` 的连接池生命周期以及键值操作，
支持 JSON / pickle 双序列化策略、自动序列化方式标记与回退，
并提供异步迭代器遍历键空间。

主要导出内容：
    - :class:`RedisManager`: Redis 连接池与数据操作管理器。
"""

import redis
import redis.asyncio as ario
from typing import Any, Optional, Dict, Union
import json
import pickle
import asyncio


class RedisManager:
    """统一管理 Redis 相关事务的类。

    提供连接池管理、数据存取、缓存操作等功能。
    所有 IO 操作均为异步，避免阻塞主事件循环。

    关键属性：
        redis_pool: ``redis.asyncio.ConnectionPool`` 实例，管理底层连接。
        redis_client: ``redis.asyncio.Redis`` 实例，对外暴露命令接口。
        host/port/db/password: 连接目标与认证信息。
        max_connections: 连接池上限。
        decode_responses: 是否自动将字节解码为字符串。
    """

    def __init__(
            self,
            host: str = "localhost",
            port: int = 6379,
            db: int = 0,
            password: Optional[str] = None,
            max_connections: int = 10,
            encoding: str = "utf-8",
            decode_responses: bool = True
        ) -> None:
        """初始化 Redis 管理器。
        
        Args:
            host: Redis 服务器地址。
            port: Redis 服务器端口。
            db: 数据库编号。
            password: 认证密码。
            max_connections: 连接池最大连接数。
            encoding: 字符编码。
            decode_responses: 是否自动解码响应。
        """
        self.redis_pool: Optional[ario.ConnectionPool] = None
        self.redis_client: Optional[ario.Redis] = None

        # redis 连接池参数
        self.host: str = host
        self.port: int = port
        self.db: int = db
        self.password: Optional[str] = password
        self.max_connections: int = max_connections
        self.encoding: str = encoding
        self.decode_responses: bool = decode_responses

    async def init_pool(self) -> None:
        """
        初始化 Redis 连接池。

        根据密码是否存在动态拼接连接 URL，并使用 ``from_url`` 创建异步连接池。
        若初始化失败会抛出异常，防止后续操作在无效客户端上执行。

        Raises:
            Exception: 底层连接池创建失败时抛出。
        """
        try:
            # 构建连接 URL
            if self.password:
                url = f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
            else:
                url = f"redis://{self.host}:{self.port}/{self.db}"
            print(f"Connection details - {url}")

            # 创建连接池
            self.redis_pool = ario.ConnectionPool.from_url(
                url,
                max_connections=self.max_connections,
                encoding=self.encoding,
                decode_responses=self.decode_responses
            )
            
            # 创建 Redis 客户端
            self.redis_client = ario.Redis(connection_pool=self.redis_pool)
        except Exception as e:
            print(f"Redis pool initialization error: {e}")
            raise

    async def ping(self) -> bool:
        """
        测试 Redis 连接。
        
        Returns:
            bool: 连接是否正常。

        Raises:
            RuntimeError: 客户端未初始化时抛出。
        """
        if not self.redis_client:
            raise RuntimeError("Redis client not initialized. Call init_pool() first.")
            
        try:
            await self.redis_client.ping()
            return True
        except Exception as e:
            print(f"Redis ping error: {e}")
            return False

    async def close_pool(self) -> None:
        """关闭 Redis 连接池并释放所有资源。

        按先客户端后连接池的顺序关闭，确保所有待发送命令已排空。
        """
        if self.redis_client:
            await self.redis_client.close()
        if self.redis_pool:
            await self.redis_pool.disconnect()
            self.redis_pool = None
        self.redis_client = None

    async def set(self, key: str, value: Any, expire: Optional[int] = None, serialize: str = "json") -> bool:
        """
        设置键值对。
        
        Args:
            key: 键。
            value: 值。
            expire: 过期时间（秒）。
            serialize: 序列化方式（"json" 或 "pickle"）。
            
        Returns:
            bool: 是否设置成功。

        Raises:
            RuntimeError: 客户端未初始化时抛出。
        """
        if not self.redis_client:
            raise RuntimeError("Redis client not initialized. Call init_pool() first.")
            
        try:
            if serialize == "json":
                # 处理不能 JSON 序列化的对象：先尝试 json，失败则回退到 pickle
                try:
                    serialized_value = json.dumps(value, ensure_ascii=False)
                except TypeError:
                    serialized_value = pickle.dumps(value)
                    # 如果使用了 pickle，则标记一下，方便 get 时自动识别
                    await self.redis_client.hset(f"__meta__:{key}", "serialize_method", "pickle")
            elif serialize == "pickle":
                serialized_value = pickle.dumps(value)
                # 标记序列化方式，便于读取端做对称处理
                await self.redis_client.hset(f"__meta__:{key}", "serialize_method", "pickle")
            else:
                serialized_value = str(value)
                
            result = await self.redis_client.set(key, serialized_value, ex=expire)
            return result
        except Exception as e:
            print(f"Redis set error: {e}")
            return False

    async def get(self, key: str, deserialize: str = "json") -> Optional[Any]:
        """
        获取键对应的值。
        
        Args:
            key: 键。
            deserialize: 反序列化方式（"json" 或 "pickle"）。
            
        Returns:
            Optional[Any]: 键对应的值；不存在则返回 None。

        Raises:
            RuntimeError: 客户端未初始化时抛出。
        """
        if not self.redis_client:
            raise RuntimeError("Redis client not initialized. Call init_pool() first.")
            
        try:
            value = await self.redis_client.get(key)
            if value is None:
                return None
                
            # 如果显式指定了反序列化方式，则按指定方式处理
            if deserialize == "json":
                return json.loads(value)
            elif deserialize == "pickle":
                return pickle.loads(value)
            else:
                # 尝试自动检测序列化方式：优先读取元数据标记，若无则默认 JSON
                try:
                    meta_key = f"__meta__:{key}"
                    serialize_method = await self.redis_client.hget(meta_key, "serialize_method")
                    
                    if serialize_method == b"pickle" or serialize_method == "pickle":
                        return pickle.loads(value)
                    else:
                        # 默认尝试 JSON
                        return json.loads(value)
                except:
                    # 如果都失败了，返回原始值，避免数据丢失
                    return value
        except Exception as e:
            print(f"Redis get error: {e}")
            return None

    async def delete(self, *keys: str) -> int:
        """
        删除一个或多个键。
        
        Args:
            keys: 要删除的键。
            
        Returns:
            int: 成功删除的键数量。

        Raises:
            RuntimeError: 客户端未初始化时抛出。
        """
        if not self.redis_client:
            raise RuntimeError("Redis client not initialized. Call init_pool() first.")
            
        try:
            return await self.redis_client.delete(*keys)
        except Exception as e:
            print(f"Redis delete error: {e}")
            return 0

    async def exists(self, *keys: str) -> int:
        """
        检查键是否存在。
        
        Args:
            keys: 要检查的键。
            
        Returns:
            int: 存在的键数量。

        Raises:
            RuntimeError: 客户端未初始化时抛出。
        """
        if not self.redis_client:
            raise RuntimeError("Redis client not initialized. Call init_pool() first.")
            
        try:
            return await self.redis_client.exists(*keys)
        except Exception as e:
            print(f"Redis exists check error: {e}")
            return 0

    async def expire(self, key: str, seconds: int) -> bool:
        """
        设置键的过期时间。
        
        Args:
            key: 键。
            seconds: 过期时间（秒）。
            
        Returns:
            bool: 是否设置成功。

        Raises:
            RuntimeError: 客户端未初始化时抛出。
        """
        if not self.redis_client:
            raise RuntimeError("Redis client not initialized. Call init_pool() first.")
            
        try:
            return await self.redis_client.expire(key, seconds)
        except Exception as e:
            print(f"Redis expire set error: {e}")
            return False

    async def scan_iter(self, pattern: str = "*"):
        """
        异步迭代匹配模式的所有键。
        
        Args:
            pattern: 匹配模式（glob 风格）。
            
        Yields:
            str: 匹配的键名。

        Raises:
            RuntimeError: 客户端未初始化时抛出。
        """
        if not self.redis_client:
            raise RuntimeError("Redis client not initialized. Call init_pool() first.")
            
        try:
            async for key in self.redis_client.scan_iter(match=pattern):
                yield key
        except Exception as e:
            print(f"Redis scan iter error: {e}")
