# syntax=docker/dockerfile:1
FROM python:3.11-slim AS builder

WORKDIR /build

COPY pyproject.toml ./
COPY README.md* ./

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e .

FROM python:3.11-slim

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
