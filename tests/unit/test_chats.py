"""私信模块单测（不依赖外部服务，CI 同款环境变量下可跑）"""
import pytest

from app.chats.services import ChatService
from app.common.exceptions import AuthenticationError, ValidationError
from tests.unit.factories import UserFactory


class TestChatService:
    def test_send_and_read_flow(self, app, db_session, mock_redis):
        """发消息 → 收件人未读 +1 → 非成员被拒 → 已读清零 → 消息可拉取"""
        with app.app_context():
            a = UserFactory()
            b = UserFactory()
            conv = ChatService.create_conversation(a.id, {'peer_id': b.id})
            cid = conv['conversation_id']

            msg = ChatService.send_message(a.id, cid, {'content': '你好'})
            assert msg['receiver_id'] == b.id
            assert ChatService.get_unread_count(b.id)['unread_count'] == 1
            # 发送方自己不计未读
            assert ChatService.get_unread_count(a.id)['unread_count'] == 0

            # 非会话成员被拒
            c = UserFactory()
            with pytest.raises(AuthenticationError):
                ChatService.list_messages(c.id, cid, None, 20)

            # 已读后清零
            ChatService.mark_read(b.id, {'conversation_id': cid})
            assert ChatService.get_unread_count(b.id)['unread_count'] == 0

            page = ChatService.list_messages(b.id, cid, None, 10)
            assert page['items'][0]['content'] == '你好'

    def test_conversation_is_idempotent(self, app, db_session, mock_redis):
        """A→B 与 B→A 命中同一会话（low/high 规范化）"""
        with app.app_context():
            a = UserFactory()
            b = UserFactory()
            c1 = ChatService.create_conversation(a.id, {'peer_id': b.id})
            c2 = ChatService.create_conversation(b.id, {'peer_id': a.id})
            assert c1['conversation_id'] == c2['conversation_id']

    def test_cannot_chat_with_self(self, app, db_session, mock_redis):
        with app.app_context():
            a = UserFactory()
            with pytest.raises(ValidationError):
                ChatService.create_conversation(a.id, {'peer_id': a.id})

    def test_list_conversations_has_peer_info(self, app, db_session, mock_redis):
        """会话列表带对端用户名，按最近消息排序"""
        with app.app_context():
            a = UserFactory()
            b = UserFactory(username='peer_b')
            ChatService.create_conversation(a.id, {'peer_id': b.id})
            result = ChatService.list_conversations(a.id, page=1, per_page=10)
            assert result['pagination']['total'] == 1
            assert result['items'][0]['peer_id'] == b.id
            assert result['items'][0]['peer_username'] == 'peer_b'
