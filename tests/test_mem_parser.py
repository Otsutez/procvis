import pytest

from procvis.memory import (
    MapsEntry,
    MemoryParser,
    PageMapEntry,
    ProcessData,
)

test_data: list[tuple[str, dict[int, ProcessData]]] = [
    ("", {}),
    (
        "1\n7f3703e00000-7f3704000000 rw-s 12bc90000 00:06 338                       /dev/dri/renderD128",
        {
            1: ProcessData(
                maps_entries=[
                    MapsEntry(
                        address=(0x7F3703E00000, 0x7F3704000000),
                        perms="rw-s",
                        offset=0x12BC90000,
                        dev="00:06",
                        inode=338,
                        pathname="",
                    )
                ],
                pagemap_entries={},
            )
        },
    ),
    ("invalid", {}),
    ("1", {1: ProcessData(maps_entries=[], pagemap_entries={})}),
    (
        "1\ninvalid",
        {1: ProcessData(maps_entries=[], pagemap_entries={})},
    ),
    (
        "1\ninvalid\ninvalid",
        {1: ProcessData(maps_entries=[], pagemap_entries={})},
    ),
    (
        "1\n2\n3\n4\n5\n6",
        {
            1: ProcessData(maps_entries=[], pagemap_entries={}),
            2: ProcessData(maps_entries=[], pagemap_entries={}),
            3: ProcessData(maps_entries=[], pagemap_entries={}),
            4: ProcessData(maps_entries=[], pagemap_entries={}),
            5: ProcessData(maps_entries=[], pagemap_entries={}),
            6: ProcessData(maps_entries=[], pagemap_entries={}),
        },
    ),
    (
        "1\n55eea76c6000-55eea76dd000 r--p 00000000 103:02 9183882                   /usr/bin/zsh",
        {
            1: ProcessData(
                maps_entries=[
                    MapsEntry(
                        address=(0x55EEA76C6000, 0x55EEA76DD000),
                        perms="r--p",
                        offset=0x0,
                        dev="103:02",
                        inode=9183882,
                        pathname="/usr/bin/zsh",
                    )
                ],
                pagemap_entries={},
            ),
        },
    ),
    (
        "1\n55eea76c6000-55eea76dd000 r--p 00000000 103:02 9183882                   /usr/bin/zsh\n7ffe4ba6d000 1ef2a5 1 0 0 1",
        {
            1: ProcessData(
                maps_entries=[
                    MapsEntry(
                        address=(0x55EEA76C6000, 0x55EEA76DD000),
                        perms="r--p",
                        offset=0x0,
                        dev="103:02",
                        inode=9183882,
                        pathname="/usr/bin/zsh",
                    )
                ],
                pagemap_entries={
                    0x7FFE4BA6D000: PageMapEntry(
                        pfn=0x1EF2A5,
                        soft_dirty=True,
                        file_page=False,
                        swapped=False,
                        present=True,
                    )
                },
            ),
        },
    ),
    (
        "1\n55eea76c6000-55eea76dd000 r--p 00000000 103:02 9183882                   /usr/bin/zsh\n7ffe4ba6d000 1ef2a5 1 0 0 1\n7ffe4ba7d000 1ef2a5 1 0 0 1\n55eea76c6000-55eea76dd000 r--p 00000000 103:02 9183882                   /usr/bin/zsh\n7ffe4ba8d000 1ef2a5 1 0 0 1\n7ffe4ba9d000 1ef2a5 1 0 0 1",
        {
            1: ProcessData(
                maps_entries=[
                    MapsEntry(
                        address=(0x55EEA76C6000, 0x55EEA76DD000),
                        perms="r--p",
                        offset=0x0,
                        dev="103:02",
                        inode=9183882,
                        pathname="/usr/bin/zsh",
                    ),
                    MapsEntry(
                        address=(0x55EEA76C6000, 0x55EEA76DD000),
                        perms="r--p",
                        offset=0x0,
                        dev="103:02",
                        inode=9183882,
                        pathname="/usr/bin/zsh",
                    ),
                ],
                pagemap_entries={
                    0x7FFE4BA6D000: PageMapEntry(
                        pfn=0x1EF2A5,
                        soft_dirty=True,
                        file_page=False,
                        swapped=False,
                        present=True,
                    ),
                    0x7FFE4BA7D000: PageMapEntry(
                        pfn=0x1EF2A5,
                        soft_dirty=True,
                        file_page=False,
                        swapped=False,
                        present=True,
                    ),
                    0x7FFE4BA8D000: PageMapEntry(
                        pfn=0x1EF2A5,
                        soft_dirty=True,
                        file_page=False,
                        swapped=False,
                        present=True,
                    ),
                    0x7FFE4BA9D000: PageMapEntry(
                        pfn=0x1EF2A5,
                        soft_dirty=True,
                        file_page=False,
                        swapped=False,
                        present=True,
                    ),
                },
            ),
        },
    ),
]


class TestMemoryParser:
    @pytest.mark.parametrize("input,expected", test_data)
    def test_parse_output(self, input: str, expected: dict[int, ProcessData]):
        maps = MemoryParser().parse_output(input)
        # Check everything match except name
        assert len(maps) == len(expected)
        for pid, proc_data in maps.items():
            assert pid in expected
            assert proc_data.maps_entries == expected[pid].maps_entries
            assert proc_data.pagemap_entries == expected[pid].pagemap_entries
