from marshmallow import Schema, fields


class PaginationRequestSchema(Schema):
    page = fields.Int(load_default=1)
    size = fields.Int(load_default=20)