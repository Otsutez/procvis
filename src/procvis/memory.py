import os
import pwd
import re
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


class GetProcessMapError(Exception):
    """Raised when memory_parser failed to retrieve process data"""

    pass


@dataclass
class Stat:
    pid: int
    comm: str
    cmdline: str
    user: str
    state: str
    ppid: int
    pgrp: int
    session: int
    tty_nr: int
    tpgid: int
    flags: int
    minflt: int
    cminflt: int
    majflt: int
    cmajflt: int
    utime: int
    stime: int
    cutime: int
    cstime: int
    priority: int
    nice: int
    num_threads: int
    itrealvalue: int
    starttime: int
    vsize: int
    rss: int
    rsslim: int
    startcode: int
    endcode: int
    startstack: int
    kstkesp: int
    kstkeip: int
    signal: int
    blocked: int
    sigignore: int
    sigcatch: int
    wchan: int
    nswap: int
    cnswap: int
    exit_signal: int
    processor: int
    rt_priority: int
    policy: int
    delayacct_blkio_ticks: int
    guest_time: int
    cguest_time: int
    start_data: int
    end_data: int
    start_brk: int
    arg_start: int
    arg_end: int
    env_start: int
    env_end: int
    exit_code: int


@dataclass
class PageMapEntry:
    pfn: int
    soft_dirty: bool
    file_page: bool
    swapped: bool
    present: bool


@dataclass
class MapsEntry:
    start: int
    end: int
    perms: str
    offset: int
    dev: str
    inode: int
    pathname: str


@dataclass
class ProcessData:
    maps_entries: list[MapsEntry]
    pagemap_entries: dict[int, PageMapEntry]


class MemoryReader:
    PAGE_SIZE: int = os.sysconf("SC_PAGESIZE")

    @staticmethod
    def get_mem(rss: int) -> str:
        return MemoryReader.format_bytes(rss * MemoryReader.PAGE_SIZE)

    # Source - https://stackoverflow.com/a/49361727
    # Posted by Pietro Battiston, modified by community. See post 'Timeline' for change history
    # Retrieved 2026-08-31, License - CC BY-SA 4.0
    @staticmethod
    def format_bytes(size: int) -> str:
        power = float(2**10)
        n = 0
        power_labels = {0: "B", 1: "K", 2: "M", 3: "G", 4: "T"}
        num = float(size)
        while num > power:
            num /= power
            n += 1
        if num >= 10 or int(num) == 0:
            return f"{int(num)}{power_labels[n]}"
        else:
            return f"{num:.1f}{power_labels[n]}"

    @staticmethod
    def unformat_bytes(size: str) -> int:
        num, suffix = float(size[:-1]), size[-1]
        power_labels = {"B": 1, "K": 2**10, "M": 2**20, "G": 2**30, "T": 2**40}
        return int(num * power_labels[suffix])

    @staticmethod
    def read_cmdline(pid: int) -> str:
        cmdline_file = Path(f"/proc/{pid}/cmdline")
        try:
            with cmdline_file.open("r") as c:
                return c.read().strip()
        except OSError:
            return ""

    @staticmethod
    def read_user(pid: int) -> str:
        pid_dir = Path(f"/proc/{pid}")
        if pid_dir.exists():
            stat = os.stat(pid_dir)
            uid = stat.st_uid
            return pwd.getpwuid(uid).pw_name.strip()
        else:
            return ""

    @staticmethod
    def read_stat(pid: int) -> Stat | None:
        cmdline = MemoryReader.read_cmdline(pid)
        user = MemoryReader.read_user(pid)
        stat_file = Path(f"/proc/{pid}/stat")
        try:
            with stat_file.open("r") as s:
                stat = s.read().strip()

                # Parse stat
                if match := re.match(
                    r"^.*\((?P<comm>[^\)]*)\)\s(?P<state>[RSDZTtWXxKWPI])\s(?P<rest>.*)$",
                    stat,
                ):
                    comm = match.group("comm")
                    state = match.group("state")
                    rest = map(int, match.group("rest").split())
                    return Stat(pid, comm, cmdline, user, state, *rest)
                else:
                    # Return None if format of stat file does not match our expectations
                    return None
        except (OSError, ValueError):
            return None

    @staticmethod
    def get_pids() -> list[int]:
        proc_dir = Path("/proc")
        pids = [int(file) for file in os.listdir(proc_dir) if file.isdigit()]
        return pids

    @staticmethod
    def get_all_stats() -> list[Stat]:
        pids = MemoryReader.get_pids()
        result: list[Stat] = []
        for pid in pids:
            stat = MemoryReader.read_stat(pid)
            if stat:
                result.append(stat)

        return result

    @staticmethod
    def run_reader(pids: str) -> str:
        process = subprocess.run(
            ["build/bin/reader"],
            input=pids,
            capture_output=True,
            text=True,
            check=True,
        )
        return process.stdout

    @staticmethod
    def get_process_data(pid: int) -> ProcessData:
        pids = str(pid) + "\n"
        try:
            output = MemoryReader.run_reader(pids)
        except subprocess.CalledProcessError as e:
            exception = GetProcessMapError(e.stderr)
            raise exception
        parser = MemoryParser()
        map = parser.parse_output(output)
        return map[pid]


class MemoryParser:
    """
    Gather all processes memory usage and return concise data for RamView to
    interpret and render
    """

    def __init__(self):
        self.lines: Iterator[str] | None = None
        self.curr: str | None = None

    def accept(self):
        if self.lines is None:
            return
        try:
            self.curr = next(self.lines)
        except StopIteration:
            self.curr = None

    def get_process_name(self, pid: int) -> str:
        path = Path(f"/proc/{pid}/comm")
        try:
            with path.open() as f:
                return f.read().strip()
        except (FileNotFoundError, PermissionError, OSError):
            return ""

    def parse_pagemap_entry(self) -> tuple[int, PageMapEntry] | None:
        if self.curr is None:
            return None

        pattern = re.compile(
            r"""
            ^
            (?P<vaddr>[0-9a-f]+)\s # virtual address
            (?P<pfn>[0-9a-f]+)\s   # page frame number
            (?P<soft>[01])\s       # soft dirty bit
            (?P<filepage>[01])\s   # file page bit
            (?P<swapped>[01])\s    # swapped bit
            (?P<present>[01])      # present bit
            $
            """,
            re.VERBOSE,
        )

        if match := pattern.match(self.curr):
            self.accept()
            groups = match.groupdict()
            vaddr = int(groups["vaddr"], 16)
            pfn = int(groups["pfn"], 16)
            soft = groups["soft"] == "1"
            filepage = groups["filepage"] == "1"
            swapped = groups["swapped"] == "1"
            present = groups["present"] == "1"

            pagemap_entry = PageMapEntry(
                pfn=pfn,
                soft_dirty=soft,
                file_page=filepage,
                swapped=swapped,
                present=present,
            )
            return (vaddr, pagemap_entry)

    def parse_maps_entry(self) -> MapsEntry | None:
        if self.curr is None:
            return None

        # Regular expression to match maps entry
        pattern = re.compile(
            r"""
            ^
            (?P<addr1>[0-9a-f]+)-              # first address
            (?P<addr2>[0-9a-f]+)\s             # second address
            (?P<perms>[r\-][w\-][x\-][s\-p])\s # permissions
            (?P<offset>[0-9a-f]+)\s            # offset
            (?P<dev>\d+:\d+)\s                 # device
            (?P<inode>\d+)\s+                  # inode
            (?P<pathname>.*)                   # pathname
            $
            """,
            re.VERBOSE,
        )
        if match := pattern.match(self.curr):
            self.accept()
            groups = match.groupdict()
            start = int(groups["addr1"], 16)
            end = int(groups["addr2"], 16)
            perms = groups["perms"]
            offset = int(groups["offset"], 16)
            dev = groups["dev"]
            inode = int(groups["inode"])
            pathname = groups["pathname"]

            return MapsEntry(
                start=start,
                end=end,
                perms=perms,
                offset=offset,
                dev=dev,
                inode=inode,
                pathname=pathname,
            )

        return None

    def parse_pid(self) -> int | None:
        if self.curr is None:
            return None

        if self.curr.isdigit():
            pid = int(self.curr, 10)
            self.accept()
            return pid

    def parse_output(self, output: str) -> dict[int, ProcessData]:
        """
        Grammar:
        output = proc_data
        proc_data = pid data*
        data = maps_entry pagemap_entry*
        """
        # Prepare iterator
        self.lines = iter(output.splitlines())
        self.accept()

        map: dict[int, ProcessData] = {}
        while (pid := self.parse_pid()) is not None:
            maps_entries: list[MapsEntry] = []
            pagemap_entries: dict[int, PageMapEntry] = {}

            while (maps_entry := self.parse_maps_entry()) is not None:
                maps_entries.append(maps_entry)
                while (data := self.parse_pagemap_entry()) is not None:
                    vaddr, pagemap_entry = data
                    pagemap_entries[vaddr] = pagemap_entry
            map[pid] = ProcessData(
                maps_entries=maps_entries, pagemap_entries=pagemap_entries
            )
        return map


def main():
    pid = int(input("pid: "))
    process_data: ProcessData = MemoryReader.get_process_data(pid)
    for map in process_data.maps_entries:
        print(map)


if __name__ == "__main__":
    main()
