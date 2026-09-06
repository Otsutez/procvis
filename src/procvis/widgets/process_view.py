from dataclasses import dataclass
from math import log2
from typing import override

from rich.text import Text
from textual import Logger, work
from textual.app import ComposeResult, RenderResult
from textual.containers import CenterMiddle, Grid
from textual.events import Resize
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static, TabbedContent, TabPane
from textual.worker import get_current_worker

from procvis.memory import MapsEntry, MemoryReader, PageMapEntry, ProcessData, Stat

"""
Process View Design

Vertical Layout                                                          
┌─────────┌────────┐──────────────┐┌───────────────┐
│ VM      │ Phys   │              ││ Process Info  │
└─────────└────────┘              ││               │
│       ┌──────────────────┐      ││               │
│       │                  │      ││               │
│       │   VM View        │      ││               │
│       │                  │      ││               │
│       │                  │      ││               │
│       │                  │      ││               │
│       │                  │      ││               │
│       │                  │      ││               │
│       │                  │      ││               │
│       │                  │      ││               │
│       │                  │      ││               │
│       │                  │      ││               │
│       │                  │      ││               │
│       └──────────────────┘      ││               │
│                                 ││               │
└─────────────────────────────────┘└───────────────┘
"""


@dataclass
class RenderBlock:
    style: str
    size: int


class VMBlock(Static):
    maps: reactive[list[MapsEntry] | None] = reactive(None)
    is_vertical: reactive[bool] = reactive(False)
    render_text: Text = Text()

    BACKGROUND_CHAR: str = "░"
    UNMAPPED_COLOR: str = "#778899"
    CODE_COLOR: str = "#4C78A8"
    RO_DATA_COLOR: str = "#59A14F"
    WR_DATA_COLOR: str = "#E0A52B"
    HEAP_COLOR: str = "#F28E2B"
    STACK_COLOR: str = "#9C6ADE"
    SHARED_LIBRARY_COLOR: str = "#E15759"
    ANONYMOUS_COLOR: str = "#7F8C8D"
    GUARD_COLOR: str = "#34495E"
    VDSO_COLOR: str = "#B279A2"

    def get_maps_min_max(self, maps: list[MapsEntry]) -> tuple[int, int]:
        min_addr = maps[0].start
        max_addr = maps[0].end

        for map in maps:
            min_addr = min(min_addr, map.start)
            max_addr = max(max_addr, map.end)

        return min_addr, max_addr

    def get_color(self, map: MapsEntry) -> str:
        color = self.UNMAPPED_COLOR
        if "[heap]" in map.pathname:
            color = self.HEAP_COLOR
        elif "[stack" in map.pathname:
            color = self.STACK_COLOR
        elif "vdso" in map.pathname:
            color = self.VDSO_COLOR
        elif "lib" in map.pathname:
            color = self.SHARED_LIBRARY_COLOR
        elif "x" in map.perms and map.pathname:
            color = self.CODE_COLOR
        elif "w" in map.perms and map.pathname:
            color = self.WR_DATA_COLOR
        elif map.pathname:
            color = self.RO_DATA_COLOR
        elif "r" in map.perms:
            color = self.ANONYMOUS_COLOR
        else:
            color = self.GUARD_COLOR

        return color

    def get_compressed_render_list(self, maps: list[MapsEntry]) -> list[RenderBlock]:
        compressed_list: list[RenderBlock] = []
        prev_end = maps[0].start
        for map in maps:
            color = self.get_color(map)
            size = (map.end - map.start) // 32
            gap_before = int(log2(map.start - prev_end + 1)) * 8
            if gap_before != 0:
                compressed_list.append(RenderBlock(self.UNMAPPED_COLOR, gap_before))
            compressed_list.append(RenderBlock(color, size))
            prev_end = map.end
        return compressed_list

    def get_render_list_total_size(self, render_list: list[RenderBlock]):
        total = 0
        for blk in render_list:
            total += blk.size
        return total

    def calc_render_text(self, maps: list[MapsEntry] | None) -> Text:
        if maps is None:
            return Text()

        area = self.size.width * self.size.height
        text = Text(self.BACKGROUND_CHAR * area, style=self.UNMAPPED_COLOR)
        render_list = self.get_compressed_render_list(maps)
        total_size = self.get_render_list_total_size(render_list)
        scale = area / total_size

        self.log(render_list)
        self.log(f"total_size: {total_size}")
        self.log(f"area: {area}")
        self.log(f"scale: {scale}")

        if self.is_vertical:
            base = 0
            for blk in render_list:
                size = int(blk.size * scale)
                text.stylize(blk.style, base, min(base + size, area))
                base += size
        else:
            base = 0
            for blk in render_list:
                size = int(blk.size * scale)
                for i in range(size):
                    c, r = divmod(base + i, self.size.height)
                    index = r * self.size.width + c
                    text.stylize(blk.style, index, min(index + 1, area))
                base += size

        return text

    def watch_maps(self, maps: list[MapsEntry]) -> None:
        self.render_text = self.calc_render_text(maps)
        self.update(self.render_text)

    def on_mount(self) -> None:
        self.render_text = self.calc_render_text(self.maps)
        self.update(self.render_text)

    def on_resize(self, event: Resize) -> None:
        self.render_text = self.calc_render_text(self.maps)
        self.update(self.render_text)


class VMView(CenterMiddle):
    MAX_V_WIDTH: int = 40
    MAX_H_HEIGHT: int = 16
    is_vertical: bool = False

    @override
    def compose(self) -> ComposeResult:
        yield VMBlock()

    def calc_ver_blk_size(self, width: int, height: int) -> tuple[int, int]:
        blk_width = min(self.MAX_V_WIDTH, int(width * 0.8))
        blk_height = int(height * 0.9)
        return blk_width, blk_height

    def calc_hor_blk_size(self, width: int, height: int) -> tuple[int, int]:
        blk_width = int(width * 0.9)
        blk_height = min(self.MAX_H_HEIGHT, int(height * 0.8))
        return blk_width, blk_height

    def on_resize(self, event: Resize) -> None:
        # Recalculate vm block size
        blk_width, blk_height = (
            self.calc_ver_blk_size(event.size.width, event.size.height)
            if self.is_vertical
            else self.calc_hor_blk_size(event.size.width, event.size.height)
        )
        block = self.query_one(VMBlock)
        block.is_vertical = self.is_vertical
        block.styles.width = blk_width
        block.styles.height = blk_height


class ProcessInfo(Widget):
    pass


class ProcessView(Grid):
    stat: reactive[Stat | None] = reactive(None)

    def watch_stat(self, stat: Stat | None) -> None:
        if stat is not None:
            # Start worker to retrive maps and pagemap data
            self.get_process_data(stat.pid)

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
        yield ProcessInfo(id="process-info")

    def on_resize(self, event: Resize) -> None:
        """When resize occur, calculate optimum layout and switch to it"""
        v_ram_pane_width = int(self.size.width * 0.65)
        v_vm_view_width = int(v_ram_pane_width * 0.8)
        v_vm_view_width = min(VMView.MAX_V_WIDTH, v_vm_view_width)
        v_vm_view_height = int(self.size.height * 0.9)
        v_area = v_vm_view_height * v_vm_view_width

        self.log(f"width: {self.size.width}")
        self.log(f"height: {self.size.height}")
        self.log(f"v_vm_view_width: {v_vm_view_width}")
        self.log(f"v_vm_view_height: {v_vm_view_height}")
        self.log(f"v_area: {v_area}")

        h_ram_pane_height = int(self.size.height * 0.65)
        h_vm_view_height = int(h_ram_pane_height * 0.8)
        v_vm_view_height = min(VMView.MAX_H_HEIGHT, v_vm_view_height)
        h_vm_view_width = int(self.size.width * 0.9)
        h_area = h_vm_view_height * h_vm_view_width

        self.log(f"h_vm_view_width: {h_vm_view_width}")
        self.log(f"h_vm_view_height: {h_vm_view_height}")
        self.log(f"h_area: {h_area}")

        vm_view = self.query_one(VMView)

        if v_area >= h_area:
            if self.has_class("horizontal-grid"):
                self.remove_class("horizontal-grid")
            if not self.has_class("vertical-grid"):
                self.add_class("vertical-grid")
            vm_view.is_vertical = True
        else:
            if self.has_class("vertical-grid"):
                self.remove_class("vertical-grid")
            if not self.has_class("horizontal-grid"):
                self.add_class("horizontal-grid")
            vm_view.is_vertical = False
