from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def test_db_connection(db_url: str) -> bool | str:
    """测试数据库连接是否可用

    参数:
        db_url: 数据库连接 URL

    返回:
        bool | str: 连接成功返回 True，失败返回错误信息
    """
    engine = None
    try:
        engine = create_async_engine(db_url)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        return str(e)
    finally:
        if engine is not None:
            await engine.dispose()
