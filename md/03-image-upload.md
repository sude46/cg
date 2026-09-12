# 03 — 图片上传接口（item 10，最大功能缺口）

现状：`image_url` 只是字符串，全项目无 upload / OSS / MinIO，前端只能贴外链。
建议**主推 OSS/MinIO 直传签名**（文件不过 Flask），**本地磁盘做降级**（开发/单机部署）。

---

## 1. 方案对比与选型

| 方案 | 优点 | 缺点 | 适用 |
|------|------|------|------|
| **A. 对象存储直传（签名）** | Flask 不碰文件字节，省带宽/内存；天然 CDN | 需配置 OSS/MinIO 密钥；前端两步（取签名→PUT） | **生产推荐** |
| B. 后端中转上传 | 前端一个 `multipart` 请求搞定 | 大文件占 worker、超时、扩容难 | 小规模/内网 |
| C. 本地磁盘 | 零外部依赖 | 多实例不共享、磁盘爆、无 CDN | 开发环境 |

结论：**A 为主 + C 开发兜底**，通过 `STORAGE_BACKEND` 切换；抽象同一层接口，前端只需按字段切换。
发帖接口的 `image_url` 逻辑不变（存最终 URL），上传接口把 URL 还给前端。

---

## 2. 存储抽象层

新建 `utils/storage.py`：

```python
from abc import ABC, abstractmethod


class StorageProvider(ABC):
    @abstractmethod
    def presign_put(self, key: str, content_type: str, expires: int) -> str:
        """返回前端可直接 PUT 的 URL"""

    @abstractmethod
    def public_url(self, key: str) -> str:
        """返回可回显的最终 URL"""

    @abstractmethod
    def save(self, file_storage, key: str) -> None:
        """后端中转/本地落盘（可选实现）"""

    @abstractmethod
    def delete(self, key: str) -> None:
        """删除对象（帖子删除/孤儿清理）"""
```

三个实现：

- `LocalStorage`：`save` 写 `UPLOAD_FOLDER`（`config/base.py:114` 已有），`public_url` 返回 `/static/uploads/<key>`。
- `S3CompatibleStorage`：用 `boto3`，同时支持 **AWS S3 / MinIO / 阿里云 OSS(S3 兼容)**。`generate_presigned_url('put_object', Params={Bucket,Key,ContentType}, ExpiresIn)`。
- （可选）`AliyunOSSStorage`：用 `oss2`，`bucket.sign_url('PUT', key, expires)`。若 OSS 开 S3 兼容，直接用 `boto3` 即可，少一个依赖。

配置（加在 `config/base.py`，`.env` 补键）：

```python
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local")   # local | s3
STORAGE_PUBLIC_BASE = os.getenv("STORAGE_PUBLIC_BASE", "")  # CDN/裸域名
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "")       # MinIO: http://minio:9000
S3_REGION = os.getenv("S3_REGION", "us-east-1")
S3_BUCKET = os.getenv("S3_BUCKET", "weibo-media")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "")
S3_USE_SSL = os.getenv("S3_USE_SSL", "true").lower() == "true"
UPLOAD_MAX_BYTES = int(os.getenv("UPLOAD_MAX_BYTES", 5 * 1024 * 1024))  # 单图 5MB
UPLOAD_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
```

依赖：`boto3>=1.34` 写入 `pyproject.toml` 的 `dependencies`（唯一新增）。

---

## 3. 新增上传模块 `app/uploads/`

按项目分层建模块（routes/services/storage），并在 `core/blueprint_registry.py` 注册蓝图。
`url_prefix='/uploads'`，`Namespace('uploads', path='/')`（遵守 AGENTS.md 路由约定）。

### 3.1 接口一：取直传签名（生产）

`POST /uploads/presign`（JWT 必填）

请求：

```json
{ "filename": "photo.jpg", "content_type": "image/jpeg", "size": 123456 }
```

服务端校验：
1. `content_type in UPLOAD_ALLOWED_TYPES`
2. `size <= UPLOAD_MAX_BYTES`
3. 生成 key：`uploads/{user_id}/{yyyymm}/{uuid4().hex}.{ext}`
4. 返回：

```json
{
  "code": 200,
  "data": {
    "upload_url": "https://bucket.oss.../uploads/1/202609/ab12.jpg?X-Amz-Signature=...",
    "method": "PUT",
    "headers": { "Content-Type": "image/jpeg" },
    "key": "uploads/1/202609/ab12.jpg",
    "url": "https://cdn.example.com/uploads/1/202609/ab12.jpg",
    "expires_in": 300
  },
  "message": "获取上传签名成功"
}
```

前端拿到后直接 `PUT upload_url`（body=文件），成功后把 `url` 填进发帖的 `image_url`。

### 3.2 接口二：后端中转上传（本地兜底 / 兼容）

`POST /uploads`，`multipart/form-data`，字段 `file`（JWT 必填，限流 `10 per minute`）。

```python
@api.route("")
class UploadResource(Resource):
    @jwt_required()
    @route_limit("10 per minute")
    def post(self):
        if "file" not in request.files:
            raise ValidationError("缺少文件")
        f = request.files["file"]
        # 1. 大小 2. MIME 3. magic bytes 4. 存盘 5. 返回 URL
```

返回：

```json
{ "code": 200, "data": { "url": "/static/uploads/202609/ab12.jpg", "key": "..." }, "message": "上传成功" }
```

### 3.3 关键校验（安全，别省）

```python
import imghdr  # 或 PIL.Image.verify
from werkzeug.utils import secure_filename

def validate_image(file_storage):
    if file_storage.content_length and file_storage.content_length > UPLOAD_MAX_BYTES:
        raise ValidationError("图片不能超过 5MB")
    sniffed = imghdr.what(file_storage.stream)   # 以真实字节判断，别信 content_type
    if sniffed not in {"jpeg", "png", "webp", "gif"}:
        raise ValidationError("仅支持 jpg/png/webp/gif")
    file_storage.stream.seek(0)
```

- 用 `uuid4` 重命名，不经用户原始文件名（防 `../` / XSS / 覆盖）。
- 直传路径**也必须在服务端签发时校验** `content_type/size`；OSS 端可加 bucket policy 限制 `Content-Type` 和 `Content-Length`。
- `Content-Type` 白名单 + 禁止 `image/svg+xml`（SVG 可内嵌 JS）。
- 可选：`PIL.Image.open(...).verify()` 去除 EXIF（隐私，如 GPS）。

---

## 4. 清理 / 生命周期

| 场景 | 做法 |
|------|------|
| 帖子被删 | 软删帖子时**不立即删图**（可能被引用），交给对账；或 `event_bus` 发 `post.deleted` 后异步删 `image_url` 对应 key |
| 上传后未发帖（孤儿） | 新增 Celery beat 任务 `cleanup_orphan_uploads`：每天扫对象存储 `uploads/` 前缀中 `last_modified > 24h` 且未被任何 `posts.image_url` 引用的对象并删除 |
| 本地磁盘 | 同上，扫 `UPLOAD_FOLDER` 对比 DB |
| 存储配额 | 单用户目录 + 定期统计；超限拒绝 |

> 对账任务参考项目已有 `tasks/*_reconcile.py` 的写法（`core/celery_app.py` 的 `beat_schedule` 注册）。

---

## 5. 前端过渡（按用户要求）

发帖组件的图片选择抽象成一个 `ImageSource` 接口：

```ts
interface ImageSource {
  pick(): Promise<{ previewUrl: string; getUrl(): Promise<string> }>
}
```

- 先只实现 `ExternalUrlSource`（手填外链），发帖直接提交 `image_url`。
- 上传接口就绪后，实现 `DirectUploadSource`：调 `POST /uploads/presign` → `PUT` → `getUrl()` 返回对象 URL。
- 发帖组件不感知区别，做到"无缝切换"。

发帖接口本身**不需要改**：`CreatePostSchema.image_url`（`app/posts/schemas.py:21`）仍收字符串，
后续可加白名单校验（只接受本域/CDN 前缀，防止外链注入），见 §6。

---

## 6. 可选加固：`image_url` 白名单

在 `CreatePostSchema/UpdatePostSchema.validate_fields` 里限制 `image_url` 必须：

- 空，或
- 以 `STORAGE_PUBLIC_BASE`（或 `/static/uploads/`）开头。

否则用户可填任意外链做钓鱼/画像。前端先只实现外链来源时，白名单要放宽——建议用配置开关 `IMAGE_URL_ALLOW_EXTERNAL=true`（开发期）。

---

## 7. 改动清单

- [ ] `pyproject.toml` 加 `boto3`（若用 S3/OSS）
- [ ] `config/base.py` + `.env` 加 `STORAGE_*` 配置
- [ ] 新建 `utils/storage.py`（抽象 + Local/S3 实现）
- [ ] 新建 `app/uploads/`（`__init__.py` 含 `from . import routes`、`routes.py`、`services.py`、`schemas.py`）
- [ ] `core/blueprint_registry.py` 注册 uploads 蓝图
- [ ] `POST /uploads/presign`、`POST /uploads`
- [ ] 清理任务 `tasks/upload_tasks.py` + `beat_schedule`
- [ ] 冒烟：新增测试（presign 返回带签名 URL；`POST /uploads` 传 1x1 png 返回 URL）
- [ ] Swagger 文档

## 8. 验证示例

```bash
# 本地后端中转
curl -s -X POST http://localhost:5000/uploads \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/tmp/test.png" | jq
# 期望 data.url 非空

# 直传签名（生产）
curl -s -X POST http://localhost:5000/uploads/presign \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"filename":"a.jpg","content_type":"image/jpeg","size":1000}' | jq
# 期望 data.upload_url 含 signature
```
