from marshmallow import Schema, fields, validate

from utils.schema_fields import UTCDateTime


class NotificationCreateSchema(Schema):
    '''创建通知的请求'''
    user_id=fields.Integer(required=True,validate=validate.Range(min=1))
    actor_id=fields.Integer(required=False,allow_none=True)
    type=fields.String(required=True,validate=validate.OneOf(['like','comment','follow','system']))
    resource_id=fields.Integer(required=False,allow_none=True)
    resource_type=fields.String(required=False,allow_none=True)
    content=fields.String(required=True,validate=validate.Length(min=1))

class NotificationSchema(Schema):
    '''通知响应数据的序列化'''
    id=fields.Integer(dump_only=True)
    user_id=fields.Integer(dump_only=True)
    actor_id=fields.Integer(dump_only=True,allow_none=True)
    type=fields.String(dump_only=True)
    resource_id=fields.Integer(dump_only=True,allow_none=True)
    resource_type=fields.String(dump_only=True,allow_none=True)
    content=fields.String(dump_only=True)
    is_read=fields.Boolean(dump_only=True)
    created_at=UTCDateTime(dump_only=True)
    actor_name=fields.Method('get_actor_name',dump_only=True)

    def get_actor_name(self,obj):
        actor=getattr(obj,'actor',None)
        return actor.username if actor else None


notification_create_schema=NotificationCreateSchema()
notification_schema=NotificationSchema()
notifications_schema=NotificationSchema(many=True)

