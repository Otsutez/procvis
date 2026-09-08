from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import log2
from typing import override

from rich.text import Text
from textual import Logger
from textual.app import ComposeResult
from textual.containers import CenterMiddle
from textual.events import Resize
from textual.reactive import reactive
from textual.widgets import Static

from procvis.memory import MapsEntry


class VMType(Enum):
    UNMAPPED = 1
    CODE = 2
    RO_DATA = 3
    WR_DATA = 4
    HEAP = 5
    STACK = 6
    SHARED_LIB = 7
    ANONYMOUS = 8
    GUARD = 9
    VDSO = 10


@dataclass
class RenderBlock:
    type: VMType
    size: int
    map: MapsEntry | None = None
    next: RenderBlock | None = None


class RenderList:
    MAX_TRY: int = 5

    def __init__(self, log: Logger):
        self.head: RenderBlock | None = None
        self.log: Logger = log
        self.curr: RenderBlock | None = None

    def __iter__(self):
        curr = self.head
        while curr is not None:
            yield curr
            curr = curr.next

    def append(self, type: VMType, size: int, map: MapsEntry | None = None):
        new_blk = RenderBlock(type, size, map)
        if self.head is None:
            self.head = new_blk
            return

        curr = self.head
        while curr.next is not None:
            curr = curr.next

        curr.next = new_blk

    def get_size(self) -> int:
        count = 0
        curr = self.head
        while curr:
            count += 1
            curr = curr.next
        return count

    def get_total_size(self) -> int:
        return sum(blk.size for blk in self)

    def count_non_one(self) -> int:
        count = 0
        for blk in self:
            if blk.size > 1:
                count += 1
        return count

    def get_non_one_total(self) -> int:
        return sum(blk.size for blk in self if blk.size > 1)

    def scale_to_area(self, scale: float) -> int:
        """Attempt to scale all blocks to fit area, return total scaled size"""
        scaled_size = 0
        for blk in self:
            blk.size = max(1, int(blk.size * scale))
            scaled_size += blk.size
        return scaled_size

    def lossless_compress(self, non_one_scale: float, area: int):
        # Scale down non one blocks
        new_size = 0
        for blk in self:
            if blk.size > 1:
                blk.size = int(blk.size * non_one_scale)
            new_size += blk.size

        self.log(f"new_size: {new_size}")

        # Redistribute leftover space to non one blocks
        diff = area - new_size
        curr = self.head
        while diff > 0:
            if not curr:
                break

            if curr.size > 1:
                curr.size += 1
                diff -= 1

            curr = curr.next
            if curr is None:
                curr = self.head

    def remove_one_unmapped(self):
        """Remove all unmapped blocks of size one"""
        if self.head and self.head.type == VMType.UNMAPPED and self.head.size == 1:
            self.head = self.head.next

        if self.head is None:
            return

        prev = self.head
        curr = prev.next
        while curr:
            if curr.type == VMType.UNMAPPED and curr.size == 1:
                prev.next = curr.next
                curr = prev.next
            else:
                prev = curr
                curr = curr.next

    def coalesce_contiguous(self):
        """Coalesce contiguous blocks of the same type"""
        if self.head is None:
            return

        prev = self.head
        curr = prev.next
        while curr:
            if curr.type == prev.type and (
                curr.type in [VMType.UNMAPPED, VMType.ANONYMOUS, VMType.GUARD]
                or curr.map
                and prev.map
                and curr.map.pathname == prev.map.pathname
            ):
                prev.size += curr.size
                prev.next = curr.next
                curr = prev.next
            else:
                prev = curr
                curr = curr.next

    def calc_non_one_scale(self, scaled_size: int, area: int) -> float:
        diff = scaled_size - area
        non_one_total_size = self.get_non_one_total()
        self.log(f"non_one_total_size: {non_one_total_size}")
        non_one_scale = (non_one_total_size - diff) / non_one_total_size
        return non_one_scale

    def compress(self, area: int):
        """Apply different compression strategy to create render list that gives user the most value"""
        total_size = self.get_total_size()
        self.log(f"area: {area}")
        self.log(f"total_size: {total_size}")
        scale = area / total_size
        scaled_size = self.scale_to_area(scale)

        try_count = 0
        non_one_scale = self.calc_non_one_scale(scaled_size, area)
        while non_one_scale < 0.5 and try_count < self.MAX_TRY:
            self.log(f"non_one_scale: {non_one_scale}")
            self.remove_one_unmapped()
            self.log(f"size before coalescing: {self.get_size()}")
            self.coalesce_contiguous()
            self.log(f"size after coalescing: {self.get_size()}")
            total_size = self.get_total_size()
            scale = area / total_size
            scaled_size = self.scale_to_area(scale)
            non_one_scale = self.calc_non_one_scale(scaled_size, area)
            try_count += 1
            self.log(f"scaled_size: {scaled_size}")

        self.lossless_compress(non_one_scale, area)


class VMBlock(Static):
    maps: reactive[list[MapsEntry] | None] = reactive(None)
    is_vertical: reactive[bool] = reactive(False)
    render_text: Text = Text()

    BACKGROUND_CHAR: str = "█"

    color_map: dict[VMType, str] = {
        VMType.UNMAPPED: "#2A374f",
        VMType.CODE: "#4C78A8",
        VMType.RO_DATA: "#59A14F",
        VMType.WR_DATA: "#E0A52B",
        VMType.HEAP: "#F28E2B",
        VMType.STACK: "#9C6ADE",
        VMType.SHARED_LIB: "#E15759",
        VMType.ANONYMOUS: "#7F8C8D",
        VMType.GUARD: "#34495E",
        VMType.VDSO: "#B279A2",
    }

    @staticmethod
    def get_type(map: MapsEntry) -> VMType:
        if "[heap]" in map.pathname:
            return VMType.HEAP
        elif "[stack" in map.pathname:
            return VMType.STACK
        elif "vdso" in map.pathname:
            return VMType.VDSO
        elif "lib" in map.pathname:
            return VMType.SHARED_LIB
        elif "x" in map.perms and map.pathname:
            return VMType.CODE
        elif "w" in map.perms and map.pathname:
            return VMType.WR_DATA
        elif map.pathname:
            return VMType.RO_DATA
        elif "r" in map.perms:
            return VMType.ANONYMOUS
        else:
            return VMType.GUARD

    def get_render_list(self, maps: list[MapsEntry]) -> RenderList | None:
        if not maps:
            return None

        render_list = RenderList(self.log)
        prev_end = maps[0].start
        for map in maps:
            type = self.get_type(map)
            size = map.end - map.start
            gap_before = int(log2(map.start - prev_end + 1))
            if gap_before != 0:
                render_list.append(VMType.UNMAPPED, gap_before)
            render_list.append(type, size, map)
            prev_end = map.end

        return render_list

    def calc_render_text(self, maps: list[MapsEntry] | None) -> Text:
        if maps is None:
            return Text()

        area = self.size.width * self.size.height
        text = Text(self.BACKGROUND_CHAR * area, style=self.color_map[VMType.UNMAPPED])

        render_list = self.get_render_list(maps)
        if render_list is None:
            return text
        render_list.compress(area)

        if self.is_vertical:
            base = 0
            for blk in render_list:
                text.stylize(self.color_map[blk.type], base, min(base + blk.size, area))
                base += blk.size
        else:
            base = 0
            for blk in render_list:
                for i in range(blk.size):
                    c, r = divmod(base + i, self.size.height)
                    if c >= self.size.width:
                        break
                    index = r * self.size.width + c
                    text.stylize(self.color_map[blk.type], index, min(index + 1, area))
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
