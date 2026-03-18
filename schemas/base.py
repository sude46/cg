from marshmallow import Schema


class BaseSchema(Schema):
    """统一的序列化基类，提供 to_dict 简化输出。"""

    def to_dict(self, obj=None, many: bool = None):
        return self.dump(obj if obj is not None else self, many=many)