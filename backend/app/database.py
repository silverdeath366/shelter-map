"""
Database connection and session management.
Uses SQLAlchemy async with asyncpg for PostgreSQL/PostGIS.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool
from sqlalchemy import text
from app.config import settings
import logging

logger = logging.getLogger(__name__)

# Create async engine
# NullPool doesn't support pool_size/max_overflow, which is suitable for asyncpg
engine = create_async_engine(
    settings.get_database_url(),
    poolclass=NullPool,  # Use NullPool for asyncpg
    echo=settings.log_level == "DEBUG",
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Base class for models
Base = declarative_base()


async def get_db() -> AsyncSession:
    """
    Dependency for getting database session.
    Yields an async database session.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Initialize database connection and verify PostGIS extension."""
    try:
        async with AsyncSessionLocal() as session:
            # Check if PostGIS extension exists
            result = await session.execute(
                text("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'postgis')")
            )
            has_postgis = result.scalar()
            
            if not has_postgis:
                logger.warning("PostGIS extension not found. Please run init-db.sql")
            else:
                logger.info("PostGIS extension verified")
                
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        # Don't raise - allow service to start even if DB check fails
        # (useful for development/testing scenarios)


async def close_db():
    """Close database connections."""
    await engine.dispose()

