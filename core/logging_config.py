# core/logging_config.py
import logging
import os
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler

def init_structured_logger(app):
    """结构化日志初始化（修复版）"""
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(app.config.get("LOG_LEVEL", logging.INFO))

    # ========== 关键修改：使用 LOG_DIR 构建绝对路径 ==========
    # 获取日志目录（绝对路径）
    log_dir = app.config.get("LOG_DIR")
    if not log_dir:
        # 如果没有配置，默认使用项目根目录下的 logs/
        project_root = app.root_path
        log_dir = os.path.join(project_root, "logs")
    
    # 确保是绝对路径
    log_dir = os.path.abspath(log_dir)
    
    # 强制使用 LOG_DIR 下的路径（忽略 INFO_LOG_FILE 配置）
    info_log_file = os.path.join(log_dir, "info.log")
    error_log_file = os.path.join(log_dir, "error.log")
    
    # 确保目录存在（提前创建，避免 TimedRotatingFileHandler 报错）
    os.makedirs(log_dir, exist_ok=True)
    
    app.logger.info(f"日志目录: {log_dir}")  # 调试用，确认路径正确
    # =====================================================

    log_format = "%(asctime)s %(levelname)s %(request_id)s %(message)s"
    log_rotate_when = app.config.get("LOG_ROTATE_WHEN", "D")
    log_rotate_interval = app.config.get("LOG_ROTATE_INTERVAL", 1)
    log_rotate_backup_count = app.config.get("LOG_ROTATE_BACKUP_COUNT", 7)
    
    # 格式化器
    class ContextFormatter(logging.Formatter):
        def format(self, record):
            record.request_id = getattr(record, 'request_id', 'N/A')
            record.user_id = getattr(record, 'user_id', 'N/A')
            record.elapsed_time = getattr(record, 'elapsed_time', 'N/A')
            return super().format(record)
    
    formatter = ContextFormatter(log_format)

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 文件处理器（非测试环境）
    if not app.config.get("TESTING", False):
        # info 日志
        info_handler = TimedRotatingFileHandler(
            info_log_file,
            when=log_rotate_when,
            interval=log_rotate_interval,
            backupCount=log_rotate_backup_count,
            encoding='utf-8'
        )
        info_handler.setLevel(logging.INFO)
        info_handler.setFormatter(formatter)
        root_logger.addHandler(info_handler)

        # error 日志
        error_handler = TimedRotatingFileHandler(
            error_log_file,
            when=log_rotate_when,
            interval=log_rotate_interval,
            backupCount=log_rotate_backup_count,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        root_logger.addHandler(error_handler)

    app.logger.info(f"日志初始化完成，目录: {log_dir}")