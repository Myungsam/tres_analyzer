"""Writing OriginLab .opju worksheets."""


# ==========================================================================
# 2b. Origin (.opju) writing
# ==========================================================================
# These four helpers mirror TRES_data_processing/csv_to_opju.py so a project
# written here matches the ones written there: a workbook whose short name is
# "Book1", one worksheet (tab) per dataset, named after the dataset. They only
# touch the `op` (originpro) / `ws` (worksheet) objects, never import anything,
# so importing this module never pulls Origin in - that happens lazily, only
# when the user actually asks for a .opju, inside TRESViewer._write_opju.
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


def _origin_fill_tres(ws, df, tab_name):
    """TRES map into a worksheet: col A = time (ps), one column per wavelength."""
    ncols = df.shape[1]
    cols = list(df.columns)
    ws.clear()
    ws.from_df(df)
    ws.cols = ncols
    ws.set_label(0, "time", "L"); ws.set_label(0, "ps", "U"); ws.set_label(0, "", "C")
    for j in range(1, ncols):
        ws.set_label(j, "", "L")
        ws.set_label(j, "", "U")
        ws.set_label(j, str(cols[j]).strip(), "C")   # wavelength kept as a comment


def _origin_fill_steady(ws, df, tab_name):
    """Steady-state spectrum into a worksheet: Wavelength / Counts / Nor. (3 cols)."""
    data = df.iloc[:, :3].reset_index(drop=True)
    ws.clear()
    ws.from_df(data)
    ws.cols = 3
    ws.set_label(0, "Wavelength", "L"); ws.set_label(0, "nm", "U");    ws.set_label(0, "", "C")
    ws.set_label(1, "Counts", "L");     ws.set_label(1, "counts", "U"); ws.set_label(1, tab_name, "C")
    ws.set_label(2, "Nor.", "L");       ws.set_label(2, "a. u.", "U"); ws.set_label(2, tab_name, "C")


def _origin_fill_table(ws, df, col_specs):
    """Generic: put df into ws, then label each column (Long name, Units, Comment).

    col_specs is a list of (long_name, unit, comment) aligned with df.columns.
    Used by the Kinetics / Global-analysis exports, whose tables do not fit the
    fixed TRES-map / steady-state shapes above.
    """
    ws.clear()
    ws.from_df(df)
    ws.cols = df.shape[1]
    for j, (lname, unit, comment) in enumerate(col_specs):
        ws.set_label(j, lname, "L")
        ws.set_label(j, unit, "U")
        ws.set_label(j, comment, "C")
