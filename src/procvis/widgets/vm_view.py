from dataclasses import dataclass
from math import log2
from typing import override

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import CenterMiddle
from textual.events import Resize
from textual.reactive import reactive
from textual.widgets import Static

from procvis.memory import MapsEntry


@dataclass
class RenderBlock:
    style: str
    size: int


class VMBlock(Static):
    maps: reactive[list[MapsEntry] | None] = reactive(None)
    is_vertical: reactive[bool] = reactive(False)
    render_text: Text = Text()

    BACKGROUND_CHAR: str = "█"
    UNMAPPED_COLOR: str = "#2A374f"
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

    def get_render_list(self, maps: list[MapsEntry]) -> list[RenderBlock]:
        render_list: list[RenderBlock] = []
        prev_end = maps[0].start
        for map in maps:
            color = self.get_color(map)
            size = map.end - map.start
            gap_before = int(log2(map.start - prev_end + 1))
            if gap_before != 0:
                render_list.append(RenderBlock(self.UNMAPPED_COLOR, gap_before))
            render_list.append(RenderBlock(color, size))
            prev_end = map.end

        return render_list

    def compress_render_list(self, render_list: list[RenderBlock], area: int):
        """Apply compression strategy to create render list that gives user the most value"""
        total_size = self.get_render_list_size(render_list)
        scale = area / total_size
        self.log(f"total_size: {total_size}")
        self.log(f"area: {area}")
        self.log(f"scale: {scale}")

        # Compress render list
        compressed_size = 0
        for blk in render_list:
            blk.size = max(1, int(blk.size * scale))
            compressed_size += blk.size

        # Make compressed list fit
        diff = compressed_size - area
        non_one_blk_size = sum(blk.size for blk in render_list if blk.size > 1)
        non_one_scale = (non_one_blk_size - diff) / non_one_blk_size
        self.log(f"compressed_size: {compressed_size}")
        self.log(f"diff: {diff}")
        self.log(f"non_one_blk_size: {non_one_blk_size}")
        self.log(f"non_one_scale: {non_one_scale}")

        # Scale down non one blocks
        new_size = 0
        for blk in render_list:
            if blk.size > 1:
                blk.size = int(blk.size * non_one_scale)
            new_size += blk.size

        # Redistribute leftover space to non one blocks
        diff = area - new_size
        index = 0
        while diff > 0:
            # Find first non one block
            while render_list[index].size == 1:
                index += 1
                if index == len(render_list):
                    index = 0
            render_list[index].size += 1
            diff -= 1
            index += 1
            if index == len(render_list):
                index = 0

    def get_render_list_size(self, render_list: list[RenderBlock]):
        total = 0
        for blk in render_list:
            total += blk.size
        return total

    def calc_render_text(self, maps: list[MapsEntry] | None) -> Text:
        if maps is None:
            return Text()

        area = self.size.width * self.size.height
        text = Text(self.BACKGROUND_CHAR * area, style=self.UNMAPPED_COLOR)
        render_list = self.get_render_list(maps)
        self.compress_render_list(render_list, area)

        if self.is_vertical:
            base = 0
            for blk in render_list:
                text.stylize(blk.style, base, min(base + blk.size, area))
                base += blk.size
        else:
            base = 0
            for blk in render_list:
                for i in range(blk.size):
                    c, r = divmod(base + i, self.size.height)
                    if c >= self.size.width:
                        break
                    index = r * self.size.width + c
                    text.stylize(blk.style, index, min(index + 1, area))
                base += blk.size
            self.log(f"End base: {base}")

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
