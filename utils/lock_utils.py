'''数据库锁工具：死锁重试、悲观锁封装'''
import logging 
import time 
from functools import wraps
from sqlalchemy.exc import OperationalError
from core.database import db

logger=logging.getLogger(__name__)

def with_deadlock_retry(max_retries:int=3,base_delay:float=0.1):
    '''
    死锁自动重试装饰器
    用法：
    @with_deadlock_retry(max_retries=3)
    def transfer_followers(...):
    
    原理：捕获数据库死锁异常（mysql:1213,PostgreSQL:40P01),
    安直树退避策略延迟后重试。
    '''
    def decorator(f):
        @wraps(f)
        def wrapper(*args,**kwrags):
            last_exception=None
            for attempt in range(1,max_retries+1):
                try:
                    return f(*args,**kwrags)
                except OperationalError as e:
                    last_exception=e
                    #Mysql死锁错误码1213，，PostgreSQL 40P01，SQLite 6 (database is locked)
                    error_code=getattr(e.orig,'args',[None])[0] if e.orig else None
                    is_deadlock=(
                        'Deadlock found 'in str(e) #MySql
                        or 'deadlock detected' in str(e).lower()  # PostgreSQL
                        or 'database is locked' in str(e).lower()  # SQLite
                        or error_code in (1213, '40P01', 6)

                    )
                    if not is_deadlock:
                        raise    #非死锁异常，直接抛出

                    if attempt==max_retries:
                        logger.error(f'[{f.__name__}]死锁重试耗尽{max_retries}次，放弃执行')
                        raise

                    #指数退避
                    delay=base_delay*(2**(attempt-1))
                    logger.warning(
                        f'[{f.__name__}]检测到死锁，第{attempt}次重试，延迟{delay}s:{e}'
                    )
                    time.sleep(delay)
                    #回滚并开启新会话
                    db.session.rollback()

            raise last_exception
        return wrapper
    return decorator

def pessimistic_get(model_class,*filters,lock_mode='update',**filter_by):
    '''
    封装悲观锁查询
    用法：
    post=pessimistic_get(Post, Post.id == post_id, is_deleted=False)
    # 等价于：SELECT * FROM posts WHERE id=1 AND is_deleted=False FOR UPDATE

    lock_mode:
        -'update':SELECT FOR UPDATE（排他锁，其他事务不能读写）
        -'share':ELECT FOR SHARE（共享锁，其他事务可读不可写）

    '''
    query=db.session.query(model_class)

    for f in filters:
        query=query.filter(f)
    if filter_by:
        query=query.filter_by(**filter_by)
    elif lock_mode=='share':
        query=query.with_for_update(read=True)
    else:
        raise ValueError(f'不支持的lock_mode:{lock_mode}')
    
    return query.first()
