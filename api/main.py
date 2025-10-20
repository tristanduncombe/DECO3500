from typing import Optional
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from src.password import build_fingerprint, compare_fingerprints, extract_body_and_hand_positions
from sqlmodel import Field, SQLModel, Session, create_engine
from sqlalchemy.exc import OperationalError
import time
from fastapi.encoders import jsonable_encoder
import shutil
import os
import base64
from functools import lru_cache
from sqlalchemy import text, Column, String
from sqlalchemy.dialects.postgresql import JSONB
from uuid import uuid4
import logging
import tempfile
from datetime import datetime, timedelta, timezone
import threading
from pydantic import BaseModel

UNLOCK_THRESHOLD = 0.8
UNLOCK_WINDOW_SECONDS = 30

app = FastAPI()

logger = logging.getLogger("api")
logging.basicConfig(level=logging.INFO)

# CORS setup: restrict to specific origins by default; override via CORS_ORIGINS env (comma separated)
DEFAULT_CORS_ORIGINS = [
    "http://103.249.239.235",
    "https://103.249.239.235",
]

_cors_origins = os.getenv("CORS_ORIGINS")
if _cors_origins and _cors_origins.strip():
    if _cors_origins.strip() == "*":
        origins = ["*"]
    else:
        origins = [o.strip() for o in _cors_origins.split(',') if o.strip()]
else:
    origins = DEFAULT_CORS_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@lru_cache
def get_database_url() -> str:
    return os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5431/deco")

DATABASE_URL = get_database_url()
engine = None

_lock = threading.Lock()
_lock_state: dict[str, Optional[datetime]] = {"expires_at": None}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _set_unlocked_for(duration_seconds: int) -> datetime:
    unlock_until = _now_utc() + timedelta(seconds=duration_seconds)
    with _lock:
        _lock_state["expires_at"] = unlock_until
    return unlock_until


def _current_lock_state() -> dict:
    with _lock:
        expires_at = _lock_state.get("expires_at")
    if expires_at and expires_at <= _now_utc():
        with _lock:
            _lock_state["expires_at"] = None
        expires_at = None
    locked = expires_at is None
    return {
        "locked": locked,
        "unlock_expires_at": expires_at.isoformat() if expires_at else None,
    }

def init_engine_with_retry(max_attempts: int = 20, delay: float = 1.5):
    global engine
    attempt = 0
    while attempt < max_attempts:
        try:
            engine = create_engine(DATABASE_URL, echo=True)
            # test a connection
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except OperationalError:
            attempt += 1
            time.sleep(delay)
    raise RuntimeError(f"Could not connect to database after {max_attempts} attempts")

init_engine_with_retry()

BASE_DIR = os.path.dirname(__file__)
IMAGES_DIR = os.path.join(BASE_DIR, "images")
os.makedirs(IMAGES_DIR, exist_ok=True)


def _remove_file_if_exists(path: Optional[str]) -> None:
    if not path:
        return
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        logger.warning("Failed to remove file %s", path, exc_info=True)

class InventoryItem(SQLModel):
    id: Optional[int] = Field(default=None, primary_key=True)
    item: str
    person_image: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    password_image: Optional[dict] = Field(default=None, sa_column=Column(JSONB, nullable=True))

    class Config:
        table = True


class InventoryItemResponse(BaseModel):
    id: Optional[int]
    item: str
    person_image: Optional[str]
    password_image: Optional[dict]
    unlock_expires_at: Optional[str] = None

SQLModel.metadata.create_all(engine)

@app.post("/inventory/items", response_model=InventoryItemResponse)
def create_item(
    item: str = Form(...),
    person_image: UploadFile = File(...),
    password_image_1: UploadFile = File(...),
    password_image_2: UploadFile = File(...),
    password_image_3: UploadFile = File(...),
):
    # validate inputs
    if (
        person_image.filename is None
        or password_image_1.filename is None
        or password_image_2.filename is None
        or password_image_3.filename is None
    ):
        raise HTTPException(status_code=400, detail="Image filename missing")

    # save files using UUID filenames (preserve extension)
    def _save_upload(upload: UploadFile) -> str:
        ext = os.path.splitext(upload.filename or '')[1] or '.jpg'
        fname = f"{uuid4().hex}{ext}"
        path = os.path.join(IMAGES_DIR, fname)
        with open(path, 'wb') as f:
            shutil.copyfileobj(upload.file, f)
        return fname

    person_fname = _save_upload(person_image)

    # For password images, use temporary files (do not persist filenames)
    def _save_temp_upload(upload: UploadFile) -> str:
        ext = os.path.splitext(upload.filename or '')[1] or '.jpg'
        tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False, dir=IMAGES_DIR)
        with tmp as f:
            shutil.copyfileobj(upload.file, f)
        return tmp.name

    pwd1 = _save_temp_upload(password_image_1)
    pwd2 = _save_temp_upload(password_image_2)
    pwd3 = _save_temp_upload(password_image_3)

    # extract positions and fingerprints for each password image
    pos1 = extract_body_and_hand_positions(pwd1)
    pos2 = extract_body_and_hand_positions(pwd2)
    pos3 = extract_body_and_hand_positions(pwd3)

    fp1 = build_fingerprint(pos1)
    fp2 = build_fingerprint(pos2)
    fp3 = build_fingerprint(pos3)

    # validate fingerprints: if extraction failed (empty fingerprint), reject the upload
    if not fp1 or not fp2 or not fp3:
        # log details for debugging
        logger.warning("Fingerprint extraction failed for one or more password images: sizes=%s,%s,%s", len(fp1), len(fp2), len(fp3))
        logger.debug("pos1=%s", pos1)
        logger.debug("pos2=%s", pos2)
        logger.debug("pos3=%s", pos3)
        raise HTTPException(status_code=400, detail="Could not detect pose/hand landmarks in one or more password images")

    db_item = InventoryItem(
        item=item,
        person_image=person_fname,
        password_image={
            "fingerprints": [fp1, fp2, fp3],
        },
    )

    with Session(engine) as session:
        session.add(db_item)
        session.commit()
        session.refresh(db_item)
    # cleanup temporary password images immediately (never persist)
    try:
        os.remove(pwd1)
    except Exception:
        pass
    try:
        os.remove(pwd2)
    except Exception:
        pass
    try:
        os.remove(pwd3)
    except Exception:
        pass

    # embed person image bytes and password images as data URLs in the returned payload
    unlock_until = _set_unlocked_for(UNLOCK_WINDOW_SECONDS)

    out = jsonable_encoder(db_item)
    try:
        imgpath = os.path.join(IMAGES_DIR, db_item.person_image) if db_item.person_image else None
        if imgpath and os.path.exists(imgpath):
            ext = os.path.splitext(imgpath)[1].lstrip('.') or 'jpeg'
            with open(imgpath, 'rb') as f:
                b = f.read()
            out['person_image'] = f"data:image/{ext};base64,{base64.b64encode(b).decode('ascii') }"
    except Exception:
        out['person_image'] = db_item.person_image

    out['unlock_expires_at'] = unlock_until.isoformat()

    # Do not include or persist any password image data in the response

    return out

@app.get("/inventory/items/{item_id}", response_model=InventoryItem)
def get_item(item_id: int):
    with Session(engine) as session:
        item = session.get(InventoryItem, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        out = jsonable_encoder(item)
        try:
            imgpath = os.path.join(IMAGES_DIR, item.person_image) if item.person_image else None
            if imgpath and os.path.exists(imgpath):
                ext = os.path.splitext(imgpath)[1].lstrip('.') or 'jpeg'
                with open(imgpath, 'rb') as f:
                    b = f.read()
                out['person_image'] = f"data:image/{ext};base64,{base64.b64encode(b).decode('ascii') }"
        except Exception:
            out['person_image'] = item.person_image

        return out


@app.get("/inventory/items")
def list_items():
    with Session(engine) as session:
        try:
            res = session.exec(text("SELECT * FROM inventoryitem"))
            rows = res.fetchall()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"DB read error: {e}")

    items = []
    for r in rows:
        try:
            m = dict(r._mapping)
        except Exception:
            try:
                m = dict(r)
            except Exception:
                m = {str(i): v for i, v in enumerate(r)}

        person_value = m.get('person_image')
        person_data_url = None
        try:
            if isinstance(person_value, str) and person_value:
                if person_value.startswith('data:'):
                    person_data_url = person_value
                else:
                    imgpath = os.path.join(IMAGES_DIR, person_value)
                    if os.path.exists(imgpath):
                        ext = os.path.splitext(imgpath)[1].lstrip('.') or 'jpeg'
                        with open(imgpath, 'rb') as f:
                            b = f.read()
                        person_data_url = f"data:image/{ext};base64,{base64.b64encode(b).decode('ascii') }"
        except Exception:
            person_data_url = person_value if isinstance(person_value, str) else None

        # We no longer store password image files; omit them from listing
        password_urls = []

        selfie_data_url = next((url for url in password_urls if url), None)
        item_id = m.get('id')

        items.append({
            "id": str(item_id) if item_id is not None else None,
            "label": m.get('item'),
            "thumbDataUrl": person_data_url or "",
            "selfieDataUrl": selfie_data_url,
            "passwordImageUrls": password_urls or None,
        })

    return jsonable_encoder(items)


    


@app.post("/inventory/items/{item_id}/unlock")
def unlock_item(
    item_id: int,
    attempt_image_1: UploadFile = File(...),
    attempt_image_2: UploadFile = File(...),
    attempt_image_3: UploadFile = File(...),
):
    """Upload three photos to attempt unlocking the item. Returns per-image similarity scores and overall success."""
    # save attempts to temp files
    tmp1 = os.path.join(IMAGES_DIR, f"attempt_{uuid4().hex}_{attempt_image_1.filename or '1'}")
    tmp2 = os.path.join(IMAGES_DIR, f"attempt_{uuid4().hex}_{attempt_image_2.filename or '2'}")
    tmp3 = os.path.join(IMAGES_DIR, f"attempt_{uuid4().hex}_{attempt_image_3.filename or '3'}")
    with open(tmp1, "wb") as f:
        shutil.copyfileobj(attempt_image_1.file, f)
    with open(tmp2, "wb") as f:
        shutil.copyfileobj(attempt_image_2.file, f)
    with open(tmp3, "wb") as f:
        shutil.copyfileobj(attempt_image_3.file, f)

    try:
        afp1 = build_fingerprint(extract_body_and_hand_positions(tmp1))
        afp2 = build_fingerprint(extract_body_and_hand_positions(tmp2))
        afp3 = build_fingerprint(extract_body_and_hand_positions(tmp3))

        with Session(engine) as session:
            item = session.get(InventoryItem, item_id)
            if not item:
                raise HTTPException(status_code=404, detail="Item not found")

            stored = item.password_image or {}

            if 'fingerprints' in stored and isinstance(stored['fingerprints'], list) and len(stored['fingerprints']) >= 3:
                sp1, sp2, sp3 = stored['fingerprints'][:3]
            elif 'fingerprint' in stored:
                # legacy single fingerprint -> compare same fingerprint to all attempts
                sp = stored.get('fingerprint') or []
                sp1 = sp2 = sp3 = sp
            else:
                raise HTTPException(status_code=400, detail="Stored fingerprint format unsupported")

            s1 = compare_fingerprints(sp1, afp1)
            s2 = compare_fingerprints(sp2, afp2)
            s3 = compare_fingerprints(sp3, afp3)

            avg = float((s1 + s2 + s3) / 3.0)
            success = avg >= UNLOCK_THRESHOLD

            response_payload = {
                "item_id": item_id,
                "item": item.item,
                "scores": [float(s1), float(s2), float(s3)],
                "average": avg,
                "success": bool(success),
            }

            if success:
                unlock_until = _set_unlocked_for(UNLOCK_WINDOW_SECONDS)
                response_payload["unlock_expires_at"] = unlock_until.isoformat()
                person_filename = item.person_image
                password_filenames = []
                if isinstance(stored, dict):
                    raw_filenames = stored.get('filenames') or []
                    password_filenames = [fn for fn in raw_filenames if isinstance(fn, str)]

                session.delete(item)
                session.commit()

                files_to_cleanup = []
                if person_filename:
                    files_to_cleanup.append(os.path.join(IMAGES_DIR, person_filename))
                for fn in password_filenames:
                    files_to_cleanup.append(os.path.join(IMAGES_DIR, fn))

                for fpath in files_to_cleanup:
                    _remove_file_if_exists(fpath)

            return jsonable_encoder(response_payload)
    finally:
        try:
            os.remove(tmp1)
        except Exception:
            pass
        try:
            os.remove(tmp2)
        except Exception:
            pass
        try:
            os.remove(tmp3)
        except Exception:
            pass

@app.get("/lock/state")
def get_lock_state():
    return jsonable_encoder(_current_lock_state())



