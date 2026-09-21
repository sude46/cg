from marshmallow import Schema, fields, validate

from utils.schema_fields import UTCDateTime


#用户基础信息子Schema（进返回关注列表所需字段）
class UserSimpleSchema(Schema):
    id=fields.Int()
    username=fields.Str()

class FollowCreateSchema(Schema):
    '''创建关注请求模式'''
    followed_id = fields.Int(
        required=True,
        validate=validate.Range(min=1, error='被关注用户ID必须为正整数')
    )

class FollowResponseSchema(Schema):
    '''关注关系响应模式'''
    id = fields.Int()
    follower_id = fields.Int()
    followed_id = fields.Int()
    created_at = UTCDateTime()
    follower = fields.Nested(UserSimpleSchema)
    followed = fields.Nested(UserSimpleSchema)
class FollowListSchema(Schema):
    follows = fields.List(fields.Nested(FollowResponseSchema()))
    pagination = fields.Dict(
        keys=fields.Str(),
        values=fields.Str(),
        metadata={'description': '分页信息: page, per_page, total, pages'}
    )

follow_created_schema = FollowCreateSchema()
follow_response_schema = FollowResponseSchema()
follow_list_schema = FollowListSchema()
