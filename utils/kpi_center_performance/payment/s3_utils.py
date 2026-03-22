# utils/kpi_center_performance/payment/s3_utils.py
"""
S3 Utilities for Payment & Collection Tab — Document Viewing.

Read-only S3 access for generating presigned URLs to view attached documents
(sale invoice files, payment receipt files) in the drill-down UI.

No upload/delete operations — this module only generates viewing URLs.

Usage:
    from .s3_utils import get_s3_manager, generate_doc_url

    # In page setup (cached singleton):
    s3 = get_s3_manager()

    # Generate URL for a single document:
    url = generate_doc_url("product-file/173552558.pdf")

    # Or as callback for payment_tab_fragment:
    payment_tab_fragment(
        ...,
        s3_url_generator=generate_doc_url,
    )

VERSION: 1.0.0
"""

import logging
from typing import Optional, Dict, List
import streamlit as st

logger = logging.getLogger(__name__)


# =============================================================================
# S3 CLIENT — Singleton via st.cache_resource
# =============================================================================

class PaymentS3Client:
    """
    Lightweight S3 client for generating presigned URLs.

    Only needs read access (s3:GetObject) to the media bucket.
    Initialized once per Streamlit session via get_s3_manager().
    """

    def __init__(self):
        """Initialize boto3 S3 client from app config."""
        import boto3
        from botocore.exceptions import ClientError
        from utils.config import config

        aws_config = config.aws_config

        required = ['access_key_id', 'secret_access_key', 'region', 'bucket_name']
        missing = [k for k in required if not aws_config.get(k)]
        if missing:
            raise ValueError(f"Missing AWS config keys: {missing}")

        self._client = boto3.client(
            's3',
            aws_access_key_id=aws_config['access_key_id'],
            aws_secret_access_key=aws_config['secret_access_key'],
            region_name=aws_config['region'],
        )
        self._bucket = aws_config['bucket_name']
        self._ClientError = ClientError

        logger.info(f"PaymentS3Client initialized for kpi_center_performance (bucket: {self._bucket})")

    # -------------------------------------------------------------------------
    # Core: Presigned URL
    # -------------------------------------------------------------------------

    def get_presigned_url(self, s3_key: str, expiration: int = 3600) -> Optional[str]:
        """
        Generate a presigned URL for viewing/downloading a file.

        Args:
            s3_key: Full S3 object key (e.g. "product-file/173552558.pdf")
            expiration: URL validity in seconds (default 1 hour)

        Returns:
            Presigned URL string, or None on error
        """
        if not s3_key:
            return None

        try:
            url = self._client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self._bucket, 'Key': s3_key},
                ExpiresIn=expiration,
            )
            return url
        except self._ClientError as e:
            logger.error(f"Presigned URL error for {s3_key}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error generating URL for {s3_key}: {e}")
            return None

    def get_presigned_urls_batch(
        self,
        s3_keys: List[str],
        expiration: int = 3600,
    ) -> Dict[str, Optional[str]]:
        """
        Generate presigned URLs for multiple files.

        Args:
            s3_keys: List of S3 keys
            expiration: URL validity in seconds

        Returns:
            Dict mapping s3_key → presigned URL (or None if failed)
        """
        return {
            key: self.get_presigned_url(key, expiration)
            for key in s3_keys
        }

    def file_exists(self, s3_key: str) -> bool:
        """Check if file exists in S3 (HEAD request)."""
        if not s3_key:
            return False
        try:
            self._client.head_object(Bucket=self._bucket, Key=s3_key)
            return True
        except self._ClientError:
            return False
        except Exception:
            return False


# =============================================================================
# SINGLETON + CONVENIENCE FUNCTIONS
# =============================================================================

@st.cache_resource
def get_s3_manager() -> Optional[PaymentS3Client]:
    """
    Get or create the singleton PaymentS3Client.

    Cached for the entire Streamlit session (st.cache_resource).
    Returns None if AWS config is missing or invalid — callers should
    handle gracefully (document links simply won't render).
    """
    try:
        return PaymentS3Client()
    except Exception as e:
        logger.warning(f"PaymentS3Client unavailable: {e}")
        return None


def generate_doc_url(s3_key: str, expiration: int = 3600) -> Optional[str]:
    """
    Convenience function — generate presigned URL using the singleton client.

    Can be passed directly as `s3_url_generator` callback:
        payment_tab_fragment(..., s3_url_generator=generate_doc_url)

    Args:
        s3_key: Full S3 object key
        expiration: URL validity in seconds

    Returns:
        Presigned URL string, or None if S3 unavailable
    """
    s3 = get_s3_manager()
    if s3 is None:
        return None
    return s3.get_presigned_url(s3_key, expiration)