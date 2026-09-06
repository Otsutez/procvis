CC := gcc
CFLAGS := -Wall -Wextra -O2

SRC := src/procvis/reader.c
BIN := build/bin/reader

.PHONY: all clean

all: $(BIN)

$(BIN): $(SRC) | build/bin
	$(CC) $(CFLAGS) $< -o $@
	sudo setcap cap_sys_admin+ep $@

build/bin:
	mkdir -p $@

clean:
	rm -rf build
