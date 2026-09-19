import logging
import os
from datetime import UTC, datetime
from uuid import uuid4

from flask import current_app

from app.common.exceptions import ValidationError
from utils.storage import get_storage

logger = logging.getLogger(__name__)

# 嗅探到的类型 -> 文件扩展名
_EXT = {'jpeg': 'jpg', 'png': 'png', 'gif': 'gif', 'webp': 'webp'}


def _sniff_image(stream) -> str | None:
    """以真实字节判断图片类型（不信任客户端 content_type）。"""
    head = stream.read(32)
    stream.seek(0)
    if head.startswith(b'\xff\xd8\xff'):
        return 'jpeg'
    if head.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png'
    if head[:6] in (b'GIF87a', b'GIF89a'):
        return 'gif'
    if head[:4] == b'RIFF' and head[8:12] == b'WEBP':
        return 'webp'
    return None


class UploadService:
    @staticmethod
    def save_image(user_id: int, file_storage) -> dict:
        """校验并保存图片，返回 {url, key}。"""
        if not file_storage or not file_storage.filename:
            raise ValidationError('缺少上传文件')

        max_bytes = current_app.config.get('UPLOAD_MAX_BYTES', 5 * 1024 * 1024)
        allowed = current_app.config.get('UPLOAD_ALLOWED_TYPES', set())

        stream = file_storage.stream
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(0)
        if size == 0:
            raise ValidationError('上传文件为空')
        if size > max_bytes:
            raise ValidationError(f'图片不能超过 {max_bytes // 1024 // 1024}MB')
        if allowed and file_storage.mimetype not in allowed:
            raise ValidationError('仅支持 jpg/png/webp/gif')

        kind = _sniff_image(stream)
        if kind is None:
            raise ValidationError('文件内容不是有效图片')

        key = f"uploads/{user_id}/{datetime.now(UTC).strftime('%Y%m')}/{uuid4().hex}.{_EXT[kind]}"
        storage = get_storage()
        storage.save(file_storage, key)
        logger.info(f'用户{user_id}上传图片成功: {key}')
        return {'url': storage.public_url(key), 'key': key}
