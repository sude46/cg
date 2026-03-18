# core/logging_config.py
import logging
import os
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler

def init_structured_logger(app):
    """结构化日志初始化（修复测试环境目录为空问题+环境适配）"""
    root_logger = logging.getLogger()
    # 清空原有处理器（避免重复输出）
    root_logger.handlers.clear()
    root_logger.setLevel(app.config.get("LOG_LEVEL", logging.INFO))

    # 1. 基础配置读取
    log_format = app.config.get("LOG_FORMAT", "%(asctime)s %(levelname)s %(request_id)s %(message)s")
    info_log_file = app.config.get("INFO_LOG_FILE", "logs/info.log")
    error_log_file = app.config.get("ERROR_LOG_FILE", "logs/error.log")
    log_rotate_when = app.config.get("LOG_ROTATE_WHEN", "D")
    log_rotate_interval = app.config.get("LOG_ROTATE_INTERVAL", 1)
    log_rotate_backup_count = app.config.get("LOG_ROTATE_BACKUP_COUNT", 7)
    
    # 2. 创建格式化器（支持request_id上下文）
    class ContextFormatter(logging.Formatter):
        def format(self, record):
            # 补充所有自定义字段，防止 KeyError
            record.request_id = getattr(record, 'request_id', 'N/A')
            record.user_id = getattr(record, 'user_id', 'N/A')
            record.elapsed_time = getattr(record, 'elapsed_time', 'N/A')
            return super().format(record)
    
    formatter = ContextFormatter(log_format)

    # 3. 控制台处理器（所有环境都启用）
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 4. 文件处理器（仅非测试环境启用，避免创建目录报错）
    if not app.config.get("TESTING", False):
        # 处理info日志文件目录
        info_log_dir = os.path.dirname(info_log_file)
        if info_log_dir:  # 只有目录非空时才创建
            os.makedirs(info_log_dir, exist_ok=True)
        # 处理error日志文件目录
        error_log_dir = os.path.dirname(error_log_file)
        if error_log_dir:
            os.makedirs(error_log_dir, exist_ok=True)
        
        # 添加info文件处理器
        info_file_handler = TimedRotatingFileHandler(
            info_log_file,
            when=log_rotate_when,
            interval=log_rotate_interval,
            backupCount=log_rotate_backup_count,
            encoding='utf-8'
        )
        info_file_handler.setLevel(logging.INFO)
        info_file_handler.setFormatter(formatter)
        root_logger.addHandler(info_file_handler)

        # 添加error文件处理器
        error_file_handler = TimedRotatingFileHandler(
            error_log_file,
            when=log_rotate_when,
            interval=log_rotate_interval,
            backupCount=log_rotate_backup_count,
            encoding='utf-8'
        )
        error_file_handler.setLevel(logging.ERROR)
        error_file_handler.setFormatter(formatter)
        root_logger.addHandler(error_file_handler)

    app.logger.info(f"日志初始化完成，测试环境：{app.config.get('TESTING', False)}")
