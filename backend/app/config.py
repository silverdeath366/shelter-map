"""
Application configuration using Pydantic Settings.
Supports environment variables and AWS Secrets Manager (via CSI driver).
"""
from pydantic_settings import BaseSettings
from typing import Optional, List, Literal
from enum import Enum
import os


class AuthMode(str, Enum):
    """Authentication mode for the API."""
    DEV_OPEN = "dev_open"           # Allow all requests (only if ENV != production)
    SERVICE_API_KEY = "service_api_key"  # Require valid API key
    USER_JWT = "user_jwt"           # Require valid JWT token
    COMBINED = "combined"           # Require either API key or JWT


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # Environment Configuration
    env: str = "development"  # development, staging, production
    
    # Authentication Mode
    auth_mode: str = "service_api_key"  # dev_open, service_api_key, user_jwt, combined
    
    # JWT Configuration (for user_jwt and combined modes)
    jwt_secret: Optional[str] = None
    jwt_algorithm: str = "HS256"
    jwt_issuer: Optional[str] = None
    jwt_audience: Optional[str] = None
    
    # Database Configuration
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "geojson_db"
    db_user: str = "postgres"
    db_password: str = ""
    db_sslmode: str = "prefer"
    db_pool_min: int = 2
    db_pool_max: int = 10
    
    # Application Configuration
    app_host: str = "0.0.0.0"
    app_port: int = 8091
    log_level: str = "INFO"
    
    # API Authentication
    api_keys: Optional[str] = None  # Comma-separated list of API keys
    
    # Security Configuration
    max_request_size: int = 10485760  # 10MB in bytes
    max_file_size: int = 52428800  # 50MB in bytes
    rate_limit: int = 60  # requests per minute

    # CityGuard (GPS ping) limits – must come from env in production
    cityguard_request_timeout_s: float = 3.0  # Request timeout for /v1/cityguard
    cityguard_db_statement_timeout_s: int = 2  # PostgreSQL statement_timeout for CityGuard queries
    cityguard_max_body_bytes: int = 2048  # Max request body size for CityGuard (2KB)
    
    # Redis Configuration (optional, for distributed rate limiting)
    redis_host: Optional[str] = None
    redis_port: int = 6379
    redis_password: Optional[str] = None
    redis_db: int = 0
    redis_enabled: bool = False  # Set to True to enable Redis-based rate limiting
    
    # CloudWatch Logging (optional)
    cloudwatch_log_group: Optional[str] = None
    cloudwatch_log_stream: Optional[str] = None
    
    # AWS Configuration
    aws_region: str = "us-east-2"
    
    # CORS Configuration
    cors_allowed_origins: str = "*"  # Comma-separated origins, or "*" for all (dev only)
    cors_allow_credentials: bool = True
    cors_allow_methods: str = "GET,POST,PUT,DELETE,OPTIONS"
    cors_allow_headers: str = "Content-Type,Authorization,X-API-Key,X-Requested-With"
    
    # S3 Configuration (for Find My Dog image uploads)
    s3_upload_bucket: Optional[str] = None  # S3 bucket for image uploads
    s3_upload_prefix: str = "find-my-dog"   # Prefix for authenticated uploads (find-my-dog/{user_sub}/)
    s3_upload_anonymous_prefix: str = "reports/anonymous"  # Prefix for anonymous uploads (Phase 2; no auth yet)
    s3_upload_max_size_mb: int = 5          # Max file size in MB (enforced at presign and confirm)
    s3_presign_expiry_seconds: int = 600    # Presigned PUT URL expiry (5-10 min; default 10 min)
    s3_get_url_expiry_seconds: int = 86400  # Presigned GET URL expiry (24 hours for display)
    s3_allowed_content_types: str = "image/jpeg,image/png,image/webp"  # Comma-separated
    
    # Cognito Configuration
    cognito_region: Optional[str] = None
    cognito_user_pool_id: Optional[str] = None
    cognito_client_id: Optional[str] = None

    # AWS deployment (optional; may appear in .env)
    aws_account_id: Optional[str] = None
    ecr_repository_name: Optional[str] = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        
        # Map environment variables to settings
        fields = {
            "env": {"env": "ENV"},
            "auth_mode": {"env": "AUTH_MODE"},
            "jwt_secret": {"env": "JWT_SECRET"},
            "jwt_algorithm": {"env": "JWT_ALGORITHM"},
            "jwt_issuer": {"env": "JWT_ISSUER"},
            "jwt_audience": {"env": "JWT_AUDIENCE"},
            "db_host": {"env": "DB_HOST"},
            "db_port": {"env": "DB_PORT"},
            "db_name": {"env": "DB_NAME"},
            "db_user": {"env": "DB_USER"},
            "db_password": {"env": "DB_PASSWORD"},
            "db_sslmode": {"env": "DB_SSLMODE"},
            "db_pool_min": {"env": "DB_POOL_MIN"},
            "db_pool_max": {"env": "DB_POOL_MAX"},
            "app_host": {"env": "APP_HOST"},
            "app_port": {"env": "APP_PORT"},
            "log_level": {"env": "LOG_LEVEL"},
            "api_keys": {"env": "API_KEYS"},
            "max_request_size": {"env": "MAX_REQUEST_SIZE"},
            "max_file_size": {"env": "MAX_FILE_SIZE"},
            "rate_limit": {"env": "RATE_LIMIT"},
            "cityguard_request_timeout_s": {"env": "CITYGUARD_REQUEST_TIMEOUT_S"},
            "cityguard_db_statement_timeout_s": {"env": "CITYGUARD_DB_STATEMENT_TIMEOUT_S"},
            "cityguard_max_body_bytes": {"env": "CITYGUARD_MAX_BODY_BYTES"},
            "redis_host": {"env": "REDIS_HOST"},
            "redis_port": {"env": "REDIS_PORT"},
            "redis_password": {"env": "REDIS_PASSWORD"},
            "redis_db": {"env": "REDIS_DB"},
            "redis_enabled": {"env": "REDIS_ENABLED"},
            "cloudwatch_log_group": {"env": "CLOUDWATCH_LOG_GROUP"},
            "cloudwatch_log_stream": {"env": "CLOUDWATCH_LOG_STREAM"},
            "aws_region": {"env": "AWS_REGION"},
            "cognito_region": {"env": "COGNITO_REGION"},
            "cognito_user_pool_id": {"env": "COGNITO_USER_POOL_ID"},
            "cognito_client_id": {"env": "COGNITO_CLIENT_ID"},
            "s3_upload_bucket": {"env": "S3_UPLOAD_BUCKET"},
            "s3_upload_prefix": {"env": "S3_UPLOAD_PREFIX"},
            "s3_upload_anonymous_prefix": {"env": "S3_UPLOAD_ANONYMOUS_PREFIX"},
            "s3_upload_max_size_mb": {"env": "S3_UPLOAD_MAX_SIZE_MB"},
            "s3_presign_expiry_seconds": {"env": "S3_PRESIGN_EXPIRY_SECONDS"},
            "s3_get_url_expiry_seconds": {"env": "S3_GET_URL_EXPIRY_SECONDS"},
            "s3_allowed_content_types": {"env": "S3_ALLOWED_CONTENT_TYPES"},
            "cors_allowed_origins": {"env": "CORS_ALLOWED_ORIGINS"},
            "cors_allow_credentials": {"env": "CORS_ALLOW_CREDENTIALS"},
            "cors_allow_methods": {"env": "CORS_ALLOW_METHODS"},
            "cors_allow_headers": {"env": "CORS_ALLOW_HEADERS"},
            "aws_account_id": {"env": "AWS_ACCOUNT_ID"},
            "ecr_repository_name": {"env": "ECR_REPOSITORY_NAME"},
        }
    
    def get_api_keys_list(self) -> List[str]:
        """Parse comma-separated API keys into a list."""
        if not self.api_keys:
            return []
        return [key.strip() for key in self.api_keys.split(",") if key.strip()]
    
    def get_database_url(self) -> str:
        """Construct PostgreSQL connection URL."""
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
            f"?ssl={self.db_sslmode}"
        )
    
    def get_redis_url(self) -> Optional[str]:
        """Construct Redis connection URL if enabled."""
        if not self.redis_enabled or not self.redis_host:
            return None
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"
    
    def get_auth_mode(self) -> AuthMode:
        """Get the validated authentication mode."""
        try:
            return AuthMode(self.auth_mode.lower())
        except ValueError:
            # Default to strictest mode if invalid
            return AuthMode.SERVICE_API_KEY
    
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.env.lower() == "production"
    
    def validate_auth_config(self) -> tuple[bool, str]:
        """
        Validate authentication configuration.
        Returns (is_valid, error_message).
        
        STRICT MODE VALIDATION:
        - dev_open: ONLY allowed when ENV != production (fail-fast)
        - service_api_key: Requires API_KEYS (no optional auth)
        - user_jwt: Requires JWT_SECRET or Cognito config (no optional auth)
        - combined: Requires both API_KEYS and JWT config (no optional auth)
        """
        auth_mode = self.get_auth_mode()
        
        # STRICT: dev_open is ONLY allowed in non-production
        if auth_mode == AuthMode.DEV_OPEN:
            if self.is_production():
                return False, (
                    "SECURITY VIOLATION: AUTH_MODE=dev_open is FORBIDDEN in production. "
                    "This mode allows unauthenticated access. Set AUTH_MODE to service_api_key, "
                    "user_jwt, or combined for production deployments."
                )
        
        # STRICT: service_api_key and combined REQUIRE API keys configured
        if auth_mode in (AuthMode.SERVICE_API_KEY, AuthMode.COMBINED):
            api_keys = self.get_api_keys_list()
            if not api_keys:
                return False, (
                    f"STRICT AUTH: AUTH_MODE={auth_mode.value} requires API_KEYS environment "
                    "variable to be set with at least one valid key. No optional auth is allowed."
                )
            # Validate no empty keys in the list
            if any(len(key) < 16 for key in api_keys):
                return False, (
                    f"STRICT AUTH: API_KEYS contains invalid keys. All keys must be at least "
                    "16 characters long for security."
                )
        
        # STRICT: user_jwt and combined REQUIRE JWT configuration
        if auth_mode in (AuthMode.USER_JWT, AuthMode.COMBINED):
            has_jwt_secret = bool(self.jwt_secret)
            has_cognito = self.is_cognito_configured()
            
            if not has_jwt_secret and not has_cognito:
                return False, (
                    f"STRICT AUTH: AUTH_MODE={auth_mode.value} requires JWT verification config. "
                    "Set either JWT_SECRET (for HS256) or Cognito config "
                    "(COGNITO_REGION, COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID) for RS256/JWKS. "
                    "No optional auth is allowed."
                )
            
            # Validate JWT_SECRET minimum length if provided
            if has_jwt_secret and len(self.jwt_secret) < 32:
                return False, (
                    "STRICT AUTH: JWT_SECRET must be at least 32 characters for security. "
                    "Use a cryptographically secure random string."
                )
        
        return True, ""
    
    def get_auth_mode_description(self) -> str:
        """Get human-readable description of current auth mode requirements."""
        auth_mode = self.get_auth_mode()
        descriptions = {
            AuthMode.DEV_OPEN: "OPEN ACCESS (no authentication required) - DEVELOPMENT ONLY",
            AuthMode.SERVICE_API_KEY: "STRICT: Valid X-API-Key header REQUIRED for all requests",
            AuthMode.USER_JWT: "STRICT: Valid JWT Bearer token REQUIRED for all requests",
            AuthMode.COMBINED: "STRICT: Valid X-API-Key OR JWT Bearer token REQUIRED for all requests",
        }
        return descriptions.get(auth_mode, "UNKNOWN")
    
    def requires_api_key(self) -> bool:
        """Check if current auth mode requires API key validation."""
        return self.get_auth_mode() in (AuthMode.SERVICE_API_KEY, AuthMode.COMBINED)
    
    def requires_jwt(self) -> bool:
        """Check if current auth mode requires JWT validation."""
        return self.get_auth_mode() in (AuthMode.USER_JWT, AuthMode.COMBINED)
    
    def allows_unauthenticated(self) -> bool:
        """Check if current auth mode allows unauthenticated requests."""
        return self.get_auth_mode() == AuthMode.DEV_OPEN and not self.is_production()
    
    def get_cognito_jwks_url(self) -> Optional[str]:
        """Get the Cognito JWKS URL for token verification."""
        if not self.cognito_region or not self.cognito_user_pool_id:
            return None
        return (
            f"https://cognito-idp.{self.cognito_region}.amazonaws.com/"
            f"{self.cognito_user_pool_id}/.well-known/jwks.json"
        )
    
    def get_cognito_issuer(self) -> Optional[str]:
        """Get the Cognito issuer URL for token verification."""
        if not self.cognito_region or not self.cognito_user_pool_id:
            return None
        return (
            f"https://cognito-idp.{self.cognito_region}.amazonaws.com/"
            f"{self.cognito_user_pool_id}"
        )
    
    def is_cognito_configured(self) -> bool:
        """Check if Cognito configuration is complete."""
        return bool(
            self.cognito_region and 
            self.cognito_user_pool_id and 
            self.cognito_client_id
        )
    
    def is_s3_upload_configured(self) -> bool:
        """Check if S3 upload configuration is complete."""
        return bool(self.s3_upload_bucket)
    
    def get_s3_allowed_content_types(self) -> List[str]:
        """Get list of allowed content types for S3 uploads."""
        return [ct.strip() for ct in self.s3_allowed_content_types.split(",") if ct.strip()]
    
    def get_s3_max_size_bytes(self) -> int:
        """Get max file size in bytes."""
        return self.s3_upload_max_size_mb * 1024 * 1024
    
    def get_cors_allowed_origins(self) -> List[str]:
        """
        Get list of allowed CORS origins.
        Returns ["*"] for wildcard, or list of specific origins.
        
        Production should use specific origins like:
        CORS_ALLOWED_ORIGINS=https://find-my-dog.example.com
        """
        if self.cors_allowed_origins.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]
    
    def get_cors_allow_methods(self) -> List[str]:
        """Get list of allowed CORS methods."""
        return [method.strip() for method in self.cors_allow_methods.split(",") if method.strip()]
    
    def get_cors_allow_headers(self) -> List[str]:
        """Get list of allowed CORS headers."""
        return [header.strip() for header in self.cors_allow_headers.split(",") if header.strip()]


# Global settings instance
settings = Settings()

