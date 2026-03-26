from datetime import datetime,timezone,timedelta

class AccountLockService:
    MAX_LOGIN_FAILS=5
    LOCK_DURATION_MINUTES=20

    def is_locked(self,user):
        if  not user.lock_until:
            return False
        return datetime.now(timezone.utc)<user.lock_until
    
    def record_failed_attempt(self,user):
        user.login_fail_count+=1
        if user.login_fail_count>=self.MAX_LOGIN_FAILS:
            user.lock_until=datetime.now(timezone.utc)+timedelta(minutes=self.LOCK_DURATION_MINUTES)

    def reset_attempts(self,user):
        user.login_fail_count=0
        user.lock_until=None