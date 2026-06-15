"""Bridge to the VoiceInk dictation store: list the most recent dictations.

VoiceInk keeps transcripts in a SwiftData (sqlite) store next to the Recordings
dir. Opening a live WAL sqlite even read-only can touch its -shm file, and the
app's data dir must stay untouched, so the store (and its -wal/-shm) is copied
into a temp dir first and only the copy is read. The Recordings dir is read
only as well: prosodi never writes next to the original wavs.
"""

import shutil
import sqlite3
import tempfile
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

VOICEINK_STORE = (Path.home()
                  / "Library/Application Support/com.prakashjoshipax.VoiceInk/default.store")

# Cocoa timestamps count seconds from 2001-01-01; unix from 1970-01-01.
COCOA_EPOCH_OFFSET = 978307200


@dataclass
class Dictation:
    wav: Path | None   # where VoiceInk says the audio is (may have been purged)
    text: str          # the stored transcript, whitespace-flattened
    timestamp: float   # unix epoch seconds


def latest_dictations(store: Path, n: int) -> list[Dictation]:
    """Return the n most recent transcriptions, newest first.

    Raises sqlite3.Error or OSError when the store cannot be copied or read.
    """
    with tempfile.TemporaryDirectory() as td:
        for suffix in ("", "-wal", "-shm"):
            src = Path(str(store) + suffix)
            if src.exists():
                shutil.copy2(src, Path(td) / src.name)
        db = sqlite3.connect(Path(td) / store.name)
        try:
            rows = db.execute(
                "SELECT ZAUDIOFILEURL, ZTEXT, ZTIMESTAMP FROM ZTRANSCRIPTION "
                "WHERE ZTEXT IS NOT NULL ORDER BY ZTIMESTAMP DESC LIMIT ?",
                (n,)).fetchall()
        finally:
            db.close()

    out = []
    for url, text, ts in rows:
        wav = (Path(urllib.parse.unquote(urllib.parse.urlparse(url).path))
               if url else None)
        out.append(Dictation(wav=wav, text=" ".join(text.split()),
                             timestamp=(ts or 0) + COCOA_EPOCH_OFFSET))
    return out
