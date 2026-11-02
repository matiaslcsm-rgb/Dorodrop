import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..paths import DATA_DIR

router = APIRouter(prefix="/api/notes", tags=["notes"])

NOTES_FILE = DATA_DIR / "notes.json"


class NoteIn(BaseModel):
    author: str = Field(default="", max_length=60)
    text: str = Field(min_length=1, max_length=2000)


def _load() -> list[dict]:
    if not NOTES_FILE.exists():
        return []
    try:
        return json.loads(NOTES_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save(notes: list[dict]) -> None:
    NOTES_FILE.write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")


@router.get("")
def list_notes():
    notes = _load()
    return sorted(notes, key=lambda n: n["created_at"], reverse=True)


@router.post("")
def add_note(payload: NoteIn):
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="La nota no puede estar vacía")

    note = {
        "id": uuid.uuid4().hex,
        "author": payload.author.strip() or "Anónimo",
        "text": text,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    notes = _load()
    notes.append(note)
    _save(notes)
    return note


@router.delete("/{note_id}")
def delete_note(note_id: str):
    notes = _load()
    remaining = [n for n in notes if n["id"] != note_id]
    if len(remaining) == len(notes):
        raise HTTPException(status_code=404, detail="Nota no encontrada")
    _save(remaining)
    return {"deleted": note_id}
