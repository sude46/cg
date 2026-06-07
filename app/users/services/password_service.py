from core import db
from core.extensions import bcrypt
from core.security import password_validator

class PasswordService:
    MAX_HISTORY=5

    def hash_password(self,plain_password:str):
        return bcrypt.generate_password_hash(plain_password).decode('utf-8')
    
    def verify_password(self,hashed:str,plain:str):
        return bcrypt.check_password_hash(hashed,plain)
    
    def is_password_reused(self,user,new_password:str):
        from app.users.models import PasswordHistory
        '''检查新密码是否在用户的密码历史中被重用'''
        if not user.password_histories:
            return False
        histories=user.password_histories.limit(self.MAX_HISTORY).all()
        for history in histories:
            if self.verify_password(history.password_hash,new_password):
                return True
        return False
    
    def update_password(self,user,new_password:str):
        '''带历史记录的记录的密码更新（事务内更新）'''
        from app.users.models import PasswordHistory

        #保存旧密码到历史表
        if user.password_hash:
            db.session.add(PasswordHistory(
                user_id=user.id,
                password_hash=user.password_hash
            ))
            #清理超出限制的
            old_records=user.password_histories.offset(self.MAX_HISTORY).all()
            for recode in old_records:
                db.session.delete(recode)
        #更新用户密码
        user.password_hash=self.hash_password(new_password)


password_service = PasswordService()

