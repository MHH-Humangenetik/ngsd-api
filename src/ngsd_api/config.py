from pydantic_settings import BaseSettings


class NgsdSettings(BaseSettings):
    """Database connection settings for NGSD."""

    host: str
    port: int = 3306
    database: str = "ngsd"
    user: str
    password: str
    projects_base: str | None = None

    model_config = {"env_prefix": "NGSD_", "env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}
