

class TestPostSearchService:
    """帖子搜索服务单元测试"""

    def test_calculate_hot_score_basic(self, app):
        from services.search.services import PostSearchService
        with app.app_context():
            score = PostSearchService._calculate_hot_score({
                "like_count": 10,
                "comment_count": 5,
            })
            assert score == 20

    def test_index_post(self, app, monkeypatch):
        from unittest.mock import MagicMock

        from services.search.services import PostSearchService
        fake_doc = MagicMock()
        fake_doc.index.return_value = {"result": "created", "_id": "123"}
        monkeypatch.setattr('services.search.services.PostDocument', fake_doc)
        with app.app_context():
            result = PostSearchService.index_post({
                "id": 123,
                "content": "test",
                "user_id": 1,
                "created_at": "2024-01-01T00:00:00+00:00",
            })
            assert result is not None

    def test_update_post(self, app, monkeypatch):
        from unittest.mock import MagicMock

        from services.search.services import PostSearchService
        fake_doc = MagicMock()
        fake_doc.update.return_value = {"result": "updated"}
        monkeypatch.setattr('services.search.services.PostDocument', fake_doc)
        with app.app_context():
            result = PostSearchService.update_post(123, content="updated")
            assert result["result"] == "updated"

    def test_delete_post(self, app, monkeypatch):
        from unittest.mock import MagicMock

        from services.search.services import PostSearchService
        fake_doc = MagicMock()
        fake_doc.delete.return_value = {"result": "deleted"}
        monkeypatch.setattr('services.search.services.PostDocument', fake_doc)
        with app.app_context():
            result = PostSearchService.delete_post(123)
            assert result["result"] == "deleted"

    def test_search_empty(self, app, monkeypatch):
        from unittest.mock import MagicMock

        from services.search.services import PostSearchService
        fake_repo = MagicMock()
        fake_repo.search.return_value = ([], 0)
        monkeypatch.setattr('services.search.services.PostSearchRepository', fake_repo)
        with app.app_context():
            result = PostSearchService.search("test", page=1, per_page=20)
            assert result["total"] == 0
            assert len(result["items"]) == 0

    def test_search_with_results(self, app, monkeypatch):
        from unittest.mock import MagicMock

        from services.search.services import PostSearchService
        fake_repo = MagicMock()
        fake_repo.search.return_value = (
            [{"id": 1, "content": "hello"}, {"id": 2, "content": "world"}],
            2
        )
        monkeypatch.setattr('services.search.services.PostSearchRepository', fake_repo)
        with app.app_context():
            result = PostSearchService.search("test", page=1, per_page=20)
            assert result["total"] == 2
            assert len(result["items"]) == 2

    def test_search_pagination(self, app, monkeypatch):
        from unittest.mock import MagicMock

        from services.search.services import PostSearchService
        fake_repo = MagicMock()
        fake_repo.search.return_value = ([{"id": 1}] * 20, 50)
        monkeypatch.setattr('services.search.services.PostSearchRepository', fake_repo)
        with app.app_context():
            result = PostSearchService.search("test", page=1, per_page=20)
            assert result["pagination"]["total_pages"] == 3
            assert result["pagination"]["has_next"] is True
            assert result["pagination"]["has_prev"] is False
