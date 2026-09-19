import logging

from flask import current_app, request, send_from_directory
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restx import Api, Namespace, Resource

from middlewares import route_limit
from utils.response import success_response

from . import uploads_bp
from .services import UploadService

logger = logging.getLogger(__name__)

authorizations = {
    'Bearer': {
        'type': 'apiKey',
        'in': 'header',
        'name': 'Authorization',
        'description': 'JWT Token (Bearer token)'
    }
}

api_restx = Api(
    uploads_bp,
    version='1.0',
    title='上传API',
    description='提供图片上传接口',
    authorizations=authorizations,
    security='Bearer',
    doc='/docs'
)

api = Namespace('uploads', description='图片上传', path='/')


@api.route('')
class UploadResource(Resource):
    @api.doc('upload_image', description='后端中转上传图片（multipart/form-data，字段名 file）')
    @api.response(200, '上传成功')
    @jwt_required()
    @route_limit('10 per minute')
    def post(self):
        '''上传图片，返回可回显的 URL'''
        from app.common.exceptions import ValidationError

        user_id = get_jwt_identity()
        if 'file' not in request.files:
            raise ValidationError('缺少上传文件')
        result = UploadService.save_image(user_id, request.files['file'])
        return success_response(data=result, message='上传成功'), 200


@api.route('/files/<path:key>')
class UploadedFile(Resource):
    @api.doc('get_uploaded_file', description='读取本地上传的图片（STORAGE_BACKEND=local）')
    def get(self, key):
        '''读取本地上传的图片（公开，供 <img> 直接加载）'''
        folder = current_app.config['UPLOAD_FOLDER']
        return send_from_directory(folder, key)


api_restx.add_namespace(api)
