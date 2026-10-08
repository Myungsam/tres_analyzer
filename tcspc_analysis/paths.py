"""Where the program lives on disk, and where it writes."""
import os
import sys


def program_dir():
    """The folder the program is started from: the one holding the .exe in a
    frozen build, otherwise the one holding the package (where the launcher
    and Data\\ are)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _documents_dir():
    """The user's Documents folder (wherever Windows has it), else ~\\Documents."""
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(260)
        # CSIDL_PERSONAL = 5, SHGFP_TYPE_CURRENT = 0
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:
            return buf.value
    except (AttributeError, OSError):       # not Windows
        pass
    return os.path.join(os.path.expanduser("~"), "Documents")


def user_dir():
    """The folder for what the program writes on its own: the default Data\\
    folder for exports and the freeze log.

    Run from source this is the program folder. A frozen build is unpacked
    from a zip and its folder is replaced as a whole by the next version, so
    there it is Documents\\TCSPC_analysis instead."""
    if getattr(sys, "frozen", False):
        return os.path.join(_documents_dir(), "TCSPC_analysis")
    return program_dir()
