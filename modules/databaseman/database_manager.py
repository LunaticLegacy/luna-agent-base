"""异步 PostgreSQL 数据库连接池管理模块。

本模块提供基于 ``asyncpg`` 的异步数据库连接池生命周期管理，
包括连接池初始化、连接获取与释放、活跃连接计数以及上下文管理器封装。

主要导出内容：
    - :class:`DBTimeoutError`: 自定义数据库连接超时异常。
    - :class:`DatabaseManager`: 数据库连接池管理器，支持 ``async with`` 安全获取连接。
"""

import asyncpg
import asyncio
from contextlib import asynccontextmanager
from typing import Optional, Any, Dict


class DBTimeoutError(TimeoutError):
    """自定义数据库超时异常。

    用于在 ``get_connection`` 等待可用连接超时时提供更具语义的异常类型，
    方便调用方区分网络/配置错误与资源耗尽导致的超时。
    """

    def __init__(self, message: str = "Database operation timed out"):
        super().__init__(message)


class DatabaseManager:
    """数据库连接池管理器。

    封装 ``asyncpg`` 连接池的创建、连接获取/释放以及优雅关闭逻辑。
    所有公开方法均为异步，避免阻塞事件循环。

    关键属性：
        connection_pool: ``asyncpg`` 连接池实例；仅在调用 ``init_pool`` 后可用。
        _active_connections: 当前已分配且尚未归还的连接数，用于泄漏排查。
    """

    def __init__(
        self,
        db_url: str,
        db_username: str,
        db_password: str,
        db_database_name: str,
        db_port: int,
        minconn: int = 1,
        maxconn: int = 20
    ):
        """初始化数据库管理器。

        Args:
            db_url: 数据库服务器地址。
            db_username: 数据库用户名。
            db_password: 数据库密码。
            db_database_name: 目标数据库名称。
            db_port: 数据库对外端口。
            minconn: 连接池最小连接数。
            maxconn: 连接池最大连接数。
        """
        self.db_url: str = db_url
        self.db_username = db_username
        self.db_password: str = db_password
        self.db_database_name: str = db_database_name
        self.db_port: int = db_port
        self.minconn: int = minconn
        self.maxconn: int = maxconn

        self.connection_pool: Optional[asyncpg.pool.Pool] = None
        # 通过计数器跟踪已分配但未释放的连接，便于在关闭时告警泄漏
        self._active_connections = 0

    async def init_pool(self) -> None:
        """异步初始化连接池。

        使用 ``asyncpg.create_pool`` 创建连接池，并清零活跃连接计数器。
        若创建失败会抛出 ``ConnectionError``，避免后续操作在无效池上进行。

        Raises:
            ConnectionError: 连接池创建失败时抛出。
        """
        print(f"Connection details - Host: {self.db_url}, Port: {self.db_port}, DB: {self.db_database_name}")
        try:
            self.connection_pool = await asyncpg.create_pool(
                user=self.db_username,
                password=self.db_password,
                database=self.db_database_name,
                host=self.db_url,
                min_size=self.minconn,
                max_size=self.maxconn,
                port=self.db_port,
                timeout=10
            )
            self._active_connections = 0
            pass
        except Exception as e:
            raise ConnectionError(f"Failed to initialize asyncpg pool: {str(e)}")

    async def get_connection(self, timeout: float = 5.0) -> asyncpg.Connection:
        """从连接池获取一个连接。

        获取后必须通过 ``release_connection`` 归还，否则会造成连接泄漏。
        建议始终配合 ``acquire()`` 上下文管理器使用，确保异常安全释放。

        Args:
            timeout: 等待可用连接的最大时长（秒）。

        Returns:
            asyncpg.Connection: 数据库连接对象。

        Raises:
            ConnectionError: 连接池未初始化时抛出。
            DBTimeoutError: 等待可用连接超时时抛出。
            EOFError: 发生其他特殊错误时抛出。
        """
        try:
            if self.connection_pool is None:
                raise ConnectionError(
                    "Connection pool is not initialized. " \
                    "Use init_pool() before get connection."
                )
            connection = await self.connection_pool.acquire(timeout=timeout)
            self._active_connections += 1
            return connection
        except asyncio.TimeoutError:
            raise DBTimeoutError(f"Timeout for {timeout} seconds without free connection.")
        except Exception as e:
            raise EOFError(f"A Special error here: {e!r}") from e

    async def release_connection(self, connection: asyncpg.Connection) -> None:
        """释放已获取的连接。

        Args:
            connection: 要归还的连接对象。
        """
        if self.connection_pool is not None:
            await self.connection_pool.release(connection)
            self._active_connections -= 1

    async def close_all_connections(self) -> None:
        """关闭连接池并清理所有资源。

        若仍有未归还的连接，会先打印警告以便排查泄漏。
        关闭操作设置 30 秒超时，防止在连接挂起时无限等待；
        即使超时也会强制将池置空，避免后续复用脏状态。

        Raises:
            asyncio.TimeoutError: 关闭操作超时时被内部捕获，不会向上传播。
        """
        if self.connection_pool is not None:
            # 在关闭前输出未释放连接数，帮助诊断连接泄漏
            print(f"WARNING: There are {self._active_connections} active connections that may not be released!")
            
            try:
                # 使用 asyncio.wait_for 设置超时
                await asyncio.wait_for(self.connection_pool.close(), timeout=30.0)
            except asyncio.TimeoutError:
                pass
                # 如果超时，我们仍然将连接池设为None
            finally:
                self.connection_pool = None
                self._active_connections = 0
    
    @asynccontextmanager
    async def acquire(self):
        """异步上下文管理器，安全获取并自动释放连接。

        封装 ``get_connection`` + ``release_connection`` 的配对逻辑，
        确保即使在执行期间发生异常，连接也能被正确归还。

        Yields:
            asyncpg.Connection: 已获取的连接对象。

        Example::
            db = DatabaseManager(...)
            await db.init_pool()
            async with db.acquire() as conn:
                ...
        """
        conn = await self.get_connection()
        try:
            yield conn
        finally:
            await self.release_connection(conn)

    def get_active_connections_count(self) -> int:
        """获取当前活跃连接数。

        Returns:
            int: 已分配且尚未归还的连接数量。
        """
        return self._active_connections


# 使用示例
async def main():
    """模块级使用示例：演示连接池初始化、查询与关闭的完整流程。"""
    db = DatabaseManager(
        db_url="127.0.0.1",
        db_username="postgres",
        db_password="lunamoon",
        db_database_name="postgres",
        db_port=12345,
        minconn=1,
        maxconn=1
    )
    await db.init_pool()

    conn = await db.get_connection()
    result: Optional[Dict[str, Any]] = await conn.fetchrow("SELECT now() as current_time")
    print(result)
    await db.release_connection(conn)

    await db.close_all_connections()


if __name__ == "__main__":
    asyncio.run(main())
