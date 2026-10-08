def register_all_blueprints(app):
    """集中注册所有蓝图"""
    blueprint_configs = [
        ("app.comments", "comments_bp", ""),
        ("app.follows", "follows_bp", ""),
        ("app.posts", "posts_bp", ""),
        ("app.likes", "likes_bp", ""),
        ("app.notifications", "notifications_bp", ""),
        ("app.users", "users_bp", ""),
        ("app.feeds", "feeds_bp", ""),
        ("app.uploads", "uploads_bp", ""),
        ("app.chats", "chats_bp", ""),
        ("app.common.health","health_bp",""),
    ]

    for module_path, bp_name, url_prefix in blueprint_configs:
        try:
            module = __import__(module_path, fromlist=[bp_name])
            blueprint = getattr(module, bp_name)

            # 关键修改2：判断前缀是否为空，为空则只传蓝图，不指定url_prefix
            if url_prefix.strip():  # 排除空字符串/空格
                app.register_blueprint(blueprint, url_prefix=url_prefix)
            else:
                app.register_blueprint(blueprint)  # 直接用模块内的url_prefix

            # 日志优化：打印实际注册的前缀
            actual_prefix = blueprint.url_prefix or "根路径"
            app.logger.info(f"✅ 成功注册蓝图 {bp_name}，前缀：{actual_prefix}")

        except Exception as e:
            app.logger.error(f"❌ 注册蓝图 {bp_name} 失败：{str(e)}", exc_info=True)

    app.logger.info("📌 所有蓝图注册完成")
