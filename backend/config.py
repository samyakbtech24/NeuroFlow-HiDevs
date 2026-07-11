from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, computed_field

class Settings(BaseSettings):
    """
    Application settings loaded from environment variables and an optional .env file.
    Every configuration parameter is typed and documented.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Database Configuration
    postgres_user: str = Field(
        default="neuroflow", 
        description="Database username for PostgreSQL connection"
    )
    postgres_password: str = Field(
        default="neuroflow_secure_pwd", 
        description="Database password for PostgreSQL connection"
    )
    postgres_db: str = Field(
        default="neuroflow", 
        description="Database name for PostgreSQL connection"
    )
    postgres_host: str = Field(
        default="postgres", 
        description="Host address of the PostgreSQL database server"
    )
    postgres_port: int = Field(
        default=5432, 
        description="Port number of the PostgreSQL database server"
    )

    # Redis Configuration
    redis_host: str = Field(
        default="redis", 
        description="Host address of the Redis cache server"
    )
    redis_port: int = Field(
        default=6379, 
        description="Port number of the Redis cache server"
    )
    redis_password: str = Field(
        default="redis_secure_pwd", 
        description="Password for Redis authentication"
    )

    # MLflow Configuration
    mlflow_tracking_uri: str = Field(
        default="http://mlflow:5000", 
        description="Tracking URI for MLflow experiment server"
    )

    # Jaeger / OpenTelemetry Configuration
    otel_service_name: str = Field(
        default="neuroflow-api", 
        description="Name of the service reported to OpenTelemetry traces"
    )
    otel_exporter_otlp_endpoint: str = Field(
        default="http://jaeger:4317", 
        description="OTLP collector endpoint (gRPC) for Jaeger"
    )

    @computed_field
    @property
    def database_url(self) -> str:
        """Constructs the asyncpg PostgreSQL connection DSN."""
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    @computed_field
    @property
    def redis_url(self) -> str:
        """Constructs the Redis connection URL."""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/0"
        return f"redis://{self.redis_host}:{self.redis_port}/0"

# Instantiated settings object
settings = Settings()
