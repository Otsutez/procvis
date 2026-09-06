/*
Helper with CAP_SYS_ADMIN capability, used for reading /proc/pid/pagemap and /proc/pid/maps
Input:
    pid1
    pid2
    ...

Output:
    pid1
    address-address perms offset dev inode pathname
    vaddr paddr
    vaddr paddr 
    address-address perms offset dev inode pathname
    vaddr paddr 
    vaddr paddr 
    vaddr paddr 
    pid2
    ...
*/

#include <linux/limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#include <stdint.h>
#include <sys/stat.h>
#include <unistd.h>
#include <string.h>
#include <fcntl.h>
#include <limits.h>

#define LINE_LENGTH PATH_MAX + 128

/* page_map_entry struct and pagemap_get_entry() function taken from stack overflow https://stackoverflow.com/questions/6284810/proc-pid-pagemaps-and-proc-pid-maps-linux */
typedef struct {
    uint64_t pfn : 55;
    unsigned int soft_dirty : 1;
    unsigned int file_page : 1;
    unsigned int swapped : 1;
    unsigned int present : 1;
} pagemap_entry;

/* Parse the pagemap entry for the given virtual address.
 *
 * @param[out] entry      the parsed entry
 * @param[in]  pagemap_fd file descriptor to an open /proc/pid/pagemap file
 * @param[in]  vaddr      virtual address to get entry for
 * @return 0 for success, 1 for failure
 */
int pagemap_get_entry(pagemap_entry *entry, int pagemap_fd, uintptr_t vpn)
{
    size_t nread;
    ssize_t ret;
    uint64_t data;

    nread = 0;
    while (nread < sizeof(data)) {
        ret = pread(pagemap_fd, ((uint8_t*)&data) + nread, sizeof(data) - nread,
                (vpn / sysconf(_SC_PAGESIZE)) * sizeof(data) + nread);
        nread += ret;
        if (ret <= 0) {
            return 1;
        }
    }
    entry->pfn = data & (((uint64_t)1 << 55) - 1);
    entry->soft_dirty = (data >> 55) & 1;
    entry->file_page = (data >> 61) & 1;
    entry->swapped = (data >> 62) & 1;
    entry->present = (data >> 63) & 1;
    return 0;
}


int main() {
    long page_size = sysconf(_SC_PAGESIZE);
    uint64_t pid;
    char line[LINE_LENGTH];
    char maps_path[PATH_MAX];
    char pagemap_path[PATH_MAX];

    while (scanf("%lu", &pid) == 1) {
        printf("%lu\n", pid);

        /* Open maps file */
        snprintf(maps_path, PATH_MAX, "/proc/%lu/maps", pid);
        FILE *maps = fopen(maps_path, "r");
        if (maps == NULL) {
            fprintf(stderr, "Error: failed to open maps at %s\n", maps_path);
            // exit(EXIT_FAILURE);
            continue;
        }
        /* Open pagemap file */
        snprintf(pagemap_path, PATH_MAX, "/proc/%lu/pagemap", pid);
        int pagemap_fd = open(pagemap_path, O_RDONLY);
        if (pagemap_fd < 0) {
            fprintf(stderr, "Error: failed to open pagemap at %s\n", pagemap_path);
            // exit(EXIT_FAILURE);
            continue;
        }

        /* Read vaddr range https://man7.org/linux/man-pages/man5/proc_pid_maps.5.html */
        while (fgets(line, LINE_LENGTH, maps)) {
            printf("%s", line);
            char *address = strtok(line, " ");

            /* Check address range */
            char *low_str = strtok(address, "-");
            char *high_str = strtok(NULL, "-");
            if (low_str == NULL || high_str == NULL) {
                continue;
            }

            char *endptr;
            uint64_t low = strtoull(low_str, &endptr, 16);
            if (low_str == endptr || errno == ERANGE) {
                continue;
            }
            uint64_t high = strtoull(high_str, &endptr, 16);
            if (high_str == endptr || errno == ERANGE) {
                continue;
            }

            pagemap_entry entry;
            for (uint64_t vpn = low; vpn < high; vpn += page_size) {
                int res = pagemap_get_entry(&entry, pagemap_fd, vpn);
                if (res == 1) {
                    printf("%lx\n", (uint64_t) vpn);
                } else {
                    printf("%lx %lx %u %u %u %u\n", vpn, (uint64_t) entry.pfn, entry.soft_dirty, entry.file_page, entry.swapped, entry.present);
                }
            }

        }
        
    }
    return 0;
}
