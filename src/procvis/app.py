from curses import KEY_F10
from typing import override

from textual import events, work
from textual.app import App, ComposeResult
from textual.containers import CenterMiddle
from textual.reactive import reactive
from textual.timer import Timer
from textual.widgets import ContentSwitcher, Footer, Header
from textual.worker import Worker, get_current_worker

from procvis.memory import (
    MemoryReader,
    Stat,
)
from procvis.widgets import ProcessSelector, ProcessView


class ProcessVisualiserApp(App):
    CSS_PATH = "app.tcss"
    TITLE = "Process Visualiser"
    stats: reactive[dict[int, Stat]] = reactive({})
    timer: Timer | None = None

    def on_mount(self) -> None:
        """Start worker to fetch pids"""
        self.update_stats()
        self.timer = self.set_interval(5, self.update_stats)

    @work(exclusive=True, thread=True)
    def update_stats(self) -> None:
        worker = get_current_worker()
        pids = MemoryReader.get_pids()

        stats: dict[int, Stat] = {}
        for pid in pids:
            stat = MemoryReader.read_stat(pid)
            if stat:
                stats[pid] = stat
            else:
                self.log(f"Error: failed to read stat for process: {pid}")

        if not worker.is_cancelled:
            self.call_from_thread(self.set_stats, stats)

    def set_stats(self, stats: dict[int, Stat]) -> None:
        self.stats = stats
        selector = self.query_one(ProcessSelector)
        selector.stats = list(stats.values())

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        self.log(event)

    def watch_stats(self, stats: dict[int, Stat]) -> None:
        selector = self.query_one(ProcessSelector)
        selector.stats = list(stats.values())

    @override
    def compose(self) -> ComposeResult:
        yield Header()
        with ContentSwitcher(initial="process-selector"):
            with CenterMiddle(id="process-selector"):
                yield ProcessSelector()
            yield ProcessView(id="process-view")
        yield Footer()

    def on_process_selector_selected(self, event: ProcessSelector.Selected):
        if event.pid is not None and event.pid in self.stats:
            if self.timer:
                self.timer.pause()
            process_view = self.query_one(ProcessView)
            process_view.stat = self.stats[event.pid]
            process_view.focus()
            self.query_one(ContentSwitcher).current = "process-view"
            self.log(f"{event.pid} selected")
        else:
            self.log(f"Failed to enter process view for {event.pid}, no data")

    def on_process_view_go_back(self, event: ProcessView.GoBack):
        content_switcher = self.query_one(ContentSwitcher)
        content_switcher.current = "process-selector"
        if self.timer:
            self.timer.resume()
        self.query_one(ProcessSelector).focus()


if __name__ == "__main__":
    app = ProcessVisualiserApp()
    app.run()
