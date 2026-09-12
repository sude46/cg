from core.security import security_manager


class TokenService:
    @staticmethod
    def generate_tokens(user_id:int,expires_in:int=3600):
        '''生成密码重置令牌'''
        return security_manager.generate_jwt_token(
            user_id=user_id,
            token_type='reset'
        )

    @staticmethod
    def verify_reset_token(token:str):
        '''验证重置令牌'''
        return security_manager.verify_jwt_token(token,token_type='reset')
