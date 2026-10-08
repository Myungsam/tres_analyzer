"""PicoQuant .phu (PQHISTO) reader."""
import struct

import numpy as np


# ==========================================================================
# 1. PicoQuant .phu (PQHISTO) reader
# ==========================================================================
TY_EMPTY8       = 0xFFFF0008
TY_BOOL8        = 0x00000008
TY_INT8         = 0x10000008
TY_BITSET64     = 0x11000008
TY_COLOR8       = 0x12000008
TY_FLOAT8       = 0x20000008
TY_TDATETIME    = 0x21000008
TY_FLOAT8ARRAY  = 0x2001FFFF
TY_ANSISTRING   = 0x4001FFFF
TY_WIDESTRING   = 0x4002FFFF
TY_BINARYBLOB   = 0xFFFFFFFF


def read_phu(path):
    """Parse a .phu file into a dict of metadata plus a (ncurves, nbins) array."""
    with open(path, "rb") as fh:
        data = fh.read()

    magic = data[:8].split(b"\x00")[0].decode("ascii", "replace")
    if magic != "PQHISTO":
        raise ValueError(f'Not a PicoQuant histogram file (magic "{magic}").')
    version = data[8:16].split(b"\x00")[0].decode("ascii", "replace")

    def payload(ident, raw, pos):
        """Length of the data that follows a tag, checked against the file: a
        negative length would step back onto the same tag for ever."""
        n = struct.unpack("<q", raw)[0]
        if n < 0 or pos + n > len(data):
            raise ValueError(f'Corrupt header: tag "{ident}" claims {n} bytes '
                             f"of data, the file has {len(data) - pos} left.")
        return n

    pos, tags = 16, []
    while pos + 48 <= len(data):
        ident = data[pos:pos + 32].split(b"\x00")[0].decode("ascii", "replace")
        idx = struct.unpack_from("<i", data, pos + 32)[0]
        typ = struct.unpack_from("<I", data, pos + 36)[0]
        raw = data[pos + 40:pos + 48]
        pos += 48

        if typ in (TY_INT8, TY_BITSET64, TY_COLOR8):
            val = struct.unpack("<q", raw)[0]
        elif typ == TY_BOOL8:
            val = bool(struct.unpack("<q", raw)[0])
        elif typ in (TY_FLOAT8, TY_TDATETIME):
            val = struct.unpack("<d", raw)[0]
        elif typ == TY_EMPTY8:
            val = None
        elif typ == TY_FLOAT8ARRAY:
            n = payload(ident, raw, pos)
            val = np.frombuffer(data[pos:pos + n], "<f8")
            pos += n
        elif typ == TY_ANSISTRING:
            n = payload(ident, raw, pos)
            val = data[pos:pos + n].split(b"\x00")[0].decode("ascii", "replace")
            pos += n
        elif typ == TY_WIDESTRING:
            n = payload(ident, raw, pos)
            val = data[pos:pos + n].split(b"\x00\x00")[0].decode("utf-16-le", "replace")
            pos += n
        elif typ == TY_BINARYBLOB:
            n = payload(ident, raw, pos)
            val = None
            pos += n
        else:
            val = None

        tags.append((ident, idx, val))
        if ident == "Header_End":
            break
    else:
        raise ValueError("Corrupt header: the file ends before the Header_End tag.")

    def one(name):
        for ident, _, val in tags:
            if ident == name:
                return val
        return None

    def many(name):
        return {i: v for ident, i, v in tags if ident == name}

    def need(name, i):
        vals = many(name)
        if vals.get(i) is None:
            raise ValueError(f"Missing header field {name}[{i}].")
        return vals[i]

    def whole(value, what):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"Bad header: the {what} is {value!r}, not a whole number.")
        return value

    ncurves = one("HistoResult_NumberOfCurves")
    if not ncurves:
        raise ValueError("No histogram curves found in this file.")
    if whole(ncurves, "curve count") < 0:
        raise ValueError(f"Bad header: the curve count is {ncurves}.")

    nbins = whole(need("HistResDscr_HistogramBins", 0), "bin count")
    if nbins <= 0:
        raise ValueError(f"Bad header: {nbins} time bins per curve.")
    res_s = need("HistResDscr_MDescResolution", 0)
    if not isinstance(res_s, float) or not np.isfinite(res_s) or res_s <= 0:
        raise ValueError(f"Bad header: the time resolution is {res_s!r} s.")
    res_ps = res_s * 1e12
    # one time axis for the whole map: every curve must have curve 0's
    all_bins, all_res = many("HistResDscr_HistogramBins"), many("HistResDscr_MDescResolution")
    for i in range(1, ncurves):
        bins_i = all_bins.get(i, nbins)
        if bins_i != nbins:
            raise ValueError(f"Curve {i} has {bins_i} bins, curve 0 has {nbins}: "
                             "curves with different time axes are not supported.")
        res_i = all_res.get(i, res_s)
        if not isinstance(res_i, float) or abs(res_i - res_s) > 1e-9 * res_s:
            raise ValueError(
                f"Curve {i} has a time resolution of {res_i!r} s, curve 0 "
                f"{res_s!r} s: curves with different time axes are not supported.")
    wl_map = many("ParValue0")
    integrals = many("HistResDscr_IntegralCount")

    counts = np.zeros((ncurves, nbins), dtype=np.uint32)
    offsets = many("HistResDscr_DataOffset")
    for i in range(ncurves):
        if offsets.get(i) is None:
            raise ValueError(f"Missing header field HistResDscr_DataOffset[{i}].")
        off = whole(offsets[i], f"data offset of curve {i}")
        if off < 0 or off + 4 * nbins > len(data):
            raise ValueError(f"Curve {i} data lies outside the file.")
        counts[i] = np.frombuffer(data[off:off + 4 * nbins], dtype="<u4")

    wls = np.array([wl_map.get(i, i) for i in range(ncurves)], dtype=float)

    return dict(
        path=path, version=version, ncurves=ncurves, nbins=nbins,
        res_ps=res_ps, counts=counts, wls=wls,
        integrals=np.array([integrals.get(i, 0) for i in range(ncurves)]),
        param_name=one("MeasDesc_Param_Name") or "Index",
        param_unit=one("MeasDesc_Param_Unit") or "",
        hw_type=one("HW_Type") or "", serial=one("HW_SerialNo") or "",
        acq_ms=one("MeasDesc_AcquisitionTime"),
        sync_rate=many("HistResDscr_SyncRate").get(0),
        comment=one("File_Comment") or "",
    )
