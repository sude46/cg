def success_response(data=None, message: str = ""):
    return {
        "code": 0,
        "data": data,
        "message": message,
    }


def pagination_response(items, page: int, size: int, total: int):
    return {"list": items, "page": page, "size": size, "total": total}
