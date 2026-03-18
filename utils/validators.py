import re
from typing import Optional,Union,List

#用户名验证
def validate_username(username:str)->bool:
    '''验证用户名格式'''
    if not username or len(username)<3 or len(username)>20:
        return False
    pattern = r'^[a-zA-Z0-9_]+$'
    return bool(re.match(pattern,username))

#密码验证
def validate_password(password):
	if not password or len(password)<8:
		return False
	if not re.search(r'\d',password) or not re.search(r'[a-zA-Z]',password):
		return False
	return True

#邮箱认证
def validate_email(email):
    if not email:
        return False
    if not re.match(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',email):
         return False
    return True

#验证内容长度
def validate_content_length(content:str,max_length:int=1000)->bool:
    return content and len(content)<=max_length

#验证图片URL格式
def validate_image_url(url:str)->bool:
    if not url:
        return True
    pattern=r'^https?://.+\.(jpg|jprg|png|gif|webp)(\?.*)?$'
    return bool(re.match(pattern,url,re.IGNORECASE))


