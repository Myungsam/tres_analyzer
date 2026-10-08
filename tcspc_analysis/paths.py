"""Where the program lives on disk."""
import os
import sys


def program_dir():
    """The folder the program is started from: the one holding the .exe in a
    frozen build, otherwise the one holding the package (where the launcher
    and Data\\ are)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
