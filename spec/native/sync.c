/* The journal's native IO. Durability: Lean's Handle.flush only drains the stdio buffer.
   This flushes it and then asks the OS to put the bytes on stable storage with
   fsync. With `full` it uses fcntl(F_FULLFSYNC) where it exists (macOS, where
   fsync alone does not flush the drive cache); that barrier stalls every other
   writer on the disk, so it is opt-in (`world-open {sync: "full"}`). */
#include <lean/lean.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <unistd.h>

lean_obj_res delvetalk_handle_sync(b_lean_obj_arg handle, uint8_t full, lean_obj_arg world) {
  FILE *file = (FILE *)lean_get_external_data(handle);
  if (fflush(file) != 0) return lean_io_result_mk_error(lean_decode_io_error(errno, NULL));
  int fd = fileno(file);
#ifdef F_FULLFSYNC
  if (full && fcntl(fd, F_FULLFSYNC) != -1) return lean_io_result_mk_ok(lean_box(0));
#else
  (void)full;
#endif
  if (fsync(fd) == -1) return lean_io_result_mk_error(lean_decode_io_error(errno, NULL));
  return lean_io_result_mk_ok(lean_box(0));
}

/* The block store's read (Host/Blocks.lean): `length` bytes at `offset` of the handle's file, by
   pread, so the stdio stream's own position and buffer are untouched. A short read is an error. */
lean_obj_res delvetalk_handle_pread(b_lean_obj_arg handle, uint64_t offset, uint64_t length, lean_obj_arg world) {
  FILE *file = (FILE *)lean_get_external_data(handle);
  int fd = fileno(file);
  lean_object *out = lean_alloc_sarray(1, length, length);
  uint8_t *p = lean_sarray_cptr(out);
  uint64_t got = 0;
  while (got < length) {
    ssize_t n = pread(fd, p + got, (size_t)(length - got), (off_t)(offset + got));
    if (n < 0) {
      if (errno == EINTR) continue;
      int e = errno;
      lean_dec(out);
      return lean_io_result_mk_error(lean_decode_io_error(e, NULL));
    }
    if (n == 0) break;
    got += (uint64_t)n;
  }
  if (got < length) {
    lean_dec(out);
    return lean_io_result_mk_error(lean_mk_io_user_error(lean_mk_string("short read in the block store")));
  }
  return lean_io_result_mk_ok(out);
}
