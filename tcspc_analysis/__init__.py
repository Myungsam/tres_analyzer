#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PicoHarp 300 post-processing - two tools in one window, one per file format

A tab bar at the top switches between:

    PHU  -  TRES : time-resolved emission spectroscopy from a .phu histogram
                   (the viewer described below)
    PTU  -  FLIM : fluorescence-lifetime imaging from a .ptu TTTR record
                   (intensity image + lifetime map + per-pixel decay)

The two tabs are independent - each opens its own file and does its own thing -
so this file simply hosts both under a single window and a shared dark theme.
The rest of this docstring describes the PHU/TRES tab.

TRES Viewer - PicoQuant PicoHarp 300 (.phu) time-resolved emission spectroscopy

Layout
    [ file path + Open ]
    [ controls                                     ]
    [ decay histogram      | TRES 2D map | color ]
    [                      | spectral ribbon     ]
    [ steady-state spectrum| spectrum            ]

The first curve can be treated as an IRF-only measurement: with the "First
curve is IRF" checkbox on, it is kept out of the map and only used to put t0
on its peak. A .phu header carries no IRF flag and an IRF cannot be told apart
from the wavelength grid (it often sits on it), so this is a manual choice.
When the checkbox is on, the IRF is the grey trace in the left decay panel,
scaled so its peak matches the map's brightest count.

The bottom-left panel is the steady-state fluorescence spectrum: every time
bin of the displayed record summed together, i.e. what a cw spectrometer would
have recorded. The bottom-right panel is still the spectrum at the cursor
delay only.

OFFSET shifts the whole wavelength axis by the number of nm in the box, for
spectrograph calibration. It is absolute - always measured from the values
stored in the file - so pressing the button twice does not shift twice. The
box starts at -50 nm (the usual calibration for this setup); type 0 for the
raw wavelengths in the file.

Two preprocessing tools live under "PREP", each in its own pop-up:
    Crop    keep only a rectangular (wavelength, time) window. The whole map is
            drawn once as a preview; drag two corners or type the bounds and the
            kept box updates live. Apply re-slices the pristine file, so the
            crop can be widened again (or Reset to full) without reloading. Its
            upper time edge is the same value as the main TIME SPAN box.
            The same window subtracts a solvent: "Load solvent..." takes a
            pure-solvent .phu measured on the same grid (same curves,
            wavelengths, resolution and bin count - anything else is refused),
            and SCALE (slider 0-2, or type a larger value) sets how much of it
            is taken off, bin for bin: sample - scale x solvent. The heatmap and
            the steady-state panel under it (sample, scaled solvent, subtracted)
            follow the scale as a preview; Apply hands it to the main window,
            where the "Subtract solvent" checkbox switches it on and off. While
            it is on, negatives left after the background are clipped to 0 -
            the share of clipped bins is shown, since clipping lifts weak
            signals. Opening another sample drops the solvent.
            Moving the pointer over the heatmap draws the spectrum of that one
            time bin in bold over the (faded) steady-state lines, on the
            right-hand scale: sample, scaled solvent and their difference, in
            raw counts and unclipped. Double-click pins the time, double-click
            again releases it; single clicks still set the crop box.
            To look closer, the wheel zooms the heatmap about the pointer (Ctrl:
            time only, Shift: wavelength only), a right-button drag moves it
            and "Fit" shows all of it again. "Log color" and "Log time" switch
            the colour and the time axis between linear and log; "Auto color"
            takes the colour range from the part in view instead of the whole
            map. These only change the picture, not the crop, and are
            forgotten when the window closes.
    Mask λ  set one or more wavelength bands to NaN so they drop out of the map,
            the summed spectra and the fits, shown as a hatched gap. Click the
            preview to pick From / To, Add region, and Remove / Clear from the
            list. Masks apply inside the current crop.
Both feed the whole pipeline through the model, so the map, the spectra, the
CSV / .opju export and the Kinetics / Global-analysis fits all follow along.
Opening another file closes all four pop-up windows (Crop, Mask, Kinetics,
Global analysis): each shows the file it was opened on, so export a fit you
want to keep first.

If the window stops answering for more than 5 seconds, or a step fails
without a message, where the program was at that moment is noted in
TCSPC_analysis_freeze.log - next to the program when it is run from source,
in Documents\\TCSPC_analysis when it is the .exe - code locations and the name
of the open file, no measured data. Slow but healthy steps (starting Origin
for an .opju export) show up there too.

Move the pointer over the map to update the decay (at the cursor wavelength)
and the spectrum (at the cursor delay) in real time. Click to pin a position.

"Save map image" writes the 2D map on its own - none of the surrounding
panels - as a picture (PNG/PDF/SVG). It carries the colormap and contrast on
screen and covers whatever the map is showing, so zoom in first to save a
region.

"Export data" writes the TRES map and the steady-state spectrum together -
never one without the other. Tick "CSV", ".opju", or both:
    CSV    two files next to each other, {name}_TRESmap.csv (a matrix of one
           row per delay, one column per wavelength) and {name}_steadystate.csv
           (one row per wavelength: summed counts and the same normalised).
    .opju  an Origin project, by default in the project's Data\\ folder
           (Documents\\TCSPC_analysis\\Data for the .exe). If one
           already exists there you can pick it and the data is added to it as
           two worksheets; otherwise a new project is created. Needs Origin +
           originpro + pywin32 installed. The map and spectrum are written in
           full - the whole record, not the current zoom.

Analysis (top bar, each opens its own window)
    Kinetics...        fit the decay at one wavelength (or an averaged band) to
                       a sum of IRF-convolved exponentials - number of
                       components, per-component fixed/stretched flags, IRF t0
                       and FWHM, and a fit window; shows data + fit + residual.
                       Runs in a background thread with a Stop button.
    Global analysis... one VARPRO fit of the whole map to a shared set of
                       exponentials; shows the data / fit / residual maps, the
                       DADS and (sequential) EADS spectra, and the kinetics at
                       a chosen wavelength. Runs in a background thread with a
                       Stop button. Both tools need SciPy (pip install scipy).
    Each window's "Export results" button obeys the same "CSV" / ".opju"
    tickboxes as "Export data" above: CSV writes {stem}_kinetics.csv, or
    {stem}_DADS.csv + {stem}_EADS.csv; .opju adds the matching worksheet tabs
    to Book1 of the chosen Origin project - the same one holding the TRES map.

Mouse
    map       drag        zoom into the rectangle
              click       pin / release the cursor
              right-click reset the zoom
    colorbar  drag        set the contrast range
              right-click auto contrast

A background spectrum - the mean over a time window, by default the first
0-100 ps of the record - is subtracted from every time bin. Untick "Subtract
background" or type your own window to change it. The window is quoted on the
displayed time axis and is re-quoted automatically when t0 moves, so it always
keeps covering the same real delays.

Usage
    python -m tcspc_analysis [file.phu]

An optional .phu path is loaded straight into the PHU/TRES tab; the PTU/FLIM
tab is opened from its own "Open file..." button.

Requires: numpy, matplotlib, tkinter (tkinter ships with most CPython builds;
on Debian/Ubuntu install it with `sudo apt install python3-tk`)
Optional: pandas + originpro + pywin32 for the TRES ".opju" export;
          tensorflow (2.10 on Windows/CUDA 11.2) for FLIM GPU acceleration -
          without it the FLIM tab still runs on the CPU.
"""

import matplotlib
matplotlib.use("TkAgg")
