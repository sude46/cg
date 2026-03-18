from flask import request, jsonify, g
from flask_jwt_extended import jwt_required,get_jwt_identity
from flask_restx import Api,Resource,fields,Namespace
from . import posts_bp
from .services import PostService
from .schemas import (
	CreatePostSchema,
	UpdatePostSchema
)
from utils.decorators import validate_json, rate_limit, ownership_required
from app.common.exceptions import (
    ResourceNotFoundError,
    ConflictError,
    PermissionError,
	ValidationError,
	DatabaseError
)

from utils.response import success_response,fail_response,ResponseCode,pagination_response
from utils.pagination import get_pagination_params


api_restx=Api(
	posts_bp,
	version='1.0',	
	title='帖子API',
	description='提供帖子相关的API接口',
	security='Bearer',
	doc='/docs'
)

api=Namespace('posts',description='帖子相关操作',security='Bearer')


@api.route('')
class PostList(Resource):
	@api.doc(
		description='获取帖子列表',
		params={
			'page': '页码，默认1',
			'per_page': '每页数量,默认20',
			'user_id': '用户ID（可选，获取指定用户的帖子）'
		},
		security='apiKey'
	)
	@api.response(200,'获取成功')
	@api.response(400,'参数错误')
	@jwt_required(optional=True)
	def get(self):
		page = request.args.get('page', 1, type=int)
		per_page = request.args.get('per_page', 20, type=int)
		user_id = request.args.get('user_id', type=int)
		current_user_id = get_jwt_identity()

		try:
			result = PostService.get_posts(
				page=page,
				per_page=per_page,
				user_id=user_id,
				current_user_id=current_user_id,
			)
			return success_response(
				data=result,
				message='获取帖子列表成功'
			), 200
		except ValidationError as e:
			return fail_response(
				code=ResponseCode.PARAM_ERROR,
				error_msg=str(e)
			), 400
		except Exception as e:
			return fail_response(
				code=ResponseCode.INTERNAL_ERROR,
				error_msg='服务器内部错误'
			), 500

	@api.doc(description='创建新帖子',security='apiKey')
	@api.response(201,'创建成功')
	@api.response(400,'参数错误')
	@api.response(401,'未授权')
	@jwt_required()
	@validate_json(CreatePostSchema)
	@rate_limit(30)
	def post(self):
		'''创建新帖子'''
		data = getattr(g, 'validated_json', request.get_json())
		current_user_id = get_jwt_identity()
		try:
			result = PostService.create_post(
				user_id=current_user_id,
				content=data['content'],
				image_url=data.get('image_url'),
			)
			return success_response(
				data=result,
				message='创建帖子成功'
			), 201
		except ValidationError as e:
			return fail_response(
				code=ResponseCode.PARAM_ERROR,
				error_msg=str(e)
			) , 400
		except Exception as e:
			return fail_response(
				code=ResponseCode.INTERNAL_ERROR,
				error_msg='服务器内部错误'
			), 500

@api.route('/<int:post_id>')
class PostDetail(Resource):
	@api.doc(
		description='获取帖子详情',
		params={'post_id':'帖子ID'},
		security='apiKey'
		)
	@api.response(200,'获取成功' )
	@api.response(404,'帖子不存在',)
	@jwt_required(optional=True)
	def get(self,post_id):
		current_user_id = get_jwt_identity()
		try:
			result = PostService.get_post_by_id(
				post_id=post_id,
				current_user_id=current_user_id,
			)
			return  success_response(
				data=result,
				message='获取帖子详情成功'
			), 200
		except ResourceNotFoundError as e:
			return fail_response(
				code=ResponseCode.RESOURCE_NOT_FOUND,
				error_msg=str(e)
			), 404
		except Exception as e:
			return fail_response(
				code=ResponseCode.INTERNAL_ERROR,
				error_msg='服务器内部错误'
			), 500
	@api.doc(
		description='更新帖子',
		params={'post_id':'帖子ID'},
		security='apiKey'
		)
	@api.response(200,'更新成功')
	@api.response(400,'参数错误')
	@api.response(403,'无权操作')
	@api.response(404,'帖子不存在')
	@jwt_required()
	@validate_json(UpdatePostSchema)
	@ownership_required('Post','post_id')
	def put(self,post_id):
		data = getattr(g, 'validated_json', request.get_json())
		current_user_id = get_jwt_identity()
		try:
			result = PostService.update_post(
				post_id=post_id,
				user_id=current_user_id,
				content=data.get('content'),
				image_url=data.get('image_url'),
				)
			return success_response(
				data=result,
				message='更新帖子成功'
			), 200
		except ResourceNotFoundError as e:
			return fail_response(
				code=ResponseCode.RESOURCE_NOT_FOUND,
				error_msg=str(e)
			), 404
		except PermissionError as e:
			return fail_response(
				code=ResponseCode.PERMISSION_DENIED,
				error_msg=str(e)
			), 403
	@api.doc(
		description='删除帖子',
		params={'post_id':'帖子id'},
		security='apiKey'
		)
	@api.response(200,'删除成功')
	@api.response(403,'无权操作')
	@api.response(404,'帖子不存在')
	@jwt_required()
	@ownership_required('Post','post_id')
	def delete(self,post_id):
		'''删除帖子'''
		current_user_id = get_jwt_identity()
		try:
			result = PostService.delete_post(
				post_id=post_id,
				user_id=current_user_id,
			)
			return  success_response(
				data=result,
				message='删除帖子成功'
			), 200
		except ResourceNotFoundError as e:
			return fail_response(
				code=ResponseCode.RESOURCE_NOT_FOUND,
				error_msg=str(e)
			), 404
		except PermissionError as e:
			return fail_response(
				code=ResponseCode.PERMISSION_DENIED,
				error_msg=str(e)
			), 403
		except Exception as e:
			return fail_response(
				code=ResponseCode.INTERNAL_ERROR,
				error_msg='服务器内部错误'
			), 500

@api.route('/<int:post_id>/likes')
class PostLike(Resource):
	@api.doc(
		description='点赞帖子',
		params={'post_id':'帖子'},
		security='apiKey'
		)
	@api.response(201,'点赞成功')
	@api.response(409,'已点赞')
	@api.response(401,'未认证')
	@api.response(404,'帖子不存在')
	@jwt_required()
	@rate_limit(60)
	def post(self,post_id):
		current_user_id = get_jwt_identity()
		try:
			result = PostService.like_post(
				post_id=post_id,
				user_id=current_user_id,
			)
			return success_response(
				data=result,
				message='点赞帖子成功'
			), 201
		except ConflictError as e:
			return fail_response(
				code=ResponseCode.CONFLICT,
				error_msg=str(e)
			), 409
		except ResourceNotFoundError as e:
			return fail_response(
				code=ResponseCode.RESOURCE_NOT_FOUND,
				error_msg=str(e)
			), 404
		except Exception as e:
			return fail_response(
				code=ResponseCode.INTERNAL_ERROR,
				error_msg='服务器内部错误'
			), 500

@api.route('/<int:post_id>/likes/<int:like_id>')
class PostUnlike(Resource):
	@api.doc(
		description='取消点赞',
		params={'post_id':'帖子ID','like_id':'点赞记录ID'},
		security='apiKey'
		)
	@api.response(200,'取消成功')
	@api.response(401,'未认证')
	@api.response(404,'点赞记录不存在/帖子不存在')
	@jwt_required()
	def delete(self,post_id, like_id):
		'''取消点赞'''
		current_user_id = get_jwt_identity()
		try:
			result = PostService.unlike_post(
				post_id=post_id,
				like_id=like_id,  # 传入like_id
				user_id=current_user_id,
			)
			return success_response(
				data=result,
				message='取消点赞成功'
			), 200
		except ResourceNotFoundError as e:
			return fail_response(
				code=ResponseCode.RESOURCE_NOT_FOUND,
				error_msg=str(e)
			), 404
		except Exception as e:
			return fail_response(
				code=ResponseCode.INTERNAL_ERROR,
				error_msg='服务器内部错误'
			), 500
@api.route('/search')
class PostSearch(Resource):
	@api.doc(
		description='搜索帖子',
		params={
			'q':'搜索关键词',
			'page':'页码，默认1',
			'per_page':'每页数量,默认20'
			},
		security='apiKey'
		)
	@api.response(200,'搜索成功')
	@api.response(400,'参数错误')
	@jwt_required(optional=True)
	def get(self):
		'''搜索帖子'''
		query = request.args.get('q', '').strip()
		page,per_page=get_pagination_params
		current_user_id = get_jwt_identity()
		if not query:
			return {'error': '搜索关键词不能为空'}, 400
		try:
			result = PostService.search_posts(
				query=query,
				page=page,
				per_page=per_page,
				current_user_id=current_user_id,
			)
			return success_response(
				data=result,
				message='搜索帖子成功'
			), 200
		except ValidationError as e:
			return fail_response(
				code=ResponseCode.VALIDATION_ERROR,
				error_msg=str(e)
			), 400
		except Exception as e:	
			return fail_response(
				code=ResponseCode.INTERNAL_ERROR,
				error_msg='服务器内部错误'
			), 500

api_restx.add_namespace(api)
		
