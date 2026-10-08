"""Writing OriginLab .opju worksheets."""


# ==========================================================================
# 2b. Origin (.opju) writing
# ==========================================================================
# These helpers mirror TRES_data_processing/csv_to_opju.py so a project
# written here matches the ones written there: a workbook whose short name is
# "Book1", one worksheet (tab) per dataset, named after the dataset. They only
# touch the `op` (originpro) / `ws` (worksheet) objects, so importing this
# module never pulls Origin in - that happens lazily, only when the user
# actually asks for a .opju, inside TRESViewer._opju_write_tabs.
#
# The numbers go in column by column with ws.from_list(). Up to 1.5 they went
# through a pandas DataFrame and ws.from_df(), and pandas was in the program
# (about 1,200 files of the .exe) for nothing else.
def _origin_book1(op):
    """The workbook with short name 'Book1', created if the project has none."""
    wb = op.find_book("w", "Book1")
    if wb is not None:
        return wb
    wb = op.new_book("w")
    try:
        if wb.name != "Book1":
            wb.name = "Book1"
    except Exception:
        pass
    return wb


def _origin_sheet(wb, sheet_name, fresh=False):
    """Find the worksheet called sheet_name in wb, or add it. -> (sheet, created).

    ``fresh`` says the project was created just now: only then is its single
    "Sheet1" known to be empty and taken over. In a project that already
    existed a lone "Sheet..." may hold the user's data and is left alone.
    """
    for sh in wb:
        if sh.name == sheet_name:
            return sh, False                       # exists -> overwrite target
    sheets = list(wb)
    # a brand-new project's single empty "Sheet1" is renamed rather than kept
    if fresh and len(sheets) == 1 and sheets[0].name.lower().startswith("sheet"):
        try:
            sheets[0].name = sheet_name
            return sheets[0], True
        except Exception:
            pass
    return wb.add_sheet(sheet_name), True


def _origin_put(ws, columns):
    """Fill the sheet with ``columns`` - 1-D arrays of numbers, one per sheet
    column - and leave it with exactly that many columns.

    Each is made a column of doubles first, as from_df() made a float column
    (a new column is "Text & Numeric"). That goes through the sheet's inner
    object and is best effort: the data are numbers either way.
    """
    ws.clear()
    for j, values in enumerate(columns):
        try:
            from originpro.config import po
            ws.obj[j].SetDataFormat(po.DF_DOUBLE)
        except Exception:               # noqa: BLE001 - see the docstring
            pass
        ws.from_list(j, [float(v) for v in values])
    ws.cols = len(columns)


def _origin_fill_tres(ws, times, Z, wls):
    """TRES map into a worksheet: col A = time (ps), one column per wavelength.
    Z is (time, wavelength)."""
    _origin_put(ws, [times] + [Z[:, j] for j in range(Z.shape[1])])
    ws.set_label(0, "time", "L"); ws.set_label(0, "ps", "U"); ws.set_label(0, "", "C")
    for j, wl in enumerate(wls, start=1):
        ws.set_label(j, "", "L")
        ws.set_label(j, "", "U")
        ws.set_label(j, f"{wl:g}", "C")              # wavelength kept as a comment


def _origin_fill_steady(ws, wls, counts, norm, tab_name):
    """Steady-state spectrum into a worksheet: Wavelength / Counts / Nor. (3 cols)."""
    _origin_put(ws, [wls, counts, norm])
    ws.set_label(0, "Wavelength", "L"); ws.set_label(0, "nm", "U");    ws.set_label(0, "", "C")
    ws.set_label(1, "Counts", "L");     ws.set_label(1, "counts", "U"); ws.set_label(1, tab_name, "C")
    ws.set_label(2, "Nor.", "L");       ws.set_label(2, "a. u.", "U"); ws.set_label(2, tab_name, "C")


def _origin_fill_table(ws, columns, col_specs):
    """Generic: put the columns into ws, then label each (Long name, Units,
    Comment).

    col_specs is a list of (long_name, unit, comment) aligned with columns.
    Used by the Kinetics / Global-analysis exports, whose tables do not fit the
    fixed TRES-map / steady-state shapes above.
    """
    _origin_put(ws, columns)
    for j, (lname, unit, comment) in enumerate(col_specs):
        ws.set_label(j, lname, "L")
        ws.set_label(j, unit, "U")
        ws.set_label(j, comment, "C")
