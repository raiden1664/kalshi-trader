"""
NotificationStore — holds alert history, tracks unread count.
Owned by DataManager, read by the bell widget and notification panel.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable


@dataclass
class Alert:
    message:   str
    severity:  str          # "warning" | "information"
    price:     float        # yes_ask at time of alert (0-1)
    match:     str          # "P1 vs P2"
    timestamp: datetime = field(default_factory=datetime.now)
    read:      bool = False

    @property
    def icon(self) -> str:
        return "⚠" if self.severity == "warning" else "ℹ"

    @property
    def color(self) -> str:
        return "#ffd700" if self.severity == "warning" else "#00bcd4"

    @property
    def time_str(self) -> str:
        return self.timestamp.strftime("%H:%M:%S")


class NotificationStore:
    def __init__(self):
        self._alerts:      list[Alert]    = []
        self._listeners:   list[Callable] = []  # called on new alert

    def add(self, alert: Alert):
        self._alerts.insert(0, alert)  # newest first
        for fn in self._listeners:
            try:
                fn(alert)
            except Exception:
                pass

    def mark_all_read(self):
        for a in self._alerts:
            a.read = True

    @property
    def unread_count(self) -> int:
        return sum(1 for a in self._alerts if not a.read)

    @property
    def alerts(self) -> list[Alert]:
        return self._alerts

    def on_new_alert(self, fn: Callable):
        self._listeners.append(fn)

    def remove_listener(self, fn: Callable):
        if fn in self._listeners:
            self._listeners.remove(fn)