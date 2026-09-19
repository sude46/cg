"""存储抽象层。

当前实现 LocalStorage（本地磁盘）；S3/MinIO/OSS 可后续按同一接口扩展，
上层（app/uploads）只依赖 StorageProvider，不感知具体后端。
"""
import logging
import os
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class StorageProvider(ABC):
    @abstractmethod
    def save(self, file_storage, key: str) -> None:
        """持久化文件（后端中转/本地落盘）"""

    @abstractmethod
    def public_url(self, key: str) -> str:
        """返回可回显的最终 URL"""

    @abstractmethod
    def delete(self, key: str) -> None:
        """删除对象（孤儿清理/帖子删除）"""


class LocalStorage(StorageProvider):
    def __init__(self, folder: str, public_base: str = '/uploads/files'):
        self.folder = folder
        self.public_base = (public_base or '').rstrip('/')

    def _path(self, key: str) -> str:
        return os.path.join(self.folder, key)

    def save(self, file_storage, key: str) -> None:
        path = self._path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        file_storage.save(path)

    def public_url(self, key: str) -> str:
        if not self.public_base:
            return f'/uploads/files/{key}'
        return f'{self.public_base}/{key}'

    def delete(self, key: str) -> None:
        path = self._path(key)
        if os.path.exists(path):
            os.remove(path)


def get_storage() -> StorageProvider:
    """按配置返回存储实现。"""
    from flask import current_app

    backend = current_app.config.get('STORAGE_BACKEND', 'local')
    if backend == 'local':
        return LocalStorage(
            current_app.config['UPLOAD_FOLDER'],
            current_app.config.get('STORAGE_PUBLIC_BASE', '/uploads/files'),
        )
    raise ValueError(f'不支持的 STORAGE_BACKEND: {backend}')
