from marshmallow import Schema, ValidationError, fields, validate, validates


class CreateConversationSchema(Schema):
    peer_id = fields.Int(
        required=True,
        validate=validate.Range(min=1, error='peer_id 必须是合法的用户ID'),
    )


class SendMessageSchema(Schema):
    # 客户端幂等去重键：MVP 非必填，列已保留
    client_msg_id = fields.Str(
        required=False,
        allow_none=True,
        validate=validate.Length(min=1, max=64, error='client_msg_id 长度必须在1-64之间'),
    )
    content = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=500, error='私信内容长度必须在1-500之间'),
    )
    type = fields.Int(
        load_default=0,
        validate=validate.OneOf([0, 1, 2, 3, 4, 9], error='不支持的 message type'),
    )
    extra = fields.Dict(required=False, allow_none=True)

    @validates('content')
    def validate_content_not_blank(self, value, **kwargs):
        if not value.strip():
            raise ValidationError('私信内容不能为纯空格')
        return value.strip()


class MarkReadSchema(Schema):
    conversation_id = fields.Int(
        required=True,
        validate=validate.Range(min=1, error='conversation_id 必须是合法的会话ID'),
    )
    # 不传则用会话的最后一条消息 id 作为已读位点
    last_read_id = fields.Int(
        required=False,
        allow_none=True,
        validate=validate.Range(min=1, error='last_read_id 必须是合法的消息ID'),
    )
