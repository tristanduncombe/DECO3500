from typing import Optional
from fastapi import FastAPI, UploadFile, File, HTTPException
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
import requests

UNLOCK_THRESHOLD = 0.8

app = FastAPI()

@lru_cache
def get_database_url() -> str:
    # return os.getenv("DATABASE_URL", "sqlite:///./inventory.db")
    return "postgresql+psycopg://postgres:postgres@localhost:5432/deco"

DATABASE_URL = get_database_url()
engine = None

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

class InventoryItem(SQLModel):
    id: Optional[int] = Field(default=None, primary_key=True)
    item: str
    person_image: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    password_image: Optional[dict] = Field(default=None, sa_column=Column(JSONB, nullable=True))

    class Config:
        table = True

SQLModel.metadata.create_all(engine)

@app.post("/inventory/items", response_model=InventoryItem)
def create_item(
    item: str,
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

    # save files
    person_path = os.path.join(IMAGES_DIR, person_image.filename)
    with open(person_path, "wb") as f:
        shutil.copyfileobj(person_image.file, f)

    pwd1 = os.path.join(IMAGES_DIR, password_image_1.filename)
    with open(pwd1, "wb") as f:
        shutil.copyfileobj(password_image_1.file, f)

    pwd2 = os.path.join(IMAGES_DIR, password_image_2.filename)
    with open(pwd2, "wb") as f:
        shutil.copyfileobj(password_image_2.file, f)

    pwd3 = os.path.join(IMAGES_DIR, password_image_3.filename)
    with open(pwd3, "wb") as f:
        shutil.copyfileobj(password_image_3.file, f)

    # extract positions and fingerprints for each password image
    pos1 = extract_body_and_hand_positions(pwd1)
    pos2 = extract_body_and_hand_positions(pwd2)
    pos3 = extract_body_and_hand_positions(pwd3)

    fp1 = build_fingerprint(pos1)
    fp2 = build_fingerprint(pos2)
    fp3 = build_fingerprint(pos3)

    db_item = InventoryItem(
        item=item,
        person_image=person_image.filename,
        password_image={
            "fingerprints": [fp1, fp2, fp3],
        },
    )

    with Session(engine) as session:
        session.add(db_item)
        session.commit()
        session.refresh(db_item)
    # persist password filenames on disk and save filenames into the DB record
    filenames = [os.path.basename(pwd1), os.path.basename(pwd2), os.path.basename(pwd3)]
    try:
        with Session(engine) as session:
            obj = session.get(InventoryItem, db_item.id)
            if isinstance(obj.password_image, dict):
                obj.password_image['filenames'] = filenames
            else:
                obj.password_image = {'filenames': filenames}
            session.add(obj)
            session.commit()
            session.refresh(obj)
            db_item = obj
    except Exception:
        pass

    # embed person image bytes and password images as data URLs in the returned payload
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

    try:
        pfiles = db_item.password_image.get('filenames') if isinstance(db_item.password_image, dict) else None
        if pfiles:
            pw_urls = []
            for fn in pfiles:
                ppath = os.path.join(IMAGES_DIR, fn)
                if os.path.exists(ppath):
                    ext = os.path.splitext(ppath)[1].lstrip('.') or 'jpeg'
                    with open(ppath, 'rb') as pf:
                        pb = pf.read()
                    pw_urls.append(f"data:image/{ext};base64,{base64.b64encode(pb).decode('ascii') }")
                else:
                    pw_urls.append(None)
            out['password_images'] = pw_urls
    except Exception:
        pass

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

    out = []
    for r in rows:
        try:
            m = dict(r._mapping)
        except Exception:
            try:
                m = dict(r)
            except Exception:
                m = {str(i): v for i, v in enumerate(r)}
        # if there's a person_image filename, try to embed the image bytes as a data URL
        try:
            if m.get('person_image'):
                imgpath = os.path.join(IMAGES_DIR, m.get('person_image'))
                if os.path.exists(imgpath):
                    ext = os.path.splitext(imgpath)[1].lstrip('.') or 'jpeg'
                    with open(imgpath, 'rb') as f:
                        b = f.read()
                    m['person_image'] = f"data:image/{ext};base64,{base64.b64encode(b).decode('ascii') }"
        except Exception:
            # leave whatever was in the row if embedding fails
            pass

        # embed password images list if filenames saved in the password_image column
        try:
            pw = m.get('password_image')
            if isinstance(pw, dict) and pw.get('filenames'):
                pw_urls = []
                for fn in pw.get('filenames'):
                    ppath = os.path.join(IMAGES_DIR, fn)
                    if os.path.exists(ppath):
                        ext = os.path.splitext(ppath)[1].lstrip('.') or 'jpeg'
                        with open(ppath, 'rb') as f:
                            pb = f.read()
                        pw_urls.append(f"data:image/{ext};base64,{base64.b64encode(pb).decode('ascii') }")
                    else:
                        pw_urls.append(None)
                m['password_images'] = pw_urls
        except Exception:
            pass

        out.append(m)

    return jsonable_encoder(out)


@app.post("/inventory/items/test", response_model=InventoryItem)
def create_test_item():
    """Create a test InventoryItem using a downloaded image for both person and password images."""
    url = "https://cdn.pixabay.com/photo/2019/03/12/20/39/girl-4051811_960_720.jpg"
    fname = "test_photo.jpg"
    path = os.path.join(IMAGES_DIR, fname)

    # download image
    resp = requests.get(url, stream=True, timeout=10)
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Failed to download test image")
    with open(path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

    # use same file for person and create three password copies for test
    person_filename = fname
    password_path1 = os.path.join(IMAGES_DIR, f"test_password_1{os.path.splitext(fname)[1]}")
    password_path2 = os.path.join(IMAGES_DIR, f"test_password_2{os.path.splitext(fname)[1]}")
    password_path3 = os.path.join(IMAGES_DIR, f"test_password_3{os.path.splitext(fname)[1]}")
    shutil.copyfile(path, password_path1)
    shutil.copyfile(path, password_path2)
    shutil.copyfile(path, password_path3)

    pos1 = extract_body_and_hand_positions(password_path1)
    pos2 = extract_body_and_hand_positions(password_path2)
    pos3 = extract_body_and_hand_positions(password_path3)

    fp1 = build_fingerprint(pos1)
    fp2 = build_fingerprint(pos2)
    fp3 = build_fingerprint(pos3)

    db_item = InventoryItem(
        item="test",
        person_image=person_filename,
        password_image={
            "fingerprints": [fp1, fp2, fp3],
        },
    )

    with Session(engine) as session:
        session.add(db_item)
        session.commit()
        session.refresh(db_item)

    # keep password copies on disk and record their filenames in the DB
    filenames = [os.path.basename(password_path1), os.path.basename(password_path2), os.path.basename(password_path3)]
    try:
        with Session(engine) as session:
            obj = session.get(InventoryItem, db_item.id)
            if isinstance(obj.password_image, dict):
                obj.password_image['filenames'] = filenames
            else:
                obj.password_image = {'filenames': filenames}
            session.add(obj)
            session.commit()
            session.refresh(obj)
            db_item = obj
    except Exception:
        pass

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

    try:
        pfiles = db_item.password_image.get('filenames') if isinstance(db_item.password_image, dict) else None
        if pfiles:
            pw_urls = []
            for fn in pfiles:
                ppath = os.path.join(IMAGES_DIR, fn)
                if os.path.exists(ppath):
                    ext = os.path.splitext(ppath)[1].lstrip('.') or 'jpeg'
                    with open(ppath, 'rb') as pf:
                        pb = pf.read()
                    pw_urls.append(f"data:image/{ext};base64,{base64.b64encode(pb).decode('ascii') }")
                else:
                    pw_urls.append(None)
            out['password_images'] = pw_urls
    except Exception:
        pass

    return out


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

            stored = item.password_image

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

            return jsonable_encoder({
                "item_id": item_id,
                "scores": [float(s1), float(s2), float(s3)],
                "average": avg,
                "success": bool(success),
            })
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


@app.get("/inventory/items/{item_id}/unlock/test")
def unlock_item_test(item_id: int):
    """Attempt unlock using the stored person/test image for this item.

    Compares the stored three fingerprints against the person image (used for all three attempts).
    """
    with Session(engine) as session:
        item = session.get(InventoryItem, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

    if not item.person_image:
        raise HTTPException(status_code=400, detail="No person image available for this item")

    person_path = os.path.join(IMAGES_DIR, item.person_image)
    if not os.path.exists(person_path):
        raise HTTPException(status_code=500, detail="Person image file missing on server")

    afp = build_fingerprint(extract_body_and_hand_positions(person_path))

    stored = item.password_image
    if not stored or not isinstance(stored, dict):
        raise HTTPException(status_code=400, detail="No stored fingerprint(s) for this item")

    if 'fingerprints' in stored and isinstance(stored['fingerprints'], list) and len(stored['fingerprints']) >= 3:
        sp1, sp2, sp3 = stored['fingerprints'][:3]
    elif 'fingerprint' in stored:
        sp = stored.get('fingerprint') or []
        sp1 = sp2 = sp3 = sp
    else:
        raise HTTPException(status_code=400, detail="Stored fingerprint format unsupported")

    s1 = compare_fingerprints(sp1, afp)
    s2 = compare_fingerprints(sp2, afp)
    s3 = compare_fingerprints(sp3, afp)

    avg = float((s1 + s2 + s3) / 3.0)
    success = avg >= UNLOCK_THRESHOLD

    return jsonable_encoder({
        "item_id": item_id,
        "scores": [float(s1), float(s2), float(s3)],
        "average": avg,
        "success": bool(success),
    })
