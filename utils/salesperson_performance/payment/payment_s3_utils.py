# utils/salesperson_performance/payment/s3_utils.py
"""
MOVED v4.1.0: S3 utilities moved to parent module.

This file re-exports from utils.salesperson_performance.s3_utils
for backward compatibility with existing imports.

New code should import directly:
    from utils.salesperson_performance.s3_utils import get_s3_manager, generate_doc_url
"""

from utils.salesperson_performance.s3_utils import (
    PaymentS3Client,
    get_s3_manager,
    generate_doc_url,
)

__all__ = [
    'PaymentS3Client',
    'get_s3_manager',
    'generate_doc_url',
]