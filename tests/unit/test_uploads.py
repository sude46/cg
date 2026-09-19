import base64
import io

import pytest
from werkzeug.datastructures import FileStorage

from app.common.exceptions import ValidationError

PNG_1X1 = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC'
)


def _file(data: bytes, filename: str, content_type: str) -> FileStorage:
    return FileStorage(stream=io.BytesIO(data), filename=filename, content_type=content_type)


def test_save_image_ok(app, tmp_path):
    from app.uploads.services import UploadService

    with app.app_context():
        app.config['UPLOAD_FOLDER'] = str(tmp_path)
        app.config['STORAGE_PUBLIC_BASE'] = 'http://cdn.test/uploads/files'
        result = UploadService.save_image(1, _file(PNG_1X1, 'a.png', 'image/png'))

    assert result['url'].startswith('http://cdn.test/uploads/files/')
    assert result['key'].endswith('.png')
    assert (tmp_path / result['key']).exists()


def test_save_image_rejects_mime(app, tmp_path):
    from app.uploads.services import UploadService

    with app.app_context():
        app.config['UPLOAD_FOLDER'] = str(tmp_path)
        with pytest.raises(ValidationError):
            UploadService.save_image(1, _file(b'<svg/>', 'a.svg', 'image/svg+xml'))


def test_save_image_rejects_fake_image(app, tmp_path):
    from app.uploads.services import UploadService

    with app.app_context():
        app.config['UPLOAD_FOLDER'] = str(tmp_path)
        # content_type 声称 png，但真实字节不是图片 -> magic bytes 拒绝
        with pytest.raises(ValidationError):
            UploadService.save_image(1, _file(b'not-an-image', 'a.png', 'image/png'))
