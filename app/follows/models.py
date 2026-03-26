from core import db
from datetime import datetime, timezone

class Follow(db.Model):
	__tablename__ = 'follows'

	id = db.Column(db.Integer, primary_key=True)
	follower_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
	followed_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
	created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
	is_deleted = db.Column(db.Boolean, default=False, nullable=False, index=True)

	__table_args__ = (
			db.UniqueConstraint('follower_id', 'followed_id', name='unique_follow_relationship'),
	)

				# 关系定义
	follower = db.relationship(
					'User', foreign_keys=[follower_id], back_populates='following', lazy='select'
				)
	followed = db.relationship(
					'User', foreign_keys=[followed_id], back_populates='followers', lazy='select'
				)

	def __repr__(self):
		return f'<Follow {self.follower_id}->{self.followed_id}>'

