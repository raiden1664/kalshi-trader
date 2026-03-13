from textual.app import App
from src.screens.dashboard import DashboardScreen
from src.core.data_manager import DataManager
from src.core.watcher import BuyWatcher
from src.core.paper import PaperLedger
from src.core import settings as cfg


class KalshiApp(App):
    TITLE = "kalshi-trader"
    CSS = """
    #stats             { padding: 1 2; height: auto; }
    #menu              { padding: 0 2; height: auto; }
    #status            { height: 1; padding: 0 1; }
    #detail            { padding: 1 2; overflow-y: auto; height: 1fr; }
    #colorfilter       { height: 1; padding: 0 1; }
    SectionHeader      { height: 1; padding: 0 1; }
    SportPillBar       { height: 1; padding: 0 2; }
    DataTable          { height: 1fr; }
    BellWidget         { width: 8; padding: 0 1; }
    ModeBar            { height: 1; padding: 0 1; }
    #bell_row          { height: 1; layout: horizontal; }
    #bell_spacer       { width: 1fr; }
    NotificationPanel  { height: auto; max-height: 16; background: $surface-darken-1;
                         border-bottom: solid #333; overflow-y: auto;
                         padding: 0 1; display: none; }
    #watch_panel       { padding: 0 2; height: auto; }
    """

    def on_mount(self):
        s = cfg.load()
        self._paper_mode = s.get("paper_mode", False)

        self.paper_ledger = PaperLedger()
        self.data_manager = DataManager(app=self, refresh_interval=60)
        self.data_manager.start()
        self.buy_watcher = BuyWatcher(app=self)
        self.buy_watcher.start()
        # Pre-warm tennis cache immediately so markets screen loads fast
        self.data_manager.request_sport("tennis")
        self.push_screen(DashboardScreen())

    def on_unmount(self):
        self.data_manager.stop()
        self.buy_watcher.stop()

    # ── Paper mode ────────────────────────────────────────────────────────────

    @property
    def paper_mode(self) -> bool:
        return self._paper_mode

    def toggle_paper_mode(self):
        self._paper_mode = not self._paper_mode
        s = cfg.load()
        s["paper_mode"] = self._paper_mode
        cfg.save(s)

        # 1. Update bar color immediately
        from src.widgets.mode_bar import ModeBar
        try:
            self.screen.query_one(ModeBar).refresh_bar()
        except Exception:
            pass

        # 2. Immediately redraw content without any API call
        try:
            screen = self.screen
            if isinstance(screen, DashboardScreen):
                if self._paper_mode:
                    # Paper: reads local ledger synchronously, zero latency
                    screen._draw_paper()
                else:
                    # Live: use whatever data is already cached on the screen
                    # _positions and _cached_bal are set by last _draw() call
                    bal = getattr(screen, "_cached_bal", {})
                    pos = getattr(screen, "_positions", [])
                    screen._draw(bal, pos)
        except Exception:
            pass

    # ── Bell / notifications ──────────────────────────────────────────────────

    def _update_bell(self):
        from src.widgets.bell import BellWidget
        count = self.data_manager.notifications.unread_count
        try:
            self.screen.query_one(BellWidget).unread = count
        except Exception:
            pass

    def toggle_notifications(self):
        from src.widgets.notification_panel import NotificationPanel
        store = self.data_manager.notifications
        try:
            panel = self.screen.query_one(NotificationPanel)
        except Exception:
            return
        if panel.display:
            panel.hide()
        else:
            store.mark_all_read()
            self._update_bell()
            panel.show(store)

    def notify_watch_fired(self, watch: dict, msg: str):
        from src.core.notification_store import Alert
        self.data_manager.notifications.add(Alert(
            message=f"Buy triggered: {watch['label']} {watch['side'].upper()} @ {watch['trigger_price']}¢",
            severity="information",
            price=watch["trigger_price"] / 100,
            match=watch["label"],
        ))
        self._update_bell()
        import threading, time
        def _delayed_refresh():
            time.sleep(2)
            try:
                screen = self.screen
                if isinstance(screen, DashboardScreen):
                    self.call_from_thread(screen._load_stats)
            except Exception:
                pass
        threading.Thread(target=_delayed_refresh, daemon=True).start()


if __name__ == "__main__":
    KalshiApp().run()