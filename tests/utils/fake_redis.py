"""tests/utils/fake_redis.py
================
Redis 内存模拟，支持 String/Set/ZSet/Hash/List/分布式锁/Pipeline。
与 pytest 无关的纯工具类，单独维护。
"""

import fnmatch
import time

from redis.exceptions import NoScriptError


class FakeRedisClient:
    def __init__(self):
        self.store = {}
        self.expiry = {}

    # --- 内部 ---
    def _evict(self, key):
        if key in self.expiry and time.time() > self.expiry[key]:
            self.store.pop(key, None)
            self.expiry.pop(key, None)

    def _is_expired(self, key):
        if key not in self.expiry:
            return False
        return time.time() > self.expiry[key]

    # --- String ---
    @staticmethod
    def _enc(value):
        """模拟 redis-py：标量值最终以字符串/字节存储。"""
        if isinstance(value, (str, bytes)):
            return value
        return str(value)

    def get(self, key):
        self._evict(key)
        return self.store.get(key)

    def set(self, key, value, ex=None, px=None, nx=False, xx=False):
        if nx and key in self.store and not self._is_expired(key):
            return False
        if xx and key not in self.store:
            return False
        self.store[key] = self._enc(value)
        if ex:
            self.expiry[key] = time.time() + ex
        elif px:
            self.expiry[key] = time.time() + px / 1000.0
        return True

    def setex(self, key, expire, value):
        self.store[key] = self._enc(value)
        if expire:
            self.expiry[key] = time.time() + expire
        return True

    def getset(self, key, value):
        old = self.get(key)
        self.store[key] = value
        return old

    def delete(self, *keys):
        count = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                self.expiry.pop(key, None)
                count += 1
        return count

    def exists(self, key):
        self._evict(key)
        return 1 if key in self.store else 0

    def expire(self, key, ttl):
        if key in self.store:
            self.expiry[key] = time.time() + ttl
            return True
        return False

    def ttl(self, key):
        if key not in self.store:
            return -2
        if key not in self.expiry:
            return -1
        remaining = self.expiry[key] - time.time()
        return int(remaining) if remaining > 0 else -2

    def incrby(self, key, amount=1):
        val = int(self.store.get(key, 0)) + amount
        self.store[key] = str(val)
        return val

    incr = incrby
    def decr(self, key, amount=1):
        return self.incrby(key, -amount)

    def keys(self, pattern="*"):
        return [k for k in self.store.keys() if fnmatch.fnmatch(k, pattern)]

    def flushall(self):
        self.store.clear()
        self.expiry.clear()
        return True

    # --- Set ---
    def smembers(self, key):
        return self.store.get(key, set())

    def sadd(self, key, *members):
        if key not in self.store:
            self.store[key] = set()
        self.store[key].update(members)
        return len(members)

    def srem(self, key, *members):
        s = self.store.get(key, set())
        count = 0
        for m in members:
            if m in s:
                s.remove(m)
                count += 1
        return count

    def sismember(self, key, member):
        return member in self.store.get(key, set())

    def scard(self, key):
        return len(self.store.get(key, set()))

    # --- ZSet ---
    def zrevrange(self, key, start, end, withscores=False):
        items = self.store.get(key, {})
        sorted_items = sorted(items.items(), key=lambda x: x[1], reverse=True)
        slice_items = sorted_items[start:end + 1] if end != -1 else sorted_items[start:]
        return slice_items if withscores else [i[0] for i in slice_items]

    def zrange(self, key, start, end, withscores=False):
        items = self.store.get(key, {})
        sorted_items = sorted(items.items(), key=lambda x: x[1])
        slice_items = sorted_items[start:end + 1] if end != -1 else sorted_items[start:]
        return slice_items if withscores else [i[0] for i in slice_items]

    def zrevrangebyscore(self, key, max_score, min_score, start=0, num=None, withscores=False):
        items = self.store.get(key, {})

        def parse_bound(v):
            exclusive = isinstance(v, str) and v.startswith('(')
            s = v[1:] if exclusive else v
            if s in ('+inf', 'inf'):
                val = float('inf')
            elif s == '-inf':
                val = float('-inf')
            else:
                val = float(s)
            return val, exclusive

        mx, mx_exclusive = parse_bound(max_score)
        mn, _ = parse_bound(min_score)
        ordered = sorted(items.items(), key=lambda x: x[1], reverse=True)
        out = []
        for member, score in ordered:
            if score > mx or score < mn:
                continue
            if mx_exclusive and score == mx:
                continue
            out.append((member, score))
        if num is not None:
            out = out[start:start + num]
        elif start:
            out = out[start:]
        return out if withscores else [m for m, _ in out]

    def zadd(self, key, mapping, **kwargs):
        if key not in self.store:
            self.store[key] = {}
        self.store[key].update(mapping)
        return len(mapping)

    def zrem(self, key, *members):
        items = self.store.get(key, {})
        count = 0
        for m in members:
            if m in items:
                del items[m]
                count += 1
        return count

    def zcard(self, key):
        return len(self.store.get(key, {}))

    def zscore(self, key, member):
        return self.store.get(key, {}).get(member)

    def zincrby(self, key, amount, member):
        items = self.store.setdefault(key, {})
        items[member] = float(items.get(member, 0)) + amount
        return items[member]

    def zremrangebyrank(self, key, start, end):
        """按排名删除（升序，支持负索引 end=-N 表示倒数第 N 个之前）。"""
        items = self.store.get(key, {})
        if not items:
            return 0
        ordered = [m for m, _ in sorted(items.items(), key=lambda x: x[1])]
        total = len(ordered)
        start = 0 if start is None else (total + start if start < 0 else start)
        end = total - 1 if end is None else (total + end if end < 0 else end)
        removed = 0
        for member in ordered[start:end + 1]:
            items.pop(member, None)
            removed += 1
        return removed

    # --- Hash ---
    def hget(self, key, field):
        return self.store.get(key, {}).get(field)

    def hset(self, key, field, value):
        if key not in self.store:
            self.store[key] = {}
        self.store[key][field] = value
        return 1

    def hmset(self, key, mapping):
        if key not in self.store:
            self.store[key] = {}
        self.store[key].update(mapping)
        return True

    def hgetall(self, key):
        return self.store.get(key, {})

    def hincrby(self, key, field, amount=1):
        if key not in self.store:
            self.store[key] = {}
        val = int(self.store[key].get(field, 0)) + amount
        self.store[key][field] = str(val)
        return val

    def hdel(self, key, *fields):
        d = self.store.get(key, {})
        count = 0
        for f in fields:
            if f in d:
                del d[f]
                count += 1
        return count

    def hexists(self, key, field):
        return field in self.store.get(key, {})

    # --- List (EventBus) ---
    def lpush(self, key, *values):
        if key not in self.store:
            self.store[key] = []
        self.store[key] = list(values) + self.store[key]
        return len(self.store[key])

    def rpush(self, key, *values):
        if key not in self.store:
            self.store[key] = []
        self.store[key].extend(values)
        return len(self.store[key])

    def lpop(self, key):
        lst = self.store.get(key, [])
        return lst.pop(0) if lst else None

    def rpop(self, key):
        lst = self.store.get(key, [])
        return lst.pop() if lst else None

    def brpop(self, keys, timeout=0):
        if isinstance(keys, str):
            keys = [keys]
        for key in keys:
            val = self.rpop(key)
            if val is not None:
                return (key, val)
        return None

    def llen(self, key):
        return len(self.store.get(key, []))

    # --- Scan ---
    def scan_iter(self, match=None, count=None):
        if match is None:
            return iter(list(self.store.keys()))
        return iter(fnmatch.filter(self.store.keys(), match))

    # --- 分布式锁 ---
    def setnx(self, key, value):
        if key not in self.store or self._is_expired(key):
            self.store[key] = value
            return True
        return False

    def release_lock(self, key, value):
        if self.store.get(key) == value:
            self.delete(key)
            return True
        return False

    # --- Lua Script ---
    def script_load(self, script):
        import hashlib
        sha = hashlib.sha1(script.encode()).hexdigest()
        if '__scripts__' not in self.store:
            self.store['__scripts__'] = {}
        self.store['__scripts__'][sha] = script
        return sha

    def _run_lua(self, script, numkeys, keys_and_args):
        """按关键字模拟项目用到的几个 Lua（点赞 INCR/DECR、评论 DECR）。"""
        keys = list(keys_and_args[:numkeys])
        args = list(keys_and_args[numkeys:])
        s = script.lower().replace(' ', '').replace('\n', '')
        # LIKE INCR: sismember -> 不存在则 sadd + incr
        if 'sadd' in s and 'sismember' in s:
            member = args[0]
            if self.sismember(keys[0], member):
                return 0
            self.sadd(keys[0], member)
            self.incrby(keys[1], 1)
            return 1
        # LIKE DECR: sismember -> 存在则 srem + decr
        if 'srem' in s and 'sismember' in s:
            member = args[0]
            if not self.sismember(keys[0], member):
                return 0
            self.srem(keys[0], member)
            self.incrby(keys[1], -1)
            return 1
        # 计数 DECR（评论 DECR_LUA / 通知未读 DECR）：get -> <=0 返回 0，否则 -1
        if 'decr' in s:
            current = self.get(keys[0])
            if current is None or int(current) <= 0:
                return 0
            return self.incrby(keys[0], -1)
        return 1

    def evalsha(self, sha, numkeys, *keys_and_args):
        scripts = self.store.get('__scripts__', {})
        if sha not in scripts:
            raise NoScriptError(f"Script not found: {sha}")
        return self._run_lua(scripts[sha], numkeys, keys_and_args)

    def eval(self, script, numkeys, *keys_and_args):
        return self._run_lua(script, numkeys, keys_and_args)

    # --- Pipeline ---
    def pipeline(self, transaction=True):
        return FakePipeline(self)

    def execute(self):
        return []


class FakePipeline:
    def __init__(self, client):
        self.client = client
        self.commands = []

    def __getattr__(self, name):
        def method(*args, **kwargs):
            self.commands.append((name, args, kwargs))
            return self
        return method

    def execute(self):
        results = []
        for name, args, kwargs in self.commands:
            method = getattr(self.client, name)
            results.append(method(*args, **kwargs))
        return results
