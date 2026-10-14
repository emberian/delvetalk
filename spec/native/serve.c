/* The host's own sockets (`delvetalk-obend serve`, HOST-HANDOFF §5 "Serve"). Two unix listeners (the
   front's `host.sock` and the operator's `owner.sock`), every connection accepted, newline-framed
   requests read from each, and the next complete line handed to Lean in the order it completed,
   tagged with its connection and whether it came on the owner socket. Lean answers it and writes the
   reply line back through `delvetalk_serve_reply`. One thread: connections are concurrent, ops run
   one at a time in arrival order. SIGTERM and SIGINT end the loop: `delvetalk_serve_next` then
   answers the empty string. */
#include <lean/lean.h>
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>

#define MAX_CONNS 1024
#define MAX_LINE (16u << 20)
#define BACKLOG 128

typedef struct {
  int fd;
  int owner;
  uint64_t id;
  char *buf;
  size_t len, cap;
} conn_t;

typedef struct line {
  uint64_t id;
  int owner;
  char *text;
  size_t len;
  struct line *next;
} line_t;

static int listeners[2] = {-1, -1};
static conn_t conns[MAX_CONNS];
static int nconns = 0;
static uint64_t next_id = 1;
static line_t *head = NULL, *tail = NULL;
static volatile sig_atomic_t stopping = 0;

/* The stop's wake: the handler writes a byte the poll watches. The signal may land on any thread of
   the Lean runtime, so an EINTR in the serving thread's poll is not to be counted on; without the pipe
   the stop waited out the poll's second. */
static int wake[2] = {-1, -1};

static void on_stop(int sig) {
  (void)sig;
  stopping = 1;
  if (wake[1] >= 0) { int saved = errno; ssize_t w = write(wake[1], "x", 1); (void)w; errno = saved; }
}

static lean_obj_res io_error(void) { return lean_io_result_mk_error(lean_decode_io_error(errno, NULL)); }

static int nonblocking(int fd) {
  int flags = fcntl(fd, F_GETFL, 0);
  return flags < 0 ? -1 : fcntl(fd, F_SETFL, flags | O_NONBLOCK);
}

/* A listener at `path`, mode `mode` (0600 the public socket, 0660 the root socket), its group `gid`
   when not -1 (`--root-group`: the hand runs under its own uid in that group, ROOT §1.4). */
static int listen_on(const char *path, mode_t mode, gid_t gid) {
  struct sockaddr_un addr;
  if (strlen(path) >= sizeof(addr.sun_path)) { errno = ENAMETOOLONG; return -1; }
  unlink(path);
  int fd = socket(AF_UNIX, SOCK_STREAM, 0);
  if (fd < 0) return -1;
  memset(&addr, 0, sizeof(addr));
  addr.sun_family = AF_UNIX;
  strcpy(addr.sun_path, path);
  mode_t old = umask(0177);
  int bound = bind(fd, (struct sockaddr *)&addr, sizeof(addr));
  umask(old);
  if (bound < 0 || (gid != (gid_t)-1 && chown(path, (uid_t)-1, gid) < 0) || chmod(path, mode) < 0 ||
      listen(fd, BACKLOG) < 0 || nonblocking(fd) < 0) {
    int e = errno;
    close(fd);
    errno = e;
    return -1;
  }
  return fd;
}

lean_obj_res delvetalk_serve_listen(b_lean_obj_arg host, b_lean_obj_arg owner, b_lean_obj_arg group, lean_obj_arg world) {
  (void)world;
  if (wake[0] < 0 && pipe(wake) == 0) {
    for (int k = 0; k < 2; k++) { nonblocking(wake[k]); fcntl(wake[k], F_SETFD, FD_CLOEXEC); }
  }
  struct sigaction sa;
  memset(&sa, 0, sizeof(sa));
  sa.sa_handler = on_stop;
  sigemptyset(&sa.sa_mask);
  sigaction(SIGTERM, &sa, NULL);  /* no SA_RESTART: poll returns EINTR */
  sigaction(SIGINT, &sa, NULL);
  signal(SIGPIPE, SIG_IGN);       /* a client gone mid-reply is an EPIPE, not a death */
  gid_t gid = (gid_t)-1;
  const char *name = lean_string_cstr(group);
  if (*name) {
    struct group *g = getgrnam(name);
    if (!g) { errno = errno ? errno : ENOENT; return io_error(); }
    gid = g->gr_gid;
  }
  listeners[0] = listen_on(lean_string_cstr(host), 0600, (gid_t)-1);
  if (listeners[0] < 0) return io_error();
  listeners[1] = listen_on(lean_string_cstr(owner), 0660, gid);
  if (listeners[1] < 0) return io_error();
  return lean_io_result_mk_ok(lean_box(0));
}

static void drop(int i) {
  close(conns[i].fd);
  free(conns[i].buf);
  conns[i] = conns[--nconns];
}

static void queue(conn_t *c, const char *text, size_t len) {
  line_t *l = malloc(sizeof(line_t));
  if (!l) return;
  l->text = malloc(len + 1);
  if (!l->text) { free(l); return; }
  memcpy(l->text, text, len);
  l->text[len] = 0;
  l->len = len;
  l->id = c->id;
  l->owner = c->owner;
  l->next = NULL;
  if (tail) tail->next = l; else head = l;
  tail = l;
}

/* Read what one connection has; queue each complete line. 0 to keep it, -1 to drop it. */
static int take(conn_t *c) {
  for (;;) {
    if (c->cap - c->len < 65536) {
      size_t cap = c->cap ? c->cap * 2 : 131072;
      if (cap > MAX_LINE + 65536) cap = MAX_LINE + 65536;
      if (cap <= c->len) return -1;
      char *b = realloc(c->buf, cap);
      if (!b) return -1;
      c->buf = b;
      c->cap = cap;
    }
    ssize_t n = read(c->fd, c->buf + c->len, c->cap - c->len);
    if (n == 0) return -1;
    if (n < 0) return (errno == EAGAIN || errno == EWOULDBLOCK) ? 0 : (errno == EINTR ? 0 : -1);
    size_t start = 0, scan = c->len;
    c->len += (size_t)n;
    for (size_t i = scan; i < c->len; i++) {
      if (c->buf[i] == '\n') {
        queue(c, c->buf + start, i - start);
        start = i + 1;
      }
    }
    if (start > 0) {
      memmove(c->buf, c->buf + start, c->len - start);
      c->len -= start;
    }
    if (c->len > MAX_LINE) return -1;
  }
}

static lean_obj_res next_line(void) {
  line_t *l = head;
  head = l->next;
  if (!head) tail = NULL;
  char prefix[48];
  int p = snprintf(prefix, sizeof(prefix), "%llu %d ", (unsigned long long)l->id, l->owner);
  char *out = malloc((size_t)p + l->len + 1);
  if (!out) { free(l->text); free(l); return lean_io_result_mk_ok(lean_mk_string("")); }
  memcpy(out, prefix, (size_t)p);
  memcpy(out + p, l->text, l->len);
  out[p + l->len] = 0;
  /* A line that is not UTF-8 is answered by Lean's JSON parser as malformed; keep its bytes. */
  lean_object *s = lean_mk_string_from_bytes(out, (size_t)p + l->len);
  free(out);
  free(l->text);
  free(l);
  return lean_io_result_mk_ok(s);
}

/* `"<id> <owner> <line>"`, the next request in arrival order; "" once the loop is told to stop. */
lean_obj_res delvetalk_serve_next(lean_obj_arg world) {
  (void)world;
  for (;;) {
    if (stopping) return lean_io_result_mk_ok(lean_mk_string(""));
    if (head) return next_line();
    struct pollfd fds[3 + MAX_CONNS];
    for (int k = 0; k < 2; k++) { fds[k].fd = listeners[k]; fds[k].events = POLLIN; fds[k].revents = 0; }
    for (int i = 0; i < nconns; i++) { fds[2 + i].fd = conns[i].fd; fds[2 + i].events = POLLIN; fds[2 + i].revents = 0; }
    int count = nconns;
    fds[2 + count].fd = wake[0]; fds[2 + count].events = POLLIN; fds[2 + count].revents = 0;  /* -1: ignored by poll */
    if (poll(fds, (nfds_t)(3 + count), 1000) < 0) {
      if (errno == EINTR) continue;
      return io_error();
    }
    /* Connections first, newest last, so a line completed earlier is queued earlier. */
    for (int i = count - 1; i >= 0; i--) {
      if (!(fds[2 + i].revents & (POLLIN | POLLHUP | POLLERR))) continue;
      if (take(&conns[i]) < 0) drop(i);
    }
    for (int k = 0; k < 2; k++) {
      if (!(fds[k].revents & POLLIN)) continue;
      for (;;) {
        int fd = accept(listeners[k], NULL, NULL);
        if (fd < 0) break;
        if (nconns >= MAX_CONNS || nonblocking(fd) < 0) { close(fd); continue; }
        conns[nconns].fd = fd;
        conns[nconns].owner = k;
        conns[nconns].id = next_id++;
        conns[nconns].buf = NULL;
        conns[nconns].len = conns[nconns].cap = 0;
        nconns++;
      }
    }
  }
}

/* Write `line` and a newline to connection `id`; a connection already gone is skipped. */
lean_obj_res delvetalk_serve_reply(uint64_t id, b_lean_obj_arg line, lean_obj_arg world) {
  (void)world;
  int i = 0;
  while (i < nconns && conns[i].id != id) i++;
  if (i == nconns) return lean_io_result_mk_ok(lean_box(0));
  const char *text = lean_string_cstr(line);
  size_t len = lean_string_size(line) - 1, sent = 0;
  int failed = 0;
  while (!failed && sent <= len) {
    const char *from = sent < len ? text + sent : "\n";
    size_t want = sent < len ? len - sent : 1;
    ssize_t n = write(conns[i].fd, from, want);
    if (n > 0) { sent += (size_t)n; continue; }
    if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR)) {
      struct pollfd p = {conns[i].fd, POLLOUT, 0};
      if (poll(&p, 1, 30000) <= 0) failed = 1;
      continue;
    }
    failed = 1;
  }
  if (failed) drop(i);
  return lean_io_result_mk_ok(lean_box(0));
}

/* Close every connection and both listeners. */
lean_obj_res delvetalk_serve_close(lean_obj_arg world) {
  (void)world;
  while (nconns > 0) drop(nconns - 1);
  for (int k = 0; k < 2; k++) if (listeners[k] >= 0) { close(listeners[k]); listeners[k] = -1; }
  while (head) { line_t *l = head; head = l->next; free(l->text); free(l); }
  tail = NULL;
  return lean_io_result_mk_ok(lean_box(0));
}
