"""Byte-budgeted LRU cache for rendered page images."""
from collections import OrderedDict


class PageCache:
    def __init__(self, max_bytes=256 * 1024 * 1024):
        self.max_bytes = max_bytes
        self._items = OrderedDict()
        self._bytes = 0

    def get(self, key):
        img = self._items.get(key)
        if img is not None:
            self._items.move_to_end(key)
        return img

    def put(self, key, image):
        old = self._items.pop(key, None)
        if old is not None:
            self._bytes -= old.sizeInBytes()
        self._items[key] = image
        self._bytes += image.sizeInBytes()
        while self._bytes > self.max_bytes and len(self._items) > 1:
            _, ev = self._items.popitem(last=False)
            self._bytes -= ev.sizeInBytes()

    def put_trim(self):
        while self._bytes > self.max_bytes and self._items:
            _, ev = self._items.popitem(last=False)
            self._bytes -= ev.sizeInBytes()

    def drop_path(self, path):
        for k in [k for k in self._items if k[0] == path]:
            self._bytes -= self._items.pop(k).sizeInBytes()

    def clear(self):
        self._items.clear()
        self._bytes = 0

    @property
    def size_bytes(self):
        return self._bytes
