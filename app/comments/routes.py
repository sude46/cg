from flask import request,current_app
from flask_jwt_extended import jwt_required,get_jwt_identity
from flask_restx import Namespace,Resource,fields,reqparse,Api
import traceback
from . import comments_bp
from .services import CommentService
from .schemas import (comment_create_schema,comment_update_schema,comment_schema,comments_schema)
from app.common.exceptions import (ResourceNotFoundError,PermissionError,ValidationError,DatabaseError,ConflictError)
from utils.decorators import validate_json
from utils.response import success_response,fail_response,ResponseCode
from utils.pagination import get_pagination_params


api_restx=Api(
        comments_bp,
        version='1.0',
        title='评论API',
        description='提供评论相关的API接口',
        security='Bearer',
        doc='/docs' 
        )
api=Namespace('comments',description='评论相关操作',security='Bearer')


comments_parser=reqparse.RequestParser()
comments_parser.add_argument('page',type=int,default=1,help='页码',location='args')
comments_parser.add_argument('per_page',type=int,default=20,help='每页数量（默认20，最大100）',location='args')


@api.route('')
class CommentListResource(Resource):
    @api.doc('create_comment')
    @api.response(201,'评论创建成功')
    @api.response(400,'参数错误')
    @api.response(401,'未授权')
    @api.response(404,'帖子不存在')
    @api.response(409,'评论冲突')
    @jwt_required()
    @validate_json(comment_create_schema)
    def post(self):
        '''创建新评论'''
        current_user_id=get_jwt_identity()
        data=request.get_json()
        current_app.logger.info(f'用户{current_user_id}尝试创建新评论:{data}')
        try:
            result=CommentService.create_comment(user_id=current_user_id,data=data)
            current_app.logger.info(f'用户{current_user_id}成功创建评论,评论ID:{result["comment"].id}')
            return success_response(data=result['comment']),201
        except ValidationError as e:
            current_app.logger.error(f'用户{current_user_id}创建评论失败:参数错误-{e}')
            return fail_response(code=ResponseCode.VALIDATION_ERROR,error_msg=str(e)),400
        except ResourceNotFoundError as e:
            current_app.logger.warning(f'用户{current_user_id}创建评论失败:{e}')
            return fail_response(code=ResponseCode.RESOURCE_NOT_FOUND,error_msg=str(e)),404
        except ConflictError as e:
            current_app.logger.warning(f'用户{current_user_id}创建评论失败:冲突错误-{e}')
            return fail_response(code=ResponseCode.CONFLICT,error_msg=str(e)),409
        except DatabaseError as e:
            current_app.logger.error(f'用户{current_user_id}创建评论失败：数据库错误-{e}')
            return fail_response(code=ResponseCode.INTERNAL_ERROR,error_msg=str(e)),500
        except Exception as e:
            current_app.logger.critical(
                    f'用户{current_user_id}创建评论时发生未知错误:{e}\n{traceback.format_exc()}'
                    )
            return fail_response(code=ResponseCode.INTERNAL_ERROR,error_msg='服务器内部错误'),500

@api.route('/<int:comment_id>')
@api.param('comment_id','评论ID')
class CommentResource(Resource):
    @api.doc('get_comment')
    @api.response(200,'获取评论成功')
    @api.response(404,'评论不存在')
    def get(self,comment_id):
        '''根据ID获取评论详情'''
        current_app.logger.debug(f'尝试获取评论详情，评论ID:{comment_id}')
        try:
            comment_data=CommentService.get_comment_by_id(comment_id)
            current_app.logger.info(f'成功获取评论详情，评论ID:{comment_id}')
            return success_response(data=comment_data),200
        except ResourceNotFoundError as e:
            current_app.logger.warning(f'获取评论详情失败:{e}')
            return fail_response(code=ResponseCode.RESOURCE_NOT_FOUND,error_msg=str(e)),404
        except Exception as e:
            current_app.logger.error(
                    f'获取评论ID{comment_id}详情时发生错误:{e} \n {traceback.format_exc()}'
                    )
            return fail_response(code=ResponseCode.INTERNAL_ERROR,error_msg='服务器内部错误'),500
    @api.doc('update_comment')
    @api.response(200,'评论更新成功')
    @api.response(400,'参数错误')
    @api.response(401,'未授权')
    @api.response(403,'权限不足')
    @jwt_required()
    @validate_json(comment_update_schema)
    def put(self,comment_id):
        '''更新评论内容'''
        current_user_id=get_jwt_identity()
        data=request.get_json()
        current_app.logger.info(f'用户{current_user_id}尝试更新评论，评论ID:{comment_id},新内容{data}')

        try:
            result=CommentService.update_comment(comment_id=comment_id,user_id=current_user_id,data=data)
            current_app.logger.info(f'用户{current_user_id}成功更新评论,评论ID:{comment_id}')
            return success_response(data=result,message='评论更新成功'),200
        except ValidationError as e:
            current_app.logger.error(f'用户{current_user_id}更新评论ID{comment_id}失败:参数错误{e}')
            return fail_response(code=ResponseCode.VALIDATION_ERROR,error_msg=str(e)),400
        except ResourceNotFoundError as e:
            current_app.logger.error(f'用户{current_user_id}更新失败:{e}')
            return fail_response(code=ResponseCode.RESOURCE_NOT_FOUND,error_msg=str(e)),404
        except PermissionError as e:
            current_app.logger.error(f'用户{current_user_id}更新评论ID{comment_id}失败:权限不足{e}')
            return fail_response(code=ResponseCode.PERMISSION_DENIED,error_msg=str(e)),403
        except DatabaseError as e:
            current_app.logger.error(f'用户{current_user_id}更新评论ID{comment_id}失败:数据库错误-{e}')
            return fail_response(code=ResponseCode.INTERNAL_ERROR,error_msg=str(e)),500
        except Exception as e:
            current_app.logger.critical(
                    f'用户{current_user_id}更新评论ID{comment_id}时发生未知严重错误:{e}\n{traceback.format_exc()}'
                    )
            return fail_response(code=ResponseCode.INTERNAL_ERROR,error_msg='服务器内部错误'),500

    @api.doc('delete_comment')
    @api.response(200,'评论删除成功')
    @api.response(401,'未授权')
    @api.response(403,'权限不足')
    @jwt_required()
    def delete(self,comment_id):
        '''删除评论'''
        current_user_id=get_jwt_identity()
        current_app.logger.info(f'用户{current_user_id}尝试删除评论,评论ID:{comment_id}')
        try:
           result=CommentService.delete_comment(comment_id=comment_id,user_id=current_user_id)
           current_app.logger.info(f'用户{current_user_id}成功删除评论,评论ID:{comment_id}')
           return success_response(message='评论删除成功'),200
        except ResourceNotFoundError as e:
           current_app.logger.warning(f'用户{current_user_id}删除评论失败:{e}')
           return fail_response(code=ResponseCode.RESOURCE_NOT_FOUND,error_msg=str(e)),404
        except PermissionError as e:
           current_app.logger.warning(f'用户{current_user_id}删除评论ID{comment_id}失败:权限不足-{e}')
           return fail_response(code=ResponseCode.PERMISSION_DENIED,error_msg=str(e)),403
        except DatabaseError as e:
           current_app.logger.error(f'用户{current_user_id}删除评论ID{comment_id}失败:数据库错误-{e}')
           return fail_response(code=ResponseCode.INTERNAL_ERROR,error_msg=str(e)),500
        except Exception as e:
           current_app.logger.critical(
                   f'用户{current_user_id}删除评论ID{comment_id}时发生未知严重错误:{e}\n{traceback.format_exc()}'
                   )
           return fail_response(code=ResponseCode.INTERNAL_ERROR,error_msg='服务器内部错误'),500
        
@api.route('/posts/<int:post_id>/comments')
@api.param('post_id','帖子ID')
class PostCommentsResource(Resource):
    @api.doc('get_post_comments')
    @api.expect(comments_parser)
    @api.response(200,'获取帖子评论成功')
    @api.response(404,'帖子不存在')
    @api.response(500,'服务器内部错误')
    def get(self, post_id):
        '''根据帖子ID获取评论列表（符合 /posts/{id}/comments 层级）'''
        args=comments_parser.parse_args()
        page,per_page=get_pagination_params()
        current_app.logger.info(f'尝试获取帖子ID{post_id}的评论列表，页码:{page},每页数量:{per_page}')

        try:
            result=CommentService.get_comments_by_post_id(
                    post_id=post_id,
                    page=page,
                    per_page=per_page
                    )
            current_app.logger.info(f'成功获取帖子ID{post_id}的评论列表，共{result["pagination"]["total"]}条评论')
            return success_response(data=result,message='获取评论列表成功'),200
        except ResourceNotFoundError as e:
            current_app.logger.warning(f'获取帖子评论列表失败:{e}')
            return fail_response(code=ResponseCode.RESOURCE_NOT_FOUND,error_msg=str(e)),404
        except DatabaseError as e:
            current_app.logger.error(f'获取帖子ID{post_id}评论列表失败:数据库错误-{e}')
            return fail_response(code=ResponseCode.INTERNAL_ERROR,error_msg=str(e)),500
        except Exception as e:
            current_app.logger.error(
                    f'获取帖子ID{post_id}评论列表时发生错误:{e}\n{traceback.format_exc()}'
                    )
            return fail_response(code=ResponseCode.INTERNAL_ERROR,error_msg='服务器内部错误'),500

api_restx.add_namespace(api)


