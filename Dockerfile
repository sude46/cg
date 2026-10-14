# syntax=docker/dockerfile:1
# 固定基础镜像 digest：避免上游 slim tag 漂移导致依赖层缓存失效（升级需手动更新这两个 digest）
FROM python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93 AS builder

WORKDIR /build

COPY pyproject.toml ./
COPY README.md* ./

# 网络不稳时更耐受：加大超时并重试（配合下面的 pip cache mount，重试可从已下载处续上）
ENV PIP_DEFAULT_TIMEOUT=100 \
    PIP_RETRIES=10 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# BuildKit pip cache mount：复用已下载的 wheel/构建依赖，层失效时也无需重新下载全部依赖
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -e .

FROM python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY . .

RUN useradd -m -u 1000 cguser && chown -R cguser:cguser /app
USER cguser

EXPOSE 5000

CMD ["gunicorn", "-w", "4", "-k", "gthread", "--threads", "8", \
     "-b", "0.0.0.0:5000", "--access-logfile", "-", "--error-logfile", "-", \
     "wsgi:app"]
