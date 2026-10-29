"""Paragon Unlimited - FE13 (Awakening) English voice lines.

Reads sound/14Iron_sound_US_EN.bcsar (the English dub; the _JP archive is never used) and
sound/stream/*EN.bcstm, decodes the requested line (DSP-ADPCM / IMA / PCM) to a .wav in a temp
folder and plays it. Which voice set a character uses comes from Asset Definitions
(an entry named after the PID has e.g. voice = CHROM -> SE_VOICE_CHROM_*).
"""
import array
import logging
import os
import struct
import sys
import tempfile
from typing import Dict, List, Optional

BCSAR_EN = "sound/14Iron_sound_US_EN.bcsar"


# ----------------------------------------------------------------------------- decoding


def _clamp(s):
    return -32768 if s < -32768 else (32767 if s > 32767 else s)


def decode_dsp(data, nsamples, coefs, h1=0, h2=0):
    out = []
    pos = 0
    n = len(data)
    while len(out) < nsamples and pos < n:
        ps = data[pos]
        scale = 1 << (ps & 0xF)
        idx = ps >> 4
        c1, c2 = coefs[idx * 2], coefs[idx * 2 + 1]
        for i in range(14):
            if len(out) >= nsamples:
                break
            bi = pos + 1 + i // 2
            if bi >= n:
                break
            b = data[bi]
            nib = (b >> 4) if not i & 1 else (b & 0xF)
            if nib >= 8:
                nib -= 16
            s = _clamp((((nib * scale) << 11) + 1024 + c1 * h1 + c2 * h2) >> 11)
            out.append(s)
            h2 = h1
            h1 = s
        pos += 8
    return out, h1, h2


_IMA_STEP = [7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97,
             107, 118, 130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796,
             876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871,
             5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385,
             24623, 27086, 29794, 32767]
_IMA_IDX = [-1, -1, -1, -1, 2, 4, 6, 8]


def decode_ima(data, nsamples, pred, idx):
    out = []
    for b in data:
        for nib in (b & 0xF, b >> 4):
            if len(out) >= nsamples:
                return out
            step = _IMA_STEP[idx]
            diff = step >> 3
            if nib & 1:
                diff += step >> 2
            if nib & 2:
                diff += step >> 1
            if nib & 4:
                diff += step
            pred = _clamp(pred - diff if nib & 8 else pred + diff)
            idx = min(88, max(0, idx + _IMA_IDX[nib & 7]))
            out.append(pred)
    return out


def _blocks(d, base=0x10):
    nb = struct.unpack_from("<H", d, base)[0]
    out = {}
    for i in range(nb):
        t, _, off, sz = struct.unpack_from("<HHII", d, base + 4 + 12 * i)
        out[t] = (off, sz)
    return out


def cwav_to_pcm(d):
    if d[:4] != b"CWAV":
        raise ValueError("not a CWAV")
    b = _blocks(d)
    info = b[0x7000][0] + 8
    data = b[0x7001][0] + 8
    enc = d[info]
    rate, _ls, le = struct.unpack_from("<III", d, info + 4)
    nch = struct.unpack_from("<I", d, info + 0x14)[0]
    chans = []
    for c in range(nch):
        off = struct.unpack_from("<i", d, info + 0x18 + 8 * c + 4)[0]
        ci = info + 0x14 + off
        soff = struct.unpack_from("<i", d, ci + 4)[0]
        aoff = struct.unpack_from("<i", d, ci + 12)[0]
        sdata = d[data + soff :]
        if enc == 2:
            coefs = struct.unpack_from("<16h", d, ci + aoff)
            chans.append(decode_dsp(sdata, le, coefs)[0])
        elif enc == 3:
            pred, idx = struct.unpack_from("<hB", d, ci + aoff)
            chans.append(decode_ima(sdata, le, pred, idx))
        elif enc == 1:
            chans.append(list(struct.unpack_from("<%dh" % le, sdata)))
        elif enc == 0:
            chans.append([(x - 256 if x > 127 else x) * 256 for x in sdata[:le]])
        else:
            raise ValueError(f"Unsupported CWAV encoding {enc}")
    return rate, chans


def cstm_to_pcm(d):
    if d[:4] != b"CSTM":
        raise ValueError("not a CSTM")
    b = _blocks(d)
    info = b[0x4000][0] + 8
    data = b[0x4002][0] + 8
    si = info + struct.unpack_from("<i", d, info + 4)[0]
    enc, _loop, nch = d[si], d[si + 1], d[si + 2]
    rate, _ls, _le, nblk, bsz, bsamp, lbsz, lbsamp, lbpad = struct.unpack_from("<9I", d, si + 4)
    soff = struct.unpack_from("<i", d, si + 0x34)[0]
    if enc != 2:
        raise ValueError(f"Unsupported stream encoding {enc}")
    cit = info + struct.unpack_from("<i", d, info + 0x14)[0]
    coefs = []
    for c in range(nch):
        co = cit + struct.unpack_from("<i", d, cit + 4 + 8 * c + 4)[0]
        ao = co + struct.unpack_from("<i", d, co + 4)[0]
        coefs.append(struct.unpack_from("<16h", d, ao))
    chans = [[] for _ in range(nch)]
    hist = [(0, 0)] * nch
    p = data + soff
    for blk in range(nblk):
        last = blk == nblk - 1
        size = lbsz if last else bsz
        pad = lbpad if last else bsz
        ns = lbsamp if last else bsamp
        for c in range(nch):
            s, h1, h2 = decode_dsp(d[p : p + size], ns, coefs[c], *hist[c])
            hist[c] = (h1, h2)
            chans[c].extend(s)
            p += pad
    return rate, chans


def wav_bytes(rate, chans):
    n = min(len(c) for c in chans)
    nch = len(chans)
    a = array.array("h", bytes(2 * n * nch))
    for c in range(nch):
        a[c::nch] = array.array("h", chans[c][:n])
    pcm = a.tobytes()
    return (
        b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, nch, rate, rate * 2 * nch, 2 * nch, 16)
        + b"data" + struct.pack("<I", len(pcm)) + pcm
    )


# ----------------------------------------------------------------------------- BCSAR


class _Csar:
    def __init__(self, d: bytes):
        if d[:4] != b"CSAR":
            raise ValueError("not a BCSAR")
        self.d = d
        self.blocks = _blocks(d)
        # strings
        base = self.blocks[0x2000][0] + 8
        tb = base + self._ref(base)[1]
        self.strings = []
        for i in range(self._u32(tb)):
            _t, _, eo, es = struct.unpack_from("<HHII", d, tb + 4 + 12 * i)
            self.strings.append(d[tb + eo : tb + eo + es - 1].decode("ascii", "replace"))
        ib = self.blocks[0x2001][0] + 8
        self.inforefs = {}
        for i in range(8):
            t, off = self._ref(ib + 8 * i)
            self.inforefs[t] = ib + off
        self.file_base = self.blocks[0x2002][0] + 8

    def _u32(self, o):
        return struct.unpack_from("<I", self.d, o)[0]

    def _ref(self, o, d=None):
        t, _, off = struct.unpack_from("<HHi", d if d is not None else self.d, o)
        return t, off

    def _table(self, o):
        return [self._ref(o + 4 + 8 * i) for i in range(self._u32(o))]

    def sounds(self) -> Dict[str, tuple]:
        """name -> (detail type, file id, detail offset)."""
        tb = self.inforefs[0x2100]
        out = {}
        for _t, off in self._table(tb):
            o = tb + off
            file_id = self._u32(o)
            dt, doff = self._ref(o + 0xC)
            flags = self._u32(o + 0x14)
            if flags & 1:
                name = self.strings[self._u32(o + 0x18)]
                out[name] = (dt, file_id, o + doff)
        return out

    def file(self, file_id):
        """('int', bytes) or ('ext', path)."""
        tb = self.inforefs[0x2106]
        _t, off = self._table(tb)[file_id]
        o = tb + off
        lt, loff = self._ref(o)
        p = o + loff
        if lt == 0x220C:
            _ft, foff = self._ref(p)
            size = self._u32(p + 8)
            return "int", self.d[self.file_base + foff : self.file_base + foff + size]
        end = self.d.index(b"\0", p)
        return "ext", self.d[p:end].decode("ascii", "replace")

    def wave_archive_file(self, index):
        tb = self.inforefs[0x2103]
        _t, off = self._table(tb)[index]
        return self._u32(tb + off)


def _cwar_wave(cwar, index):
    b = _blocks(cwar)
    info = b[0x6800][0]
    data = b[0x6801][0]
    _t, _, off, size = struct.unpack_from("<HHiI", cwar, info + 12 + 12 * index)
    return cwar[data + 8 + off : data + 8 + off + size]


def _wsd_wave(wsd, index):
    """(wave archive index, wave index) for wave sound #index in a CWSD."""
    b = _blocks(wsd)
    ib = b[0x6800][0] + 8
    _t1, o1 = struct.unpack_from("<HHi", wsd, ib)[0::2]
    _t2, o2 = struct.unpack_from("<HHi", wsd, ib + 8)[0::2]
    wid = ib + o1
    ids = [struct.unpack_from("<II", wsd, wid + 4 + 8 * i) for i in range(struct.unpack_from("<I", wsd, wid)[0])]
    tb = ib + o2
    ws = tb + struct.unpack_from("<i", wsd, tb + 4 + 8 * index + 4)[0]
    nt = ws + struct.unpack_from("<i", wsd, ws + 16 + 4)[0]
    no = nt + struct.unpack_from("<i", wsd, nt + 4 + 4)[0]
    wave_id_index = struct.unpack_from("<I", wsd, no)[0]
    item, wave = ids[wave_id_index]
    return item & 0xFFFFFF, wave


# ----------------------------------------------------------------------------- service


class FE13Voices:
    def __init__(self, gd):
        self.gd = gd
        self._csar = None
        self._sounds = None
        self._wars = {}
        self._cache_dir = os.path.join(tempfile.gettempdir(), "ParagonUnlimitedVoices")
        self.error = None

    def _load(self):
        if self._sounds is not None:
            return
        try:
            self._csar = _Csar(bytes(self.gd.read_file(BCSAR_EN)))
            self._sounds = {k: v for k, v in self._csar.sounds().items() if k.startswith("SE_VOICE_")}
        except Exception as e:
            logging.exception("Could not read the English voice archive.")
            self.error = str(e)
            self._sounds = {}

    def all_voices(self) -> List[str]:
        self._load()
        return sorted(self._sounds)

    def voice_codes_for_pid(self, pid: str) -> List[str]:
        codes = []
        try:
            node = self.gd.node("asset_definitions")
            for e in self.gd.items(node.rid, "specs") or []:
                if self.gd.string(e, "name") == pid:
                    v = self.gd.string(e, "voice")
                    if v and v not in codes:
                        codes.append(v)
        except Exception:
            logging.exception("Could not read voice codes from Asset Definitions.")
        return codes

    def voices_for_codes(self, codes) -> List[str]:
        self._load()
        import re

        out = []
        for code in codes:
            # '#' / '?' in Asset Definitions are wildcards (avatar voice sets: PLAYER_M1..M3).
            pat = re.compile("^SE_VOICE_" + re.escape(code).replace("\\#", r"\d+").replace("\\?", ".") + "_")
            out.extend(n for n in self._sounds if pat.match(n) and n not in out)
        return sorted(out, key=_natural)

    def voices_for_pid(self, pid: str) -> List[str]:
        return self.voices_for_codes(self.voice_codes_for_pid(pid))

    def wav_path(self, name: str) -> str:
        self._load()
        os.makedirs(self._cache_dir, exist_ok=True)
        path = os.path.join(self._cache_dir, name + ".wav")
        if os.path.exists(path):
            return path
        dt, file_id, detail = self._sounds[name]
        c = self._csar
        if dt == 0x2201:  # stream
            _k, ext = c.file(file_id)
            raw = bytes(self.gd.read_file("sound/" + ext))
            rate, chans = cstm_to_pcm(raw)
        elif dt == 0x2202:  # wave sound
            index = struct.unpack_from("<I", c.d, detail)[0]
            _k, wsd = c.file(file_id)
            war_index, wave = _wsd_wave(wsd, index)
            if war_index not in self._wars:
                _k, self._wars[war_index] = c.file(c.wave_archive_file(war_index))
            rate, chans = cwav_to_pcm(_cwar_wave(self._wars[war_index], wave))
        else:
            raise ValueError(f"{name} is not a playable voice line")
        with open(path, "wb") as f:
            f.write(wav_bytes(rate, chans))
        return path

    def has(self, name: str) -> bool:
        self._load()
        return name in self._sounds

    def duration(self, name: str) -> float:
        """Length of a voice line in seconds (0 if unknown)."""
        import wave

        try:
            with wave.open(self.wav_path(name), "rb") as w:
                return w.getnframes() / float(w.getframerate() or 1)
        except Exception:
            return 0.0

    def play(self, name: str):
        path = self.wav_path(name)
        if sys.platform == "win32":
            import winsound

            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        else:
            from PySide6.QtMultimedia import QSoundEffect
            from PySide6.QtCore import QUrl

            self._effect = QSoundEffect()
            self._effect.setSource(QUrl.fromLocalFile(path))
            self._effect.play()
        return path

    @staticmethod
    def stop():
        if sys.platform == "win32":
            import winsound

            winsound.PlaySound(None, 0)


def _natural(s):
    import re

    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]
