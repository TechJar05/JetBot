# utils/frames.py
from typing import List
from django.core.cache import cache

def _cache_key(interview_id: int, user_id: int) -> str:
    return f"iv_frames:{interview_id}:{user_id}"

def append_frames_to_cache(interview_id: int, user_id: int, new_frames: List[str], max_len: int = 10, ttl_seconds: int = 6*3600) -> int:
    """
    Append base64 frames to cache; cap at max_len. Returns new total length.
    """
    key = _cache_key(interview_id, user_id)
    existing = cache.get(key, [])
    merged = (existing + (new_frames or []))[:max_len]
    cache.set(key, merged, timeout=ttl_seconds)
    return len(merged)

def pop_frames_from_cache(interview_id: int, user_id: int) -> List[str]:
    """
    Retrieve frames and clear the cache entry.
    """
    key = _cache_key(interview_id, user_id)
    frames = cache.get(key, []) or []
    cache.delete(key)
    return frames
