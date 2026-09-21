import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logger(app):
    #若logs目录不存在，创建目录（避免日志文件无法被写入）
    if not os.path.exists('logs'):
        os.mkdir('logs')

    #配置轮转日志处理器（避免单个日志文件过大）
    #-日志文件路径:logs/weibo.log
    #-maxBytes=1024:单个文件最大10kB
    #-backupCount=10:最多保留10个备份文件
    file_handler=RotatingFileHandler('logs/weibo.log',maxBytes=10240,backupCount=10)

    #定义日志格式（包含时间，级别，消息，代码路径+行号，用于定位问题）
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))

    #设置日志文减级别为INFO
    file_handler.setLevel(logging.INFO)
    #将处理器添加到Flask应用的日志器
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)


    #记录应用启动日志（首次调用时触发，证明日志配置生效）
    app.logger.info('Weibo startup')

