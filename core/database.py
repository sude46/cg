import logging

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Query

#配置日志
logging.basicConfig(level=logging.INFO)
logger=logging.getLogger(__name__)




class SoftDeleteQuery(Query):
    def __iter__(self):
        return super().__iter__()
    def _add_soft_delete_filter(self):
        if self.column_descriptions and len(self.column_descriptions)>0:
            entity = self.column_descriptions[0]["entity"]
            # 仅对包含 is_deleted 字段的模型生效
            if hasattr(entity, "is_deleted"):
                return self.filter(entity.is_deleted.is_(False))
        return self
# 创建数据库实例
db = SQLAlchemy(query_class=SoftDeleteQuery)
migrate = Migrate()


#定义基础模型，实现软删除+全局过滤逻辑
class BaseModel(db.Model):
    __abstract__=True
    #软删除字段，默认未删除
    is_deleted=db.Column(db.Boolean,default=False,nullable=False,index=True)

    #重写查询方法
    @classmethod
    def query(cls):
        return super().query.filter_by(is_deleted=False)
class DatabaseManager:
    """数据库管理器，处理初始化，连接池，会话管理，异常处理"""
    @staticmethod
    def init_app(app):
        """初始化数据库配置(核心修复点)"""
        #配置数据库连接池连接参数，解决高并发泄露问题
        app.config.setdefault('SQLALCHEMY_POOL_SIZE',10)  #连接池默认大小
        app.config.setdefault('SQLALCHEMY_POOL_RECYCLE',3600)  #1小时回收连接（防止数据库端断开未释放)
        app.config.setdefault('SQLALCHEMY_POOL_PRE_PING',True)   #执行SQL前检查连接有效性
        app.config.setdefault('SQLALCHEMY_MAX_OVERFLOW',20)      #超出池大小的临时链接数
        app.config.setdefault('SQLALCHEMY_TRACK_MODIFICATIONS', False)  # 关闭不必要的性能损耗

        # 初始化Flask-SQLAlchemy和Migrate
        db.init_app(app)
        migrate.init_app(app, db)

        #注册CLI命令（统一处理异常，避免泄露敏感信息)
        @app.cli.command('init-db')
        def init_db_command():
            """初始化数据库表"""
            try:
                with app.app_context():
                    db.create_all()
                logger.info("数据库表创建成功")
                print("数据库表创建成功")
            except SQLAlchemyError as e:
                # 日志记录详细异常，前端返回通用提示
                logger.error(f"数据库表创建失败: {str(e)}")
                print("数据库表创建失败：服务内部错误")
            except Exception as e:
                logger.error(f"数据库表创建未知错误: {str(e)}")
                print("数据库表创建失败：服务内部错误")

        @app.cli.command('drop-db')
        def drop_db_command():
            """删除所有数据库表"""
            try:
                with app.app_context():
                    db.drop_all()
                logger.info("数据库表删除成功")
                print("数据库表删除成功")
            except SQLAlchemyError as e:
                logger.error(f"数据库表删除失败: {str(e)}")
                print("数据库表删除失败：服务内部错误")
            except Exception as e:
                logger.error(f"数据库表删除未知错误: {str(e)}")
                print("数据库表删除失败：服务内部错误")

        @app.cli.command('reset-db')
        def reset_db_command():
            """重置数据库"""
            try:
                with app.app_context():
                    db.drop_all()
                    db.create_all()
                logger.info("数据库重置成功")
                print("数据库重置成功")
            except SQLAlchemyError as e:
                logger.error(f"数据库重置失败: {str(e)}")
                print("数据库重置失败：服务内部错误")
            except Exception as e:
                logger.error(f"数据库重置未知错误: {str(e)}")
                print("数据库重置失败：服务内部错误")

        # 请求结束时关闭会话（多线程安全）
        @app.teardown_appcontext
        def shutdown_session(exception=None):
            try:
                db.session.remove()
            except Exception as e:
                logger.error(f"关闭数据库会话失败: {str(e)}")

    @staticmethod
    def test_connection():
        """测试数据库连接（统一异常处理）"""
        try:
            with db.session() as session:
                session.execute(text('SELECT 1'))
            logger.info("数据库连接正常")
            return True, "数据库连接正常"
        except SQLAlchemyError as e:
            # 4. 捕获SQLAlchemy异常，封装错误信息（不暴露原始异常）
            logger.error(f"数据库连接失败: {str(e)}")
            return False, "数据库连接失败：服务内部错误"
        except Exception as e:
            logger.error(f"数据库连接未知错误: {str(e)}")
            return False, "数据库连接失败：服务内部错误"

# 创建数据库管理器实例
db_manager = DatabaseManager()
