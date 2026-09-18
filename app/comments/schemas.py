from marshmallow import Schema, fields, validate

from utils.schema_fields import UTCDateTime


class CommentCreateSchema(Schema):
    '''评论创建请求的数据验证Schema'''
    content=fields.String(
            required=True,
            validate=validate.Length(min=1,max=500),
            error_messages={'required':'评论内容不能为空','length':'评论内容长度必须在1-500字符之间'}
            )
    post_id=fields.Integer(
            required=True,
            validate=validate.Range(min=1),
            error_messages={'required':'帖子ID不能为空','range':'帖子ID必须是正整数'}
            )

class CommentUpdateSchema(Schema):
    '''评论更新请求的数据验证'''
    content=fields.String(
            required=True,
            validate=validate.Length(min=1,max=500),
            error_messages={'required':'评论内容不能为空','length':'评论内容长度必须在1-500'}
            )
class CommentSchema(Schema):
    id = fields.Integer(dump_only=True, metadata={'description': '评论id'})
    content = fields.String(dump_only=True, metadata={'description': '评论内容'})
    post_id = fields.Integer(dump_only=True, metadata={'description': '所属帖子id'})
    user_id = fields.Integer(dump_only=True, metadata={'description': '评论用户id'})
    username = fields.Method('get_username', dump_only=True, metadata={'description': '评论者用户名'})
    avatar_url = fields.Method('get_avatar_url', dump_only=True, allow_none=True)
    like_count = fields.Integer(dump_only=True, dump_default=0)
    created_at = UTCDateTime(dump_only=True, metadata={'description': '创建时间'})
    updated_at = UTCDateTime(dump_only=True, metadata={'description': '更新时间'})

    def get_username(self, obj):
        author = getattr(obj, 'author', None)
        return author.username if author else None

    def get_avatar_url(self, obj):
        author = getattr(obj, 'author', None)
        return author.avatar_url if author else None

comment_create_schema=CommentCreateSchema()
comment_update_schema=CommentUpdateSchema()
comment_schema=CommentSchema()
comments_schema=CommentSchema(many=True) #用于序列化多个评论
