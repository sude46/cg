from marshmallow import Schema,fields,validate,ValidationError,validates
from datetime import datetime

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
    created_at = fields.DateTime(dump_only=True, metadata={'description': '创建时间'})
    updated_at = fields.DateTime(dump_only=True, metadata={'description': '更新时间'})

comment_create_schema=CommentCreateSchema()
comment_update_schema=CommentUpdateSchema()
comment_schema=CommentSchema()
comments_schema=CommentSchema(many=True) #用于序列化多个评论
