"""
S3 Upload Service for Find My Dog image uploads.

Provides presigned URL generation for secure, direct-to-S3 uploads.
Uses IRSA (IAM Roles for Service Accounts) for AWS credentials.
"""
import logging
import uuid
from typing import Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class PresignedUploadResponse:
    """Response from presigned URL generation."""
    upload_url: str          # Presigned PUT URL for upload
    photo_key: str           # S3 object key
    public_url: Optional[str] = None  # Public URL if bucket is public (usually None)
    get_url: Optional[str] = None     # Presigned GET URL for retrieval
    expires_in: int = 3600   # URL expiry in seconds


class S3UploadError(Exception):
    """Custom exception for S3 upload errors."""
    pass


class S3UploadService:
    """
    Service for generating presigned URLs for S3 uploads.
    
    Security features:
    - Validates file type (content-type)
    - Enforces max file size (via content-length condition)
    - Scopes uploads to user-specific prefix: s3://{bucket}/find-my-dog/{user_sub}/
    - Uses IRSA for credentials (no long-lived keys)
    """
    
    def __init__(self):
        """Initialize S3 client with IRSA credentials."""
        if not settings.is_s3_upload_configured():
            logger.warning("S3 upload not configured. Set S3_UPLOAD_BUCKET environment variable.")
            self._client = None
            return
        
        # Configure boto3 with retries and timeouts
        boto_config = BotoConfig(
            region_name=settings.aws_region,
            signature_version='s3v4',
            retries={'max_attempts': 3, 'mode': 'standard'},
            connect_timeout=5,
            read_timeout=10
        )
        
        # Create S3 client - uses IRSA credentials automatically via AWS SDK
        self._client = boto3.client('s3', config=boto_config)
        self._bucket = settings.s3_upload_bucket
        self._prefix = settings.s3_upload_prefix
        
        logger.info(f"S3 upload service initialized: bucket={self._bucket}, prefix={self._prefix}")
    
    @property
    def is_configured(self) -> bool:
        """Check if S3 upload is properly configured."""
        return self._client is not None and self._bucket is not None
    
    def validate_content_type(self, content_type: str) -> Tuple[bool, str]:
        """
        Validate content type against allowed types.
        
        Args:
            content_type: MIME type to validate
            
        Returns:
            (is_valid, error_message)
        """
        allowed_types = settings.get_s3_allowed_content_types()
        
        if content_type not in allowed_types:
            return False, f"Invalid content type: {content_type}. Allowed: {', '.join(allowed_types)}"
        
        return True, ""
    
    def validate_file_size(self, file_size: int) -> Tuple[bool, str]:
        """
        Validate file size against max allowed.
        
        Args:
            file_size: File size in bytes
            
        Returns:
            (is_valid, error_message)
        """
        max_size = settings.get_s3_max_size_bytes()
        
        if file_size > max_size:
            max_mb = settings.s3_upload_max_size_mb
            return False, f"File too large: {file_size} bytes. Maximum: {max_mb}MB ({max_size} bytes)"
        
        if file_size <= 0:
            return False, "File size must be positive"
        
        return True, ""
    
    def generate_object_key(self, user_sub: str, content_type: str) -> str:
        """
        Generate a unique S3 object key for the upload.
        
        Format: {prefix}/{user_sub}/{timestamp}_{uuid}.{extension}
        
        Args:
            user_sub: Cognito user sub (unique identifier)
            content_type: MIME type for determining extension
            
        Returns:
            S3 object key
        """
        # Map content type to extension
        extensions = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
        }
        ext = extensions.get(content_type, "jpg")
        
        # Generate unique filename
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        filename = f"{timestamp}_{unique_id}.{ext}"
        
        # Construct full key
        return f"{self._prefix}/{user_sub}/{filename}"
    
    def generate_object_key_anonymous(self, content_type: str) -> str:
        """
        Generate a unique S3 object key for anonymous upload (Phase 2; no user_sub).
        Format: reports/anonymous/{uuid}.{ext}
        """
        extensions = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
        }
        ext = extensions.get(content_type, "jpg")
        unique_id = str(uuid.uuid4())
        prefix = getattr(settings, "s3_upload_anonymous_prefix", "reports/anonymous")
        return f"{prefix}/{unique_id}.{ext}"
    
    async def create_presigned_upload_anonymous(
        self,
        content_type: str,
        file_size: int,
        filename: Optional[str] = None,
    ) -> PresignedUploadResponse:
        """
        Create a presigned URL for anonymous upload (Phase 2; no JWT).
        Key format: reports/anonymous/{uuid}.{ext}
        """
        if not self.is_configured:
            raise S3UploadError("S3 upload not configured")
        
        is_valid, error = self.validate_content_type(content_type)
        if not is_valid:
            raise S3UploadError(error)
        
        is_valid, error = self.validate_file_size(file_size)
        if not is_valid:
            raise S3UploadError(error)
        
        object_key = self.generate_object_key_anonymous(content_type)
        
        try:
            upload_url = self._client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": self._bucket,
                    "Key": object_key,
                    "ContentType": content_type,
                },
                ExpiresIn=settings.s3_presign_expiry_seconds,
                HttpMethod="PUT",
            )
            get_url = self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": object_key},
                ExpiresIn=settings.s3_get_url_expiry_seconds,
            )
            logger.info(f"Generated anonymous presigned upload key={object_key}")
            return PresignedUploadResponse(
                upload_url=upload_url,
                photo_key=object_key,
                get_url=get_url,
                expires_in=settings.s3_presign_expiry_seconds,
            )
        except ClientError as e:
            logger.error(f"S3 presign error: {e}")
            raise S3UploadError(f"Failed to generate presigned URL: {str(e)}")
    
    async def create_presigned_upload(
        self,
        user_sub: str,
        content_type: str,
        file_size: int,
        filename: Optional[str] = None
    ) -> PresignedUploadResponse:
        """
        Create a presigned URL for uploading a file to S3.
        
        Args:
            user_sub: Cognito user sub for path scoping
            content_type: MIME type of the file
            file_size: Expected file size in bytes
            filename: Optional original filename (for metadata)
            
        Returns:
            PresignedUploadResponse with upload URL and object key
            
        Raises:
            S3UploadError: If validation fails or S3 operation fails
        """
        if not self.is_configured:
            raise S3UploadError("S3 upload not configured")
        
        # SECURITY: Validate user_sub to prevent anonymous/invalid uploads
        # Cognito user subs are UUIDs (36 chars), require minimum 20 chars
        invalid_subs = {"anonymous", "guest", "public", "unknown", "null", "undefined", ""}
        if not user_sub or user_sub.lower() in invalid_subs or len(user_sub) < 20:
            logger.warning(f"S3 upload rejected: invalid user_sub (len={len(user_sub) if user_sub else 0})")
            raise S3UploadError(f"Invalid user identity: user_sub must be a valid Cognito user ID")
        
        # Validate content type
        is_valid, error = self.validate_content_type(content_type)
        if not is_valid:
            raise S3UploadError(error)
        
        # Validate file size
        is_valid, error = self.validate_file_size(file_size)
        if not is_valid:
            raise S3UploadError(error)
        
        # Generate object key
        object_key = self.generate_object_key(user_sub, content_type)
        
        try:
            # Generate presigned PUT URL
            # Note: Only include ContentType in signed params
            # ContentLength and Metadata are removed to avoid signature mismatch errors
            upload_url = self._client.generate_presigned_url(
                'put_object',
                Params={
                    'Bucket': self._bucket,
                    'Key': object_key,
                    'ContentType': content_type,
                },
                ExpiresIn=settings.s3_presign_expiry_seconds,
                HttpMethod='PUT'
            )
            
            # Generate presigned GET URL for retrieval (longer expiry for display)
            get_url = self._client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self._bucket,
                    'Key': object_key,
                },
                ExpiresIn=settings.s3_get_url_expiry_seconds,
            )
            
            logger.info(f"Generated presigned upload URL for user {user_sub[:8]}... key={object_key}")
            
            return PresignedUploadResponse(
                upload_url=upload_url,
                photo_key=object_key,
                get_url=get_url,
                expires_in=settings.s3_presign_expiry_seconds
            )
            
        except ClientError as e:
            logger.error(f"S3 presign error: {e}")
            raise S3UploadError(f"Failed to generate presigned URL: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected S3 error: {e}")
            raise S3UploadError(f"S3 operation failed: {str(e)}")
    
    def get_presigned_get_url(self, object_key: str, expiry_seconds: Optional[int] = None) -> str:
        """
        Generate a presigned GET URL for an existing object.
        
        Args:
            object_key: S3 object key
            expiry_seconds: URL expiry (default: s3_get_url_expiry_seconds, 24 hours)
            
        Returns:
            Presigned GET URL
        """
        if not self.is_configured:
            raise S3UploadError("S3 upload not configured")
        
        expiry = expiry_seconds or settings.s3_get_url_expiry_seconds
        
        try:
            return self._client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self._bucket,
                    'Key': object_key,
                },
                ExpiresIn=expiry
            )
        except ClientError as e:
            logger.error(f"S3 presign GET error: {e}")
            raise S3UploadError(f"Failed to generate GET URL: {str(e)}")


# Global service instance (lazy initialization)
_s3_upload_service: Optional[S3UploadService] = None


def get_s3_upload_service() -> S3UploadService:
    """Get or create the S3 upload service instance."""
    global _s3_upload_service
    if _s3_upload_service is None:
        _s3_upload_service = S3UploadService()
    return _s3_upload_service
