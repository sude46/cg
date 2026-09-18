import logging
import threading
import time
from typing import Any

from core.redis_cache import redis_cache

logger=logging.getLogger(__name__)

class UserCache:
    '''
    用户缓存管理（对标PostCache设计）
    -key:user:profile:{user_id}             #用户公开资料（过滤敏感字段）
    -key:user:recent_modify:{id}            #强一致标记（创建/更新/删除后）
    -key:user:name:{username}               #用户名->user_id映射
    -key:user:email:{email}                 #邮箱->user_id映射
    '''

    PROFILE_TTL=600                     #用户资料10分钟(变更比帖子少)
    RECENT_MODIFY_TTL=60                #强一致窗口60秒
    NAME_INDEX_TTL=3600                 #用户名/邮箱索引1小时


    #============================Key生成=======================
    @classmethod
    def _profile_key(cls,user_id:int):
        return f'user:profile:{user_id}'
    @classmethod
    def _recent_key(cls,user_id:int):
        return f'user:recent_modify:{user_id}'
    @classmethod
    def _name_key(cls,username:str):
        return f'user:name:{username.lower()}'
    @classmethod
    def _email_key(cls,email:str):
        return f'user:email:{email.lower()}'
    @classmethod
    def _public_key(cls,user_id:int):
        return f'user:public:{user_id}'

    #=========================敏感数据过滤=================
    # 防御纵深（Defense-in-Depth）：
    # 第一层：UserSchema 控制响应字段（schema 里不定义就不输出）
    # 第二层：_sanitize 兜底——即使有人绕过 schema 直接缓存 model dict，也绝不泄露
    @classmethod
    def _sanitize(cls,user_data:dict[str,Any]):
        sensitive={'password_hash','mfa_secret','lock_until','login_fail_count'}
        leaked=[k for k in sensitive if k in user_data]
        if leaked:
            logger.warning(f'敏感字段 {leaked} 到达缓存层，已被过滤（Schema 应提前拦截）')
        return {k:v for k,v in user_data.items() if k not in sensitive}


    #================基础CRUD==============================
    @classmethod
    def get_profile(cls,user_id:int):
        '''读用户资料缓存'''
        try:
            return redis_cache.get(cls._profile_key(user_id),for_write=False)
        except Exception as e:
            logger.error(f'获取用户{user_id}缓存失败:{e}')
            return None


    @classmethod
    def set_profile(cls,user_id:int,user_data:dict[str,Any]):
        '''写用户资料缓存（自动过滤敏感字段）'''
        try:
            safe_data=cls._sanitize(user_data)
            return redis_cache.set(
                cls._profile_key(user_id),
                safe_data,
                expire=cls.PROFILE_TTL,
                for_write=True
                )
        except Exception as e:
            logger.error(f'设置用户{user_id}缓存失败:{e}')
            return False

    @classmethod
    def invalidate(cls,user_id:int):
        '''删除用户资料缓存（含公开资料缓存）'''
        try:
            redis_cache.delete(cls._profile_key(user_id))
            redis_cache.delete(cls._public_key(user_id))
            return True
        except Exception as e:
            logger.error(f'删除用户{user_id}缓存失败:{e}')
            return False

    @classmethod
    def get_public_profile(cls,user_id:int):
        '''读用户公开资料缓存（脱敏，独立 key，不复用含 email 的 profile）'''
        try:
            return redis_cache.get(cls._public_key(user_id),for_write=False)
        except Exception as e:
            logger.error(f'获取用户{user_id}公开资料缓存失败:{e}')
            return None

    @classmethod
    def set_public_profile(cls,user_id:int,data:dict):
        '''写用户公开资料缓存'''
        try:
            return redis_cache.set(
                cls._public_key(user_id),
                data,
                expire=cls.PROFILE_TTL,
                for_write=True
            )
        except Exception as e:
            logger.error(f'设置用户{user_id}公开资料缓存失败:{e}')
            return False


    #==================强一致标记===============
    @classmethod
    def mark_recently_modified(cls,user_id:int,ttl:int=None):
        '''标记用户最近被修改，后续读强制走主库'''
        ttl=ttl or cls.RECENT_MODIFY_TTL
        try:
            return redis_cache.set(
                cls._recent_key(user_id),
                "1",
                expire=ttl,
                for_write=True
            )
        except Exception as e:
            logger.error(f'标记用户{user_id}最近修改失败:{e}')
            return False

    @classmethod
    def is_recently_modified(cls,user_id:int):
        '''检查用户是否在强一致窗口内'''
        try:
            return redis_cache.exists(cls._recent_key(user_id), for_write=True)>0
        except Exception as e:
            logger.error(f'检查用户{user_id}最近修改失败:{e}')
            return False


    #===================用户名/邮箱索引（存在性快速校验）==============
    @classmethod
    def get_by_username(cls,username:str):
        '''
        通过用户名反查user_id（非密码场景）
        登录密码校验绝不能走这个缓存
        '''
        try:
            result=redis_cache.get(cls._name_key(username),for_write=False)
            return int(result) if result else None
        except Exception as e:
            logger.error(f'获取用户名{username}缓存失败:{e}')
            return None

    @classmethod
    def set_by_username(cls,username:str,user_id:int):
        try:
            return redis_cache.set(
                cls._name_key(username),
                user_id,
                expire=cls.NAME_INDEX_TTL,
                for_write=True
            )
        except Exception as e:
            logger.error(f'设置用户名{username}缓存失败: {e}')
            return False
    @classmethod
    def invalidate_by_username(cls,username:str):
        try:
            redis_cache.delete(cls._name_key(username))
            return True
        except Exception as e:
            logger.error(f'删除用户名{username}缓存失败:{e}')
            return False

    @classmethod
    def get_by_email(cls,email:str):
        '''通过邮箱反查user_id'''
        try:
            result=redis_cache.get(cls._email_key(email),for_write=False)
            return int(result) if result else None
        except Exception as e:
            logger.error(f'获取邮箱{email}缓存失败:{e}')
            return None

    @classmethod
    def set_by_email(cls,email:str,user_id:int):
        try:
            return redis_cache.set(
                cls._email_key(email),
                user_id,
                expire=cls.NAME_INDEX_TTL,
                for_write=True
            )
        except Exception as e:
            logger.error(f'设置邮箱{email}缓存失败: {e}')
            return False

    @classmethod
    def invalidate_by_email(cls, email: str) -> bool:
        try:
            redis_cache.delete(cls._email_key(email))
            return True
        except Exception as e:
            logger.error(f'删除邮箱{email}缓存失败: {e}')
            return False
    #=============批量预加载===================
    @classmethod
    def preload_profiles(cls,user_ids:list[int]):
        '''
        批量预加载用户资料（用于帖子列表反查作者）
        返回:{user_id:profile_dict,....}
        '''
        if not user_ids:
            return{}
        profiles={}
        for uid in set(user_ids):
            data=cls.get_profile(uid)
            if data:
                profiles[uid]=data
        return profiles

    #==============延迟双删=============
    @classmethod
    def double_invalidate(cls, user_id: int, username: str = None, email: str = None):
        """
        用户更新/删除后的延迟双删
        第一次：立即删除 profile + 索引
        第二次：Celery 延迟 2 秒删除（防主从延迟回填脏数据）
        """
        cls.invalidate(user_id)
        if username:
            cls.invalidate_by_username(username)
        if email:
            cls.invalidate_by_email(email)

        try:
            from core.celery_app import celery_app
            celery_app.send_task(
                'tasks.user_tasks.delayed_invalidate',
                args=(user_id, username, email),
                countdown=2
            )
        except Exception as e:
            logger.warning(f'调度用户缓存延迟删除失败，降级为线程: {e}')
            cls._threaded_delayed_invalidate(user_id, username, email)

    @classmethod
    def _threaded_delayed_invalidate(cls, user_id: int, username: str = None, email: str = None):
        """线程降级：延迟 2 秒后再次删除"""
        def _delayed():
            time.sleep(2)
            cls.invalidate(user_id)
            if username:
                cls.invalidate_by_username(username)
            if email:
                cls.invalidate_by_email(email)
        threading.Thread(target=_delayed, daemon=True).start()





