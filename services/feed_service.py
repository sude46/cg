class FeedService:
    """预留：时间线/推荐流相关服务。"""

    def get_feed(self, user_id: int, page: int = 1, size: int = 20):
        raise NotImplementedError


feed_service = FeedService()