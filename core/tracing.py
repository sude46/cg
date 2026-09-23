"""OpenTelemetry 分布式追踪初始化（导出到 Jaeger / 任意 OTLP 后端）。

- Web 进程：`wsgi.py` 在 create_app 之前调用 `init_tracing('weibo-api')`
- Celery worker：`core/celery_app.py` 通过 worker_process_init 信号在子进程调用
- 关闭/未装/连不上：`OTEL_ENABLED=false` 或异常都直接跳过，不影响业务

说明：不启用 redis instrumentation——事件总线 BRPOP / SSE pubsub 是长轮询，
会持续产生每秒级的 span。ES 客户端同理先不接入。
"""
import logging
import os

logger = logging.getLogger(__name__)

_initialized = False


def _enabled() -> bool:
    return os.getenv('OTEL_ENABLED', 'true').lower() == 'true'


def _sampler():
    from opentelemetry.sdk.trace.sampling import ALWAYS_ON, ParentBased, TraceIdRatioBased
    try:
        ratio = float(os.getenv('OTEL_TRACES_SAMPLER_ARG', '1.0'))
    except (TypeError, ValueError):
        ratio = 1.0
    if ratio >= 1.0:
        return ParentBased(ALWAYS_ON)
    return ParentBased(TraceIdRatioBased(ratio))


def init_tracing(service_name: str) -> None:
    """幂等初始化；已初始化或关闭时直接返回。"""
    global _initialized
    if not _enabled() or _initialized:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.celery import CeleryInstrumentor
        from opentelemetry.instrumentation.flask import FlaskInstrumentor
        from opentelemetry.instrumentation.logging import LoggingInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        endpoint = os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT', 'http://jaeger:4317')
        resource = Resource.create({
            'service.name': service_name,
            'service.version': os.getenv('APP_VERSION', '1.0.0'),
            'deployment.environment': os.getenv('FLASK_ENV', 'development'),
        })
        provider = TracerProvider(resource=resource, sampler=_sampler())
        provider.add_span_processor(BatchSpanProcessor(
            OTLPSpanExporter(endpoint=endpoint, insecure=endpoint.startswith('http://'))
        ))
        trace.set_tracer_provider(provider)

        FlaskInstrumentor().instrument()
        SQLAlchemyInstrumentor().instrument()
        CeleryInstrumentor().instrument()
        LoggingInstrumentor().instrument(set_logging_format=False)

        _initialized = True
        logger.info(f'[Tracing] OpenTelemetry 已启用 service={service_name} otlp={endpoint}')
    except Exception as e:  # 追踪绝不能拖垮主流程
        logger.warning(f'[Tracing] 初始化失败，已跳过: {e}')


def get_tracer(name: str = 'weibo-platform'):
    from opentelemetry import trace
    return trace.get_tracer(name)
