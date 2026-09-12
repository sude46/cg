from flask import request


def get_pagination_params(default_page=1, default_per_page=10):
    """统一获取分页参数，避免重复代码"""
    try:
        page = int(request.args.get('page', default_page))
        per_page = int(request.args.get('per_page', default_per_page))
        # 边界值校验
        page = page if page >= 1 else default_page
        per_page = per_page if 1 <= per_page <= 100 else default_per_page
        return page, per_page
    except (ValueError, TypeError):
        return default_page, default_per_page
