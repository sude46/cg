"""
EventBus 实现 - 用于服务间解耦的发布/订阅模式
"""
from typing import Callable, Dict, List, Any
import logging

logger = logging.getLogger(__name__)


class EventBus:
    """简单的事件总线实现，支持同步事件发布/订阅"""
    
    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = {}
    
    def subscribe(self, event_type: str, handler: Callable[[Any], None]) -> None:
        """
        订阅特定类型的事件
        
        Args:
            event_type: 事件类型标识符，如 'comment.created'
            handler: 事件处理函数，接收 event_data 参数
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
        logger.debug(f"Handler subscribed to event '{event_type}'")
    
    def unsubscribe(self, event_type: str, handler: Callable[[Any], None]) -> None:
        """取消订阅事件"""
        if event_type in self._handlers and handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)
            logger.debug(f"Handler unsubscribed from event '{event_type}'")
    
    def publish(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        发布事件到所有订阅者
        
        Args:
            event_type: 事件类型标识符
            data: 事件数据字典
        """
        handlers = self._handlers.get(event_type, [])
        if not handlers:
            logger.debug(f"No handlers for event '{event_type}'")
            return
        
        for handler in handlers:
            try:
                handler(data)
            except Exception as e:
                logger.error(f"Event handler for '{event_type}' failed: {e}")
                # 事件处理失败不影响主流程


# 全局事件总线实例
event_bus = EventBus()
