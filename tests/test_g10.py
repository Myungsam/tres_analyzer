"""Stage 3, group G10: the freeze log, the launcher, the documents (review items D-17, S-3c; D-18 - D-23 are
checked by running the launcher and by check_doc.py). See _harness.py."""
import ctypes
import os
import time

from _harness import *                        # noqa: F401,F403
from _harness import NEW, ROOT, TMP, check, finish, np, pump, root, section

real_dir = NEW.user_dir
NEW.user_dir = lambda: TMP
LOG = os.path.join(TMP, NEW.FreezeLog.NAME)


def fresh_log():
    if os.path.exists(LOG):
        os.remove(LOG)
    log = NEW.FreezeLog(root, lambda: "file.phu")
    return log


# ---------------------------------------------------------------------------------------------
if section("D-17"):
    # a log that has grown past its limit keeps its latest entries
    limit = NEW.FreezeLog.MAX_BYTES
    with open(LOG, "w", encoding="utf-8") as fh:
        n = 0
        while fh.tell() <= limit + 4096:
            n += 1
            fh.write(f"==== 2026-01-01 00:00:00  entry {n:06d} " + "x" * 80 + "\n")
    last = f"entry {n:06d}"
    path, fh = NEW.FreezeLog._open()
    fh.write("==== now  appended\n")
    fh.close()
    body = open(LOG, encoding="utf-8").read()
    check("an oversized log is cut down, not emptied: well below the limit, newest entries kept",
          0 < len(body.encode("utf-8")) < 0.8 * limit and last in body and "entry 000001 " not in body,
          f"{len(body)} bytes, last kept: {last in body}")
    check("... it starts on a whole line that says older entries were dropped, and new entries follow at the end",
          body.splitlines()[0].startswith("====") and "older entries" in body.splitlines()[0]
          and all(ln.startswith("====") for ln in body.splitlines()[:5]) and body.rstrip().endswith("appended"),
          body[:120])
    open(LOG, "w").write("==== small\n")
    path, fh = NEW.FreezeLog._open()
    fh.close()
    check("a small log is left as it is", open(LOG).read() == "==== small\n")
    # waking up from sleep is not a frozen window
    log = fresh_log()
    try:
        log._seen = time.monotonic() - 3600.0          # as after an hour with the lid closed
        told = log._check(tick_gap=3600.0)
        body = open(LOG, encoding="utf-8").read()
        check("after a gap in which the watcher itself did not run (sleep), no stall is reported",
              not told and "not answering" not in body and time.monotonic() - log._seen < 5.0, body[-200:])
        log._seen = time.monotonic() - 50.0
        told = log._check(tick_gap=1.0)
        body = open(LOG, encoding="utf-8").read()
        check("a main loop silent for 50 s while the watcher kept running is still reported",
              told and "window not answering for 50 s" in body, body[-300:])
    finally:
        log.close()

# ---------------------------------------------------------------------------------------------
if section("S-3c"):
    # the home folder is cut out of the log however it is written
    home = os.path.expanduser("~")
    drive, rest = os.path.splitdrive(home)
    buf = ctypes.create_unicode_buffer(600)
    ctypes.windll.kernel32.GetShortPathNameW(home, buf, 600)
    forms = {"as it is": home, "forward slashes": home.replace("\\", "/"), "upper case": home.upper(),
             "without the drive letter": rest, "without the drive, forward slashes": rest.replace("\\", "/"),
             "doubled backslashes (a repr)": home.replace("\\", "\\\\")}
    if buf.value and buf.value.lower() != home.lower():
        forms["8.3 short name"] = buf.value
    log = fresh_log()
    try:
        for label, text in forms.items():
            log.write(f"MARK {label}: {text}\\Data\\sample.phu")
    finally:
        log.close()
    body = open(LOG, encoding="utf-8").read()
    user = os.path.basename(home)
    for label, text in forms.items():
        line = [ln for ln in body.splitlines() if f"MARK {label}:" in ln][0]
        check(f"home folder {label}: replaced by ~, the user name is not in the log",
              user.lower() not in line.lower() and "~" in line and "sample.phu" in line, line[-90:])
    log = fresh_log()
    try:
        log.write(r"other folders stay: C:\Program Files\Origin\x.dll and D:\Users.txt")
    finally:
        log.close()
    body = open(LOG, encoding="utf-8").read()
    check("other paths are left alone", r"C:\Program Files\Origin\x.dll" in body and r"D:\Users.txt" in body, body[-120:])

NEW.user_dir = real_dir
finish()
