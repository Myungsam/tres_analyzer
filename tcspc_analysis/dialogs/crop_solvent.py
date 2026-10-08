"""The Crop window: loading and scaling the solvent."""
import numpy as np

from tkinter import filedialog, messagebox

from ..phu import read_phu
from ..util import short_name
from ..model import solvent_mismatch


class _CropSolvent:
    """The solvent of the Crop window: its file, its scale (slider and
    entry), and whether Apply switches the subtraction on. Part of
    CropDialog (crop.py).
    """

    # -- solvent ---------------------------------------------------------
    def _sync_solvent_controls(self):
        """File-name label and SCALE widgets follow whether a solvent is loaded."""
        loaded = self._solvent is not None
        self.var_solv_name.set(short_name(self._solvent["path"]) if loaded
                               else "none")
        self.scale.state(["!disabled"] if loaded else ["disabled"])
        self.ent_scale.configure(state="normal" if loaded else "disabled")

    def _set_scale(self, v, from_slider=False):
        """Take ``v`` as the scale and mirror it into the entry and the slider.

        Setting a ttk.Scale fires its command, so _busy keeps that from coming
        back in as a slider move; a value past the slider's range parks it at 2.
        """
        self._scale = v
        self.var_scale.set(f"{v:g}")
        if not from_slider:
            self._busy = True
            try:
                self.scale.set(min(v, 2.0))
            finally:
                self._busy = False

    def _on_slider(self, value):
        if self._busy:
            return
        v = round(float(value), 2)      # the widget reports 0.8532110091743119
        if v != self._scale:
            self._set_scale(v, from_slider=True)
            self._schedule()

    def _on_scale_entry(self):
        """Read the SCALE box; anything but a finite number >= 0 is put back."""
        if not self.alive:
            return
        try:
            v = float(self.var_scale.get())
        except ValueError:
            v = None
        if v is None or not np.isfinite(v) or v < 0:
            self.var_scale.set(f"{self._scale:g}")
            return
        if v != self._scale:
            self._set_scale(v)
            self._update_overlay()

    def _load_solvent(self):
        """Pick the solvent .phu; it is only taken if it sits on the sample's grid."""
        path = filedialog.askopenfilename(
            parent=self.win, title="Open the solvent measurement",
            filetypes=[("PicoQuant histogram", "*.phu"), ("All files", "*.*")])
        if not path:
            return
        try:
            solvent = read_phu(path)
        except Exception as exc:
            messagebox.showerror("Could not read file", str(exc), parent=self.win)
            return
        errors, notes = solvent_mismatch(self.model.phu, solvent)
        if errors:
            messagebox.showerror(
                "Solvent does not match the sample",
                "The solvent is subtracted bin for bin, so it has to be measured "
                "on the same grid as the sample.\n\n"
                + "\n".join(f"- {e}" for e in errors), parent=self.win)
            return
        if notes:
            messagebox.showwarning(
                "Solvent measured differently",
                "\n".join(f"- {n}" for n in notes)
                + "\n\nIt is loaded with the scale at 1 - adjust the scale to "
                  "make up for the difference.", parent=self.win)
        self._solvent = solvent
        self._sync_solvent_controls()   # enable the slider before moving it
        self._set_scale(1.0)
        self._update_overlay()

    def _clear_solvent(self):
        if self._solvent is None:
            return
        self._solvent = None
        self._set_scale(1.0)
        self._sync_solvent_controls()
        self._update_overlay()

    def _left_off(self):
        """The subtraction was switched off in the main window, and neither the
        solvent nor its scale was touched here: Apply is about the crop then,
        and must not switch it back on."""
        m = self.model
        return (m.solvent is not None and not m.solvent_sub
                and self._solvent is m.solvent and self._scale == m.solvent_scale)
