from markupsafe import escape

def html_escape(content):
    """
    HTML转义（防止XSS）
    :param content: 待转义内容（字符串/字典/列表）
    :return: 转义后的内容
    """
    if isinstance(content, str):
        return escape(content)
    elif isinstance(content, dict):
        # 递归转义字典中的所有值
        return {k: html_escape(v) for k, v in content.items()}
    elif isinstance(content, list):
        # 递归转义列表中的所有元素
        return [html_escape(item) for item in content]
    else:
        # 非字符串类型，直接返回
        return content
