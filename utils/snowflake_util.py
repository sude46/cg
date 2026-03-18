# utils/snowflake_util.py
# 完全移除 Flask current_app 依赖，不依赖应用上下文
import time
import threading
import os  # 新增：用环境变量读取配置，而非 Flask 配置

class Snowflake:
    """雪花算法生成唯一ID（无 Flask 上下文依赖）"""
    twepoch = 1288834974657
    data_center_id_bits = 5
    worker_id_bits = 5
    sequence_bits = 12

    max_data_center_id = (1 << data_center_id_bits) - 1
    max_worker_id = (1 << worker_id_bits) - 1
    max_sequence = (1 << sequence_bits) - 1

    worker_id_shift = sequence_bits
    data_center_id_shift = sequence_bits + worker_id_bits
    timestamp_left_shift = sequence_bits + worker_id_bits + data_center_id_bits

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    # 初始化参数（从环境变量读取，无上下文依赖）
                    cls._instance.worker_id = cls._get_config("SNOWFLAKE_WORKER_ID", 0)
                    cls._instance.data_center_id = cls._get_config("SNOWFLAKE_DATA_CENTER_ID", 0)
                    cls._instance.sequence = 0
                    cls._instance.last_timestamp = -1
        return cls._instance

    @classmethod
    def _get_config(cls, key, default):
        """从环境变量读取配置，完全避开 Flask current_app"""
        try:
            # 从 .env 或系统环境变量读取
            value = os.getenv(key, default)
            return int(value)
        except (TypeError, ValueError):
            return int(default)

    def _gen_timestamp(self):
        return int(time.time() * 1000)

    def get_id(self):
        """生成唯一ID"""
        with self._lock:
            timestamp = self._gen_timestamp()

            if timestamp < self.last_timestamp:
                raise ValueError(f"Clock moved backwards. Refusing to generate id for {self.last_timestamp - timestamp} milliseconds")

            if timestamp == self.last_timestamp:
                self.sequence = (self.sequence + 1) & self.max_sequence
                if self.sequence == 0:
                    timestamp = self._til_next_millis(self.last_timestamp)
            else:
                self.sequence = 0

            self.last_timestamp = timestamp

            id = ((timestamp - self.twepoch) << self.timestamp_left_shift) | \
                 (self.data_center_id << self.data_center_id_shift) | \
                 (self.worker_id << self.worker_id_shift) | \
                 self.sequence
            return id

    def _til_next_millis(self, last_timestamp):
        timestamp = self._gen_timestamp()
        while timestamp <= last_timestamp:
            timestamp = self._gen_timestamp()
        return timestamp


