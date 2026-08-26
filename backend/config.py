"""Central configuration, loaded from environment / .env."""
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict

# Mirrors ml_engine/taxonomy.py, which is the source of truth. The two services are
# separate deployment units and cannot import from each other, so this list must be
# changed alongside it -- the /health endpoint exposes it for cross-checking.
LAND_COVER_CLASSES: List[str] = [
    "built_up",
    "road",
    "water",
    "vegetation",
    "cropland",
    "bare_soil",
    "sand",
]

# 10 m VNIR + 20 m SWIR bands resampled onto the 10 m grid -> B = 6
INPUT_BANDS: List[str] = ["B02", "B03", "B04", "B08", "B11", "B12"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:3000"

    postgres_user: str = "srm"
    postgres_password: str = "srm_dev_password"
    postgres_db: str = "srm"
    postgres_host: str = "postgis"
    postgres_port: int = 5432

    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"

    cog_storage_dir: str = "/data/cogs"
    data_cache_dir: str = "/data/cache"
    tensor_exchange_dir: str = "/data/tensors"

    stac_endpoint: str = "https://planetarycomputer.microsoft.com/api/stac/v1"
    stac_collection: str = "sentinel-2-l2a"
    stac_timeout_seconds: float = 3.0
    max_cloud_cover: float = 10.0
    offline_mode: bool = False

    sync_mode: bool = False
    scale_factor: int = 4
    titiler_base_url: str = "http://localhost:8001"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
