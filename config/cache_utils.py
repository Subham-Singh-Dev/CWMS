"""Cache utilities for safe pattern deletion and helpers.

Provides a safe `delete_pattern(pattern)` function that works whether
`cache.delete_pattern` is available (django-redis) or not. Falls back to
using redis SCAN/DELETE via `django_redis.get_redis_connection` when needed.
"""
from typing import Optional, Iterable, Dict
import logging

from django.conf import settings
from django.core.cache import cache
from django.core.cache import caches

# Use a dedicated logger so production can route it to file/Sentry separately
logger = logging.getLogger('cwms.cache')


def _build_full_pattern(pattern: str) -> str:
    """Construct full redis key pattern including KEY_PREFIX and VERSION.

    Observed key format: {KEY_PREFIX}:{VERSION}:{key}
    """
    key_prefix = None
    version = None
    try:
        cfg = settings.CACHES.get('default', {})
        key_prefix = cfg.get('KEY_PREFIX')
        version = cfg.get('VERSION', None)
    except Exception:
        key_prefix = None
        version = None

    # If VERSION not configured in settings, try to read common default 1
    if version is None:
        version = 1

    if key_prefix:
        full = f"{key_prefix}:{version}:{pattern}"
    else:
        full = pattern
    return full


def delete_patterns(patterns: Iterable[str]) -> Dict[str, Optional[int]]:
    """Delete multiple patterns in one Redis connection.

    Returns a dict mapping pattern -> number of keys deleted (or None).
    """
    # Try native implementation if available for the cache object
    native = getattr(cache, 'delete_pattern', None)
    results = {}
    if callable(native):
        try:
            for p in patterns:
                try:
                    results[p] = native(p)
                except Exception as exc:
                    logger.error("native delete_pattern failed for %s: %s", p, exc)
                    results[p] = None
            return results
        except Exception:
            # fallback to manual approach
            logger.warning('native delete_pattern batch failed, falling back')

    # If cache backend is DummyCache, skip redis operations entirely
    try:
        from django.core.cache import caches
        backend = caches['default']
        backend_name = f"{backend.__class__.__module__}.{backend.__class__.__name__}"
        if 'dummy' in backend_name.lower() or 'dummycache' in backend_name.lower():
            logger.info('DummyCache configured; skipping delete_patterns')
            for p in patterns:
                results[p] = 0
            return results
    except Exception:
        # If any issue reading cache backend, continue and attempt redis connection
        logger.debug('could not determine cache backend, attempting redis fallback', exc_info=True)

    try:
        from django_redis import get_redis_connection
    except Exception as exc:
        logger.error('django_redis not available for delete_patterns: %s', exc)
        for p in patterns:
            results[p] = None
        return results

    try:
        conn = get_redis_connection()
    except Exception as exc:
        logger.error('could not get redis connection for delete_patterns: %s', exc)
        for p in patterns:
            results[p] = None
        return results

    for p in patterns:
        full_pattern = _build_full_pattern(p)
        deleted = 0
        try:
            for key in conn.scan_iter(match=full_pattern):
                try:
                    conn.delete(key)
                    deleted += 1
                except Exception:
                    logger.debug('failed to delete key during pattern cleanup', exc_info=True)
            logger.info('delete_patterns: %s removed %d keys', full_pattern, deleted)
            results[p] = deleted
        except Exception as exc:
            logger.error('delete_patterns failed for %s: %s', full_pattern, exc)
            results[p] = None

    return results


def delete_pattern(pattern: str) -> Optional[int]:
    """Compatibility wrapper for single pattern deletion returning int or None."""
    res = delete_patterns([pattern])
    return res.get(pattern)
