"""FreezeLog: notes where the program is when its window stops answering."""
import faulthandler
import os
import re
import sys
import threading
import time
import traceback

from .version import APP_VERSION
from .paths import user_dir


# ==========================================================================
# 7. Application - the two tabs in one window
# ==========================================================================


class FreezeLog:
    """Write down where the program is when its window stops answering.

    A windowed .exe shows nothing when it hangs or when a callback fails, so
    the cause can only be guessed afterwards. This keeps a small log next to
    the program (TCSPC_analysis_freeze.log) with what is needed to find it:

    - the main loop marks the time every half second; a watcher thread
      notices when that stops for LIMIT_S and writes the call stack of every
      thread - the main thread's is where the program is stuck;
    - an exception in a Tk callback, with its traceback (it still goes to the
      console as well, when there is one);
    - Python's own dump if the main loop stays silent for HARD_S (written by
      faulthandler, which needs no Python thread and so also works when the
      watcher cannot run).

    File dialogs and message boxes keep the main loop running and are not
    reported. With no callback running the program itself is not stuck - Tk
    is waiting inside its own loop - so that only counts after IDLE_S.
    Slow but healthy work on the main thread (starting Origin for an .opju
    export) is reported like any other stall; the stack says what it was.
    No measured data is written, only the name of the open file, and the
    user's home folder is cut out of every path the program writes itself
    (faulthandler's dump shows source paths as Python has them).
    """

    NAME = "TCSPC_analysis_freeze.log"
    BEAT_MS = 500
    LIMIT_S = 5.0       # a callback that keeps the window from answering this long
    IDLE_S = 30.0       # the same, with no callback running
    HARD_S = 60         # faulthandler's own dump
    MAX_BYTES = 512 * 1024

    def __init__(self, root, describe=lambda: ""):
        self.root = root
        self.describe = describe    # one line on what is loaded; main thread only
        self.path, self._fh = self._open()
        home = [re.escape(p) for p in re.split(r"[\\/]+", os.path.expanduser("~")) if p]
        # the home folder however it is spelt: either slash, doubled in a repr, any case
        self._home = re.compile(r"[\\/]+".join(home), re.IGNORECASE)
        self._lock = threading.Lock()
        self._note = ""
        self._seen = time.monotonic()
        self._told = None           # when the stall being reported began
        self._closed = threading.Event()
        if self._fh is None:        # nowhere to write: run without the log
            return
        self.write(f"started, version {APP_VERSION}, "
                   f"{'exe' if getattr(sys, 'frozen', False) else 'source'}, "
                   f"Python {sys.version.split()[0]}")
        root.report_callback_exception = self._callback_error
        self._beat()
        threading.Thread(target=self._watch, daemon=True).start()

    @classmethod
    def _open(cls):
        """(path, file) of the log: in user_dir() - beside the program when run
        from source, Documents\\TCSPC_analysis for a frozen build - else in
        LOCALAPPDATA."""
        here = user_dir()
        local = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                             "TCSPC_analysis")
        for folder in (here, local):
            path = os.path.join(folder, cls.NAME)
            try:
                os.makedirs(folder, exist_ok=True)
                cls._trim(path)
                return path, open(path, "a", encoding="utf-8",
                                  errors="replace", buffering=1)
            except OSError:
                continue
        return None, None

    @classmethod
    def _trim(cls, path):
        """Cut a log that has outgrown MAX_BYTES down to its newest half.

        (It used to be emptied at the next start - together with the very
        entries the user was about to send.)"""
        if not os.path.exists(path) or os.path.getsize(path) <= cls.MAX_BYTES:
            return
        with open(path, "rb") as fh:
            fh.seek(-(cls.MAX_BYTES // 2), os.SEEK_END)
            tail = fh.read()
        start = tail.find(b"\n====")          # the first whole entry of what is kept
        tail = tail[start + 1:] if start >= 0 else b""
        with open(path, "wb") as fh:
            fh.write(b"==== (older entries dropped: the log had grown past "
                     + str(cls.MAX_BYTES // 1024).encode() + b" kB)\n" + tail)

    def write(self, text):
        """Append a time-stamped entry; the user's home folder is left out of it."""
        if self._fh is None:
            return
        text = self._home.sub("~", text)
        with self._lock:
            try:
                self._fh.write(f"==== {time.strftime('%Y-%m-%d %H:%M:%S')}  {text}\n")
            except (OSError, ValueError):       # disk full, or closed on exit
                pass

    def _beat(self):
        """Main thread: the loop is alive."""
        if self._closed.is_set():
            return
        now = time.monotonic()
        if self._told is not None:
            self.write(f"answering again after {now - self._told:.1f} s")
            self._told = None
        self._seen = now
        try:
            self._note = self.describe()
        except Exception:                       # noqa: BLE001 - never break the loop
            self._note = ""
        faulthandler.dump_traceback_later(self.HARD_S, file=self._fh)
        self.root.after(self.BEAT_MS, self._beat)

    def _watch(self):
        """Watcher thread: report a main loop that has gone silent, once."""
        last = time.monotonic()
        while not self._closed.wait(1.0):
            now = time.monotonic()
            self._check(now - last)
            last = now

    WAKE_S = 10.0       # the watcher ticks every second; a gap like this is the PC asleep

    def _check(self, tick_gap):
        """One look at the main loop; True when a stall was written down.

        ``tick_gap`` is how long ago the watcher last looked. When that is far
        more than its one-second tick, nothing in the process ran - the
        computer was asleep (the clock used here keeps counting through
        sleep) - and the silence of the main loop means nothing: start over.
        """
        if tick_gap > self.WAKE_S:
            self._seen = time.monotonic()
            return False
        main = threading.main_thread().ident
        seen = self._seen
        quiet = time.monotonic() - seen
        if quiet < self.LIMIT_S or self._told is not None:
            return False
        frames = sys._current_frames()
        at = frames.get(main)
        if at is None:
            return False
        code = at.f_code                    # waiting in Tk's own loop?
        idle = (code.co_name == "mainloop"
                and os.path.basename(os.path.dirname(code.co_filename)) == "tkinter")
        if idle and quiet < self.IDLE_S:
            return False
        names = {t.ident: t.name for t in threading.enumerate()}
        lines = [f"window not answering for {quiet:.0f} s"
                 + (" (no callback running: Tk itself is busy, or the window is"
                    " being moved)" if idle else ""),
                 f"open: {self._note or '-'}"]
        for ident, frame in frames.items():
            lines.append(f"-- thread {names.get(ident, ident)}"
                         + ("  <-- the window's thread" if ident == main else ""))
            lines += [ln.rstrip() for ln in traceback.format_stack(frame)]
        self._told = seen
        self.write("\n".join(lines))
        return True

    def _callback_error(self, exc, val, tb):
        self.write("error in a callback\n"
                   + "".join(traceback.format_exception(exc, val, tb)).rstrip())
        if sys.stderr is not None:              # as Tk does without the log
            print("Exception in Tkinter callback", file=sys.stderr)
            traceback.print_exception(exc, val, tb)

    def close(self):
        self._closed.set()
        if self._fh is not None:
            faulthandler.cancel_dump_traceback_later()
            with self._lock:
                self._fh.close()
