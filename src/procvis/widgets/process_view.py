from typing import override

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Container, Grid, Horizontal, Vertical
from textual.events import Resize
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Static, TabbedContent, TabPane
from textual.worker import get_current_worker

from procvis.memory import MemoryReader, ProcessData, Stat

from .vm_view import VMBlock, VMView


class InfoBlock(Vertical):
    info: reactive[str] = reactive("")

    def __init__(self, header: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.header: str = header

    @override
    def compose(self) -> ComposeResult:
        yield Static(Text(self.header, style="bold"))
        yield Static(id="info")

    def on_mount(self) -> None:
        self.update_info(self.info)

    def watch_info(self, info: str) -> None:
        self.update_info(info)

    def update_info(self, info: str) -> None:
        self.query_one("#info", Static).update(Text(info, style="white"))


class ProcessInfo(Container):
    stat: reactive[Stat | None] = reactive(None)

    def on_mount(self) -> None:
        self.border_title = "Process Info"

    @override
    def compose(self) -> ComposeResult:
        with Horizontal():
            yield InfoBlock("Pid:", id="pid")
            yield InfoBlock("Program:", id="program")
        yield InfoBlock("Command: ", id="command")
        yield InfoBlock("Threads: ", id="threads")
        yield InfoBlock("User: ", id="user")

    def watch_stat(self, stat: Stat | None) -> None:
        if stat is None:
            return
        self.query_one("#pid", InfoBlock).info = str(stat.pid)
        self.query_one("#program", InfoBlock).info = stat.comm[:16]
        self.query_one("#command", InfoBlock).info = stat.cmdline[:32]
        self.query_one("#threads", InfoBlock).info = str(stat.num_threads)
        self.query_one("#user", InfoBlock).info = stat.user


class Legend(Container):
    def on_mount(self) -> None:
        self.border_title = "Legend"

    LEGENDS: list[Text] = [
        Text("■ ", style=VMBlock.CODE_COLOR) + Text("CODE", style="white"),
        Text("■ ", style=VMBlock.RO_DATA_COLOR) + Text("RO Data", style="white"),
        Text("■ ", style=VMBlock.WR_DATA_COLOR) + Text("WR Data", style="white"),
        Text("■ ", style=VMBlock.HEAP_COLOR) + Text("Heap", style="white"),
        Text("■ ", style=VMBlock.STACK_COLOR) + Text("Stack", style="white"),
        Text("■ ", style=VMBlock.SHARED_LIBRARY_COLOR)
        + Text("Shared library", style="white"),
        Text("■ ", style=VMBlock.ANONYMOUS_COLOR) + Text("Anonymous", style="white"),
        Text("■ ", style=VMBlock.GUARD_COLOR) + Text("Guard", style="white"),
        Text("■ ", style=VMBlock.VDSO_COLOR) + Text("VDSO", style="white"),
        Text("■ ", style=VMBlock.UNMAPPED_COLOR) + Text("Unmapped", style="white"),
    ]

    @override
    def compose(self) -> ComposeResult:
        for text in self.LEGENDS:
            yield Static(text)


class ProcessView(Grid):
    can_focus = True
    stat: reactive[Stat | None] = reactive(None)

    BINDINGS = [("escape", "go_back", "Go back to process selector")]

    class GoBack(Message):
        def __init__(self) -> None:
            super().__init__()

    def action_go_back(self) -> None:
        self.stat = None
        res = self.post_message(self.GoBack())
        if not res:
            self.log("Warning: failed to post ProcessView.GoBack message")

    def watch_stat(self, stat: Stat | None) -> None:
        if stat is not None:
            # Start worker to retrive maps and pagemap data
            self.query_one("#process-info", ProcessInfo).stat = stat
            self.get_process_data(stat.pid)
        else:
            self.query_one(ProcessInfo).stat = None
            self.query_one(VMBlock).maps = None

    @work(exclusive=True, thread=True)
    def get_process_data(self, pid: int) -> None:
        worker = get_current_worker()
        process_data = MemoryReader.get_process_data(pid)

        if not worker.is_cancelled:
            self.app.call_from_thread(self.set_process_data, process_data)

    def set_process_data(self, process_data: ProcessData):
        vm_block = self.query_one(VMBlock)
        vm_block.maps = process_data.maps_entries

    @override
    def compose(self) -> ComposeResult:
        with TabbedContent(id="vm-tabbed-pane", initial="vm"):
            with TabPane("VM", id="vm"):
                yield VMView(id="vm-view")
        with Container(id="process-container"):
            yield ProcessInfo(id="process-info")
            yield Legend(id="legend")

    def on_resize(self, event: Resize) -> None:
        """When resize occur, calculate optimum layout and switch to it"""
        v_ram_pane_width = int(self.size.width * 0.65)
        v_vm_view_width = int(v_ram_pane_width * 0.8)
        v_vm_view_width = min(VMView.MAX_V_WIDTH, v_vm_view_width)
        v_vm_view_height = int(self.size.height * 0.9)
        v_area = v_vm_view_height * v_vm_view_width

        h_ram_pane_height = int(self.size.height * 0.65)
        h_vm_view_height = int(h_ram_pane_height * 0.8)
        v_vm_view_height = min(VMView.MAX_H_HEIGHT, v_vm_view_height)
        h_vm_view_width = int(self.size.width * 0.9)
        h_area = h_vm_view_height * h_vm_view_width

        vm_view = self.query_one(VMView)
        process_container = self.query_one("#process-container")

        if v_area >= h_area:
            self.add_class("vertical")
            process_container.add_class("vertical")
            vm_view.is_vertical = True
        else:
            self.remove_class("vertical")
            process_container.remove_class("vertical")
            vm_view.is_vertical = False
