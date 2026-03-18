from marshmallow import Schema, fields, validate, validates_schema, ValidationError
from datetime import datetime

class LikeCreateSchema(Schema):
    """点赞操作请求模式（用于参数验证）"""
    post_id = fields.Integer(validate=validate.Range(min=1), required=False, allow_none=True)
    comment_id=fields.Integer(validate=validate.Range(min=1),required=False,allow_none=True)

    @validates_schema
    def validate_either(self, data, **kwargs):
        has_post = data.get('post_id')is not None
        has_comment=data.get('comment_id')is not None
        if not (has_post or has_comment):
            raise ValidationError('必须传入post_id或comment_id')
        if has_post and has_comment:
            raise ValidationError('不能同时传入post_id和comment_id')


class LikeSchema(Schema):
    """点赞记录响应模型"""
    id = fields.Integer(dump_only=True)
    post_id = fields.Integer(dump_only=True, allow_none=True)
    comment_id = fields.Integer(dump_only=True, allow_none=True) 
    user_id = fields.Integer(dump_only=True)
    created_at = fields.DateTime(dump_only=True)



like_create_schema = LikeCreateSchema()
like_schema = LikeSchema()
likes_schema = LikeSchema(many=True)

