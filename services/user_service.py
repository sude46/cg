from core import db
from app.users.models import User
from app.common import (ResourceNotFoundError,AuthorizationError,DatabaseError,ValidationError,pagination_utils)
from typing import Dict,Any
import logging

logger=logging.getLogger(__name__)

class UserService:
    @staticmethod
    def get_user_profile(user_id:int,current_user_id:int=None)->Dict[str,Any]:
        '''获取用户公开资料'''
        user=User.query.get(user_id)
        if not user:
            raise ResourceNotFoundError('用户')
        #基础资料(所有人可见)
        profile={
                'id':user.id,
                'username':user.username,
                'avatar_url':user.avatar_url,
                'bio':user.bio,
                'created_at':user.created_at.isformat(),
                'post_count':user.posts.count(),
                'follower_count':user.followers.count(),
                'following_count':user.following.count()
                }
        if current_user_id==user_id:
            profile['email']=user.email #邮箱仅自己可见
        return {'user':profile}
    @staticmethod
    def update_user_profile(user_id:int,**kwargs):
        '''更新用户资料'''
        user=User.query.get(user_id)
        if not user:
            raise ResourceNotFoundError('用户')
        try:
            #允许更新的字段:头像、简介
            if 'avatar_url' in kwargs:
                avatar=kwargs['avatar_url'].strip() if kwargs['avatar_url']else None
                if avatar and len(avatar)>500:
                    raise ValidationError('头像URL长度不能超过500字符')
                user.avatar_url=avatar
            if 'bio' in kwargs:
                bio=kwargs['bio'].strip() if kwargs['bio'] else None
                if bio and len(bio)>200:
                    raise ValidationError('个人简介不能超过200个字符')
                user.bio=bio
            db.session.commit()
            logger.info(f'用户{user_id}更新资料成功')
            return {
                    'message':'资料更新成功',
                    'user':UserService.get_user_profile(user_id)['user']
                    }
        except Exception as e:
            db.session.rollback()
            logger.error(f'更新资料失败:{str(e)}')
            if isinstance(e,ValidationError):
                raise
            raise DatabaseError()

    @staticmethod
    def search_users(keyword:str,page:int=1,per_page:int=20)->Dict[str,Any]:
        '''搜索用户'''
        if not keyword.strip():
            raise ValidationError('搜索关键词不能为空')
        query=User.query.filter(
                User.username.ilike(f'%{keyword.strip()}%')
                ).order_by(User.username)
        result=pagination_utils.paginate(query,page,per_page)
        return{
                'users':[{'id':u.id,'username':u.username,'avatar_url':u.avatar_url} for u in result['items']],
                'pagination':result['pagination']
                }

