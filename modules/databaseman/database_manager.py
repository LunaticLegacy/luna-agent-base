import asyncpg
import asyncio
from contextlib import asynccontextmanager
from typing import Optional, Any, Dict

class DBTimeoutError(TimeoutError):
    """自定义数据库超时异常。"""
    def __init__(self, message: str = "Database operation timed out"):
        super().__init__(message)

class DatabaseManager:
    """
    数据库管理器。
    - 在本管理器内，所有函数均为**异步调用**——为尽可能不阻塞IO。
    - 异步编程需要使用asyncio库。
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
        """
        初始化类。

        Args:
            db_url (str): 数据库服务器URL地址。
            db_username (str): 数据库用户名。
            db_password (str): 数据库密码。
            db_database_name (str): 数据库名。
            db_port (int): 数据库对外端口。
            minconn (int): 连接池最小连接数量。
            maxconn (int): 连接池最大连接数量。
        """
        self.db_url: str = db_url
        self.db_username = db_username
        self.db_password: str = db_password
        self.db_database_name: str = db_database_name
        self.db_port: int = db_port
        self.minconn: int = minconn
        self.maxconn: int = maxconn

        self.connection_pool: Optional[asyncpg.pool.Pool] = None
        # 添加活跃连接计数器
        self._active_connections = 0

    async def init_pool(self) -> None:
        """
        异步初始化连接池。
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
        """
        从连接池获取一个连接。
        - 在获取连接并使用完毕后，必须使用本实例内的`release_connection`函数释放连接。
            否则会造成连接泄漏（类似内存泄漏）。
        
        注意：请在try块内使用，如果等待超时，该块会抛出`TimeoutError`。

        Args:
            timeout (float): 超时等待时长（秒）
        
        Returns:
            (asyncpg.Connection): 连接对象
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
        """
        释放已获取的连接。

        Args:
            connection (asyncpg.Connection): 连接对象
        """
        if self.connection_pool is not None:
            await self.connection_pool.release(connection)
            self._active_connections -= 1

    async def close_all_connections(self) -> None:
        """
        关闭连接池。
        """
        if self.connection_pool is not None:
            # 显示当前活跃连接数
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
        """
        连接管理器。
        - **请在async with上下文中使用，例：**
        ```
        db = DatabaseManager()
        async with db.acquire() as conn:
            conn.somefunction()
        ```
        """
        conn = await self.get_connection()
        try:
            yield conn
        finally:
            await self.release_connection(conn)

    def get_active_connections_count(self) -> int:
        """
        获取当前活跃连接数。
        
        Returns:
            int: 当前活跃连接数
        """
        return self._active_connections

# 使用示例
async def main():
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