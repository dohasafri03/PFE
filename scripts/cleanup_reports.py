import argparse
import os
import shutil
import sys
import time


def _iter_report_dirs(base_dir: str):
  if not os.path.isdir(base_dir):
    return
  for name in os.listdir(base_dir):
    p = os.path.join(base_dir, name)
    if os.path.isdir(p):
      yield p


def main() -> int:
  parser = argparse.ArgumentParser(description="Delete old generated reports folders.")
  parser.add_argument("--base-dir", default="dossiers_generes", help="Reports base directory")
  parser.add_argument("--days", type=int, default=30, help="Delete folders older than N days (by mtime)")
  parser.add_argument("--dry-run", action="store_true", help="Only print what would be deleted")
  args = parser.parse_args()

  base_dir = args.base_dir
  if not os.path.isdir(base_dir):
    print(f"[cleanup] base dir not found: {base_dir}")
    return 0

  now = time.time()
  cutoff = now - (max(0, int(args.days)) * 24 * 60 * 60)

  candidates = []
  for d in _iter_report_dirs(base_dir):
    try:
      mtime = os.path.getmtime(d)
    except OSError:
      continue
    if mtime < cutoff:
      candidates.append((mtime, d))

  candidates.sort(key=lambda x: x[0])

  if not candidates:
    print("[cleanup] nothing to delete")
    return 0

  for mtime, d in candidates:
    age_days = int((now - mtime) // (24 * 60 * 60))
    stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))
    if args.dry_run:
      print(f"[dry-run] delete ({age_days}d old, mtime={stamp}): {d}")
    else:
      print(f"[delete] ({age_days}d old, mtime={stamp}): {d}")
      shutil.rmtree(d, ignore_errors=False)

  print(f"[cleanup] done. deleted={len(candidates)} dry_run={bool(args.dry_run)}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())

