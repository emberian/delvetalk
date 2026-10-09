# Requires a C11 compiler, pkg-config, GMP and json-c >= 0.15.
CC ?= cc
CFLAGS ?= -O2 -g
CPPFLAGS += $(shell pkg-config --cflags gmp json-c)
LDLIBS += $(shell pkg-config --libs gmp json-c)
all: evaluator
evaluator: evaluator.c
	$(CC) $(CPPFLAGS) $(CFLAGS) -std=c11 -Wall -Wextra -Wpedantic $< -o $@ $(LDFLAGS) $(LDLIBS)
clean:
	rm -f evaluator
.PHONY: all clean
