from pydantic_settings import BaseSettings


class NgsdSettings(BaseSettings):
    """Database connection settings for NGSD."""

    host: str = "localhost"
    port: int = 3306
    database: str = "ngsd"
    user: str = "root"
    password: str = ""

    model_config = {"env_prefix": "NGSD_", "env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}
