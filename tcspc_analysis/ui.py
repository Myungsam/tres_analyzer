"""The small pieces every window builds its controls from: a button in a role
colour, a titled group, a number box with arrows, the plot toolbar, and the
export buttons that turn orange while ".opju" is ticked."""
import math
from decimal import Decimal, InvalidOperation
from weakref import WeakKeyDictionary

from matplotlib.backends.backend_tkagg import NavigationToolbar2Tk

import tkinter as tk
from tkinter import ttk

from .theme import FIXED_FONT, PANEL


def button(parent, text, command, role=None, **kw):
    """A ttk button; ``role`` ("Analysis", "Export", "Opju", "Run", "Stop") picks
    its colour, None the plain grey one."""
    if role:
        kw.setdefault("style", f"{role}.TButton")
    return ttk.Button(parent, text=text, command=command, **kw)


def group(parent, text, **kw):
    """A titled group box (ttk.Labelframe)."""
    kw.setdefault("padding", (6, 2, 6, 4))
    return ttk.Labelframe(parent, text=text, **kw)


def _decimals(text):
    """Digits after the point in ``text`` as written ("1e4" and "10000" have 0)."""
    try:
        return max(0, -Decimal(text.strip()).as_tuple().exponent)
    except (InvalidOperation, TypeError, AttributeError):
        return 0


def spin(parent, var, step, lo=None, hi=None, on_change=None, width=8, debounce_ms=250):
    """A number box with up / down arrows bound to the Tk variable ``var``.

    The arrows (and the Up / Down keys) add or take ``step``, kept within
    [lo, hi] (None: no limit), and write the number with as many decimals as
    the box or the step has - Tk's own stepping rewrote 10000 as "10000" but
    -13496.3 as "-13496", and jumped to the lower limit on text it could not
    read. Text that is not a number is left alone. ``on_change()`` runs once,
    ``debounce_ms`` after the last step; typed text is the caller's (its
    <Return> / <FocusOut> bindings). The mouse wheel does nothing: it would
    change a value while the page is scrolled past it.
    """
    sb = ttk.Spinbox(parent, textvariable=var, width=width, font=FIXED_FONT,
                     increment=step,
                     from_=lo if lo is not None else -1e12,
                     to=hi if hi is not None else 1e12)
    pending = [None]

    def cancel(event=None):
        if pending[0] is not None:
            try:
                sb.after_cancel(pending[0])
            except tk.TclError:
                pass
            pending[0] = None

    def fire():
        pending[0] = None
        on_change()

    def _step(sign):
        # the box's text, not var.get(): an IntVar raises on "" or "abc"
        text = sb.get()
        try:
            value = float(text)
        except ValueError:
            return "break"
        if not math.isfinite(value):
            return "break"
        value += sign * step
        if lo is not None:
            value = max(value, lo)
        if hi is not None:
            value = min(value, hi)
        digits = max(_decimals(text), _decimals(f"{step:g}"))
        value = round(value, digits) + 0.0          # -0.0 is written as 0
        var.set(f"{value:.{digits}f}")
        if on_change is not None:
            cancel()
            pending[0] = sb.after(debounce_ms, fire)
        return "break"

    sb.bind("<<Increment>>", lambda e: _step(+1))
    sb.bind("<<Decrement>>", lambda e: _step(-1))
    sb.bind("<MouseWheel>", lambda e: "break")
    sb.bind("<Destroy>", cancel, add="+")
    return sb


class NavToolbar(NavigationToolbar2Tk):
    """matplotlib's toolbar, in the window's colours, that tells the window
    when it changed the view.

    ``on_home()`` runs after Home (the window frames its full view);
    ``on_nav()`` after Back / Forward and a zoom or pan drag (the window reads
    the new limits). Only axes that can be navigated are kept in the history,
    so a colour bar's contrast is never put back by Back or Home.
    """

    def __init__(self, canvas, master, on_home=None, on_nav=None):
        self._on_home, self._on_nav = on_home, on_nav
        super().__init__(canvas, master, pack_toolbar=False)
        self.configure(bg=PANEL)
        for child in self.winfo_children():
            try:
                child.configure(bg=PANEL)
            except tk.TclError:
                pass

    def _nav(self):
        if self._on_nav is not None:
            self._on_nav()

    def home(self, *args):
        super().home(*args)
        if self._on_home is not None:
            self._on_home()

    def back(self, *args):
        super().back(*args)
        self._nav()

    def forward(self, *args):
        super().forward(*args)
        self._nav()

    def release_zoom(self, event):
        busy = self._zoom_info is not None
        super().release_zoom(event)
        if busy:
            self._nav()

    def release_pan(self, event):
        busy = self._pan_info is not None
        super().release_pan(event)
        if busy:
            self._nav()

    def _update_view(self):
        """Back / Forward / Home put back the limits only. The positions a
        history entry also holds may be old: a window lays its panels out by
        itself, and would have to draw again to move them back."""
        entry = self._nav_stack()
        if entry is None:
            return
        for ax, (view, _position) in list(entry.items()):
            ax._set_view(view)
        self.canvas.draw_idle()

    def push_current(self):
        """Push the limits of the navigable axes (not the colour bar's)."""
        self._nav_stack.push(WeakKeyDictionary(
            {ax: (ax._get_view(),
                  (ax.get_position(True).frozen(), ax.get_position().frozen()))
             for ax in self.canvas.figure.axes if ax.get_navigate()}))
        self.set_history_buttons()

    def forget_history(self):
        """Drop the history; what is on screen now is the new Home."""
        self.update()               # NavigationToolbar2.update: clears the stack
        self.push_current()

    def ensure_base(self):
        """Keep what is on screen as Home before the window changes the view itself."""
        if self._nav_stack() is None:
            self.push_current()

    def rebase(self, ax):
        """``ax`` alone was drawn again: in every view the history keeps, put
        its view as it is now, so Home / Back / Forward never bring back a
        view of the old curve (or of another scale), while the zoom history
        of the other axes stays."""
        self.ensure_base()
        entry = (ax._get_view(), (ax.get_position(True).frozen(), ax.get_position().frozen()))
        for i in range(len(self._nav_stack)):
            self._nav_stack[i][ax] = entry
        self.set_history_buttons()

    def locked(self):
        """True while pan / zoom mode (or a drag of it) holds the canvas."""
        return self.canvas.widgetlock.locked()

    def dragging(self):
        """True while a zoom or pan drag of the toolbar is under way."""
        return self._zoom_info is not None or self._pan_info is not None


def attach_toolbar(canvas, master, before=None, on_home=None, on_nav=None):
    """A NavToolbar for ``canvas``, packed into ``master`` above ``before``."""
    tb = NavToolbar(canvas, master, on_home=on_home, on_nav=on_nav)
    if before is not None:
        tb.pack(side="top", fill="x", before=before)
    else:
        tb.pack(side="top", fill="x")
    return tb


class ExportButtons:
    """The buttons that export data: blue, orange while ``var_opju`` is ticked.

    One trace on the variable restyles every button added; a button whose
    window was closed is dropped on the way.
    """

    def __init__(self, var_opju):
        self.var = var_opju
        self.buttons = []
        var_opju.trace_add("write", lambda *args: self.restyle())

    def style(self):
        return "Opju.TButton" if self.var.get() else "Export.TButton"

    def add(self, btn):
        self.buttons.append(btn)
        btn.configure(style=self.style())
        return btn

    def restyle(self):
        style, alive = self.style(), []
        for btn in self.buttons:
            try:
                if btn.winfo_exists():
                    btn.configure(style=style)
                    alive.append(btn)
            except tk.TclError:
                pass
        self.buttons = alive
