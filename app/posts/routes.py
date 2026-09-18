from flask import g, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restx import Api, Namespace, Resource, fields

from middlewares import route_limit
from utils.decorators import ownership_required, validate_json
from utils.pagination import get_pagination_params
from utils.response import ResponseCode, fail_response, paginated_response, success_response

from . import posts_bp
from .models import Post
from .schemas import CreatePostSchema, UpdatePostSchema, post_schema, posts_schema
from .services import PostService

authorizations = {
    'Bearer': {
        'type': 'apiKey',
        'in': 'header',
        'name': 'Authorization',
        'description': 'JWT Token (Bearer token)'
    }
}

api_restx=Api(
	posts_bp,
	version='1.0',
	title='帖子API',
	description='提供帖子相关的API接口',
	authorizations=authorizations,
	security='Bearer',
	doc='/docs'
)

api=Namespace('posts',description='帖子相关操作',path='/')

# Swagger请求模型
post_create_model = api.model('PostCreate', {
    'content': fields.String(required=True, description='帖子内容（1-1000字符）'),
    'image_url': fields.String(required=False, description='图片URL（可选）')
})

post_update_model = api.model('PostUpdate', {
    'content': fields.String(required=False, description='帖子内容（1-1000字符）'),
    'image_url': fields.String(required=False, description='图片URL（可选）')
})


@api.route('')
class PostList(Resource):
	@api.doc(
		description='获取帖子列表',
		params={
			'page': '页码，默认1',
			'per_page': '每页数量,默认20',
			'user_id': '用户ID（可选，获取指定用户的帖子）'
		},
		security='Bearer'
	)
	@api.response(200,'获取成功')
	@jwt_required(optional=True)
	def get(self):
		page = request.args.get('page', 1, type=int)
		per_page = request.args.get('per_page', 20, type=int)
		user_id = request.args.get('user_id', type=int)
		current_user_id = get_jwt_identity()


		result = PostService.get_posts(
				page=page,
				per_page=per_page,
				user_id=user_id,
				current_user_id=current_user_id,
			)
		# 序列化帖子列表
		posts_data = posts_schema.dump(result['items'])
		return paginated_response(
				posts_data,
				result['pagination'],
				extra={'liked_post_ids': list(result.get('liked_post_ids', []))},
				message='获取帖子列表成功'
			), 200

	@api.doc(description='创建新帖子',security='Bearer')
	@api.expect(post_create_model, validate=False)
	@api.response(201,'创建成功')
	@jwt_required()
	@validate_json(CreatePostSchema)
	@route_limit("10 per minute")
	def post(self):
		'''创建新帖子'''
		data = getattr(g, 'validated_json', request.get_json())
		current_user_id = get_jwt_identity()

		post = PostService.create_post(
				user_id=current_user_id,
				content=data['content'],
				image_url=data.get('image_url'),
			)
		return success_response(
				data=post_schema.dump(post),
				message='创建帖子成功'
			), 201

@api.route('/<int:post_id>')
class PostDetail(Resource):
	@api.doc(
		description='获取帖子详情',
		params={'post_id':'帖子ID'},
		security='Bearer'
		)
	@api.response(200,'获取成功' )
	@jwt_required(optional=True)
	def get(self,post_id):
		current_user_id = get_jwt_identity()

		result = PostService.get_post(
				post_id=post_id,
				current_user_id=current_user_id,
			)
		# get_post 已返回序列化后的 dict，直接使用，避免二次序列化
		post_data = result['post']
		return success_response(
				data={
					'post': post_data,
					'has_liked': result['has_liked'],
					'is_following': result.get('is_following', False)
				},
				message='获取帖子详情成功'
			), 200
	@api.doc(
		description='更新帖子',
		params={'post_id':'帖子ID'},
		security='Bearer'
		)
	@api.response(200,'更新成功')
	@jwt_required()
	@validate_json(UpdatePostSchema)
	@ownership_required(Post,'post_id')
	def put(self,post_id):
		data = getattr(g, 'validated_json', request.get_json())
		current_user_id = get_jwt_identity()

		post = PostService.update_post(
				post_id=post_id,
				user_id=current_user_id,
				content=data.get('content'),
				image_url=data.get('image_url'),
			)
		return success_response(
				data=post_schema.dump(post),
				message='更新帖子成功'
			), 200
	@api.doc(
		description='删除帖子',
		params={'post_id':'帖子id'},
		security='Bearer'
		)
	@api.response(200,'删除成功')
	@jwt_required()
	@ownership_required(Post,'post_id')
	def delete(self,post_id):
		'''删除帖子'''
		current_user_id = get_jwt_identity()

		PostService.delete_post(
				post_id=post_id,
				user_id=current_user_id,
			)
		return success_response(
				data=None,
				message='删除帖子成功'
			), 200

@api.route('/search')
class PostSearch(Resource):
	@api.doc(
		description='搜索帖子（支持 ES 智能搜索）',
		params={
			'q': '搜索关键词',
			'page': '页码，默认1',
			'per_page': '每页数量，默认20',
			'sort': '排序方式：relevance(相关度)、time(最新)、hot(最热)，默认relevance'
			},
		security='Bearer'
		)
	@api.response(200,'搜索成功')
	@jwt_required(optional=True)
	def get(self):
		'''搜索帖子'''
		query = request.args.get('q', '').strip()
		page, per_page = get_pagination_params()
		sort_by = request.args.get('sort', 'relevance')
		current_user_id = get_jwt_identity()

		if not query:
			return fail_response(ResponseCode.VALIDATION_ERROR, '搜索关键词不能为空'), 400

		if sort_by not in ['relevance', 'time', 'hot']:
			sort_by = 'relevance'

		result = PostService.search_posts(
				query=query,
				page=page,
				per_page=per_page,
				current_user_id=current_user_id,
				sort_by=sort_by
			)

		# ES 搜索返回的已经是格式化数据，不需要再序列化
		if result.get('is_es_search'):
			posts_data = result['items']
		else:
			# 降级到数据库搜索，需要序列化
			posts_data = posts_schema.dump(result['items'])
		return paginated_response(
			posts_data,
			result['pagination'],
			extra={
				'liked_post_ids': list(result.get('liked_post_ids', [])),
				'search_engine': 'elasticsearch' if result.get('is_es_search') else 'database'
			},
			message='搜索帖子成功'
		), 200


@api.route('/hot-searches')
class HotSearches(Resource):
	@api.doc(
		description='获取热搜榜',
		params={'size': '返回数量，默认10'}
	)
	@api.response(200, '获取成功')
	def get(self):
		'''获取热搜榜'''
		size = request.args.get('size', 10, type=int)
		size = min(50, max(1, size))

		from services.search import PostSearchService
		hot_searches = PostSearchService.get_hot_searches(size=size)

		return success_response(
			data={'hot_searches': hot_searches},
			message='获取热搜榜成功'
		), 200


@api.route('/search/suggestions')
class SearchSuggestions(Resource):
	@api.doc(
		description='搜索建议（自动补全）',
		params={
			'q': '输入的关键词',
			'size': '返回数量，默认10'
		}
	)
	@api.response(200, '获取成功')
	def get(self):
		'''获取搜索建议'''
		keyword = request.args.get('q', '').strip()
		size = request.args.get('size', 10, type=int)

		if not keyword or len(keyword) < 1:
			return success_response(data={'suggestions': []}, message='获取成功'), 200

		from services.search import PostSearchService
		suggestions = PostSearchService.get_search_suggestions(keyword, size)

		return success_response(
			data={'suggestions': suggestions},
			message='获取搜索建议成功'
		), 200

api_restx.add_namespace(api)

