from typing import override

from rich.text import Text
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import DataTable

from procvis.memory import MemoryReader, Stat


class ProcessSelector(DataTable):
    stats: reactive[list[Stat]] = reactive([])
    COLOR_1 = "white"
    COLOR_2 = "green"

    BINDINGS = [
        ("p", "sort_by_pid", "Sort By Pid"),
        ("r", "sort_by_program", "Sort By Program"),
        ("c", "sort_by_command", "Sort By Command"),
        ("t", "sort_by_threads", "Sort By Threads"),
        ("u", "sort_by_user", "Sort By User"),
        ("m", "sort_by_mem", "Sort By Memory"),
    ]

    current_sort = "mem"

    def action_sort_by_pid(self) -> None:
        self.sort("pid", key=lambda pid: int(pid.plain))
        self.current_sort = "pid"

    def action_sort_by_program(self) -> None:
        self.sort("program", key=lambda prog: prog.plain)
        self.current_sort = "program"

    def action_sort_by_command(self) -> None:
        self.sort("command", key=lambda comm: comm.plain)
        self.current_sort = "command"

    def action_sort_by_threads(self) -> None:
        self.sort("threads", key=lambda threads: int(threads.plain), reverse=True)
        self.current_sort = "threads"

    def action_sort_by_user(self) -> None:
        self.sort("user", key=lambda user: user.plain)
        self.current_sort = "user"

    def action_sort_by_mem(self) -> None:
        self.sort(
            "mem", key=lambda mem: MemoryReader.unformat_bytes(mem.plain), reverse=True
        )
        self.current_sort = "mem"

    @override
    def on_mount(self) -> None:
        """Add border title and columns"""
        self.border_title: str = "Select a process:"
        _ = self.add_columns(
            ("Pid:", "pid"),
            ("Program:", "program"),
            ("Command:", "command"),
            ("Threads:", "threads"),
            ("User:", "user"),
            ("Mem:", "mem"),
        )
        self.cursor_type = "row"

    def get_styled_row(self, stat: Stat) -> list[Text]:
        return [
            Text(str(stat.pid), style=self.COLOR_1, justify="right"),
            Text(stat.comm[:16], style=self.COLOR_2),
            Text(stat.cmdline[:32], style=self.COLOR_1),
            Text(str(stat.num_threads), style=self.COLOR_2, justify="right"),
            Text(stat.user[:10], style=self.COLOR_1),
            Text(
                MemoryReader.get_mem(stat.rss),
                style=self.COLOR_2,
                justify="right",
            ),
        ]

    def watch_stats(self, stats: list[Stat]) -> None:
        """Update rows when process stats update"""
        self.clear()
        for stat in stats:
            _ = self.add_row(*self.get_styled_row(stat), key=str(stat.pid))

        # Sort into previous order
        if self.current_sort == "pid":
            self.action_sort_by_pid()
        elif self.current_sort == "program":
            self.action_sort_by_program()
        elif self.current_sort == "command":
            self.action_sort_by_command()
        elif self.current_sort == "threads":
            self.action_sort_by_threads()
        elif self.current_sort == "user":
            self.action_sort_by_user()
        elif self.current_sort == "mem":
            self.action_sort_by_mem()

    class Selected(Message):
        def __init__(self, pid: int | None) -> None:
            self.pid: int | None = pid
            super().__init__()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        pid = event.row_key.value
        if pid is not None:
            pid = int(pid)
        res = self.post_message(self.Selected(pid))
        if not res:
            self.log("Warning: failed to post ProcessSelector.Selected message")
