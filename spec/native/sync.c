/* Durability for the journal: Lean's Handle.flush only drains the stdio buffer.
   This flushes it and then asks the OS to put the bytes on stable storage:
   fcntl(F_FULLFSYNC) where it exists (macOS, where fsync alone does not flush
   the drive cache), otherwise fsync. */
#include <lean/lean.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <unistd.h>

lean_obj_res delvetalk_handle_sync(b_lean_obj_arg handle, lean_obj_arg world) {
  FILE *file = (FILE *)lean_get_external_data(handle);
  if (fflush(file) != 0) return lean_io_result_mk_error(lean_decode_io_error(errno, NULL));
  int fd = fileno(file);
#ifdef F_FULLFSYNC
  if (fcntl(fd, F_FULLFSYNC) == -1 && fsync(fd) == -1)
    return lean_io_result_mk_error(lean_decode_io_error(errno, NULL));
#else
  if (fsync(fd) == -1) return lean_io_result_mk_error(lean_decode_io_error(errno, NULL));
#endif
  return lean_io_result_mk_ok(lean_box(0));
}
