from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config, models
from ..db import get_db
from ..errors import err
from ..services import storage
from ..services.presenters import asset_out

router = APIRouter(prefix="/api", tags=["assets"])


@router.post("/assets/upload", status_code=201)
async def upload_asset(
    project_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    project = db.scalars(
        select(models.Project).where(
            models.Project.id == project_id,
            models.Project.owner_id == config.DEFAULT_OWNER_ID,
        )
    ).first()
    if project is None:
        return err(404, "NOT_FOUND", "项目不存在")

    # 分块读，避免超大文件一次性进内存
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > config.MAX_UPLOAD_BYTES:
            limit_mb = config.MAX_UPLOAD_BYTES // (1024 * 1024)
            return err(400, "FILE_TOO_LARGE", f"文件超过 {limit_mb}MB 限制")
        chunks.append(chunk)
    data = b"".join(chunks)

    try:
        fmt, width, height = storage.validate_image_bytes(data)
        path, name, size = storage.save_upload(data, fmt)
    except storage.UploadRejected as e:
        return err(400, e.code, e.message)

    asset = models.Asset(
        owner_id=config.DEFAULT_OWNER_ID,
        project_id=project_id,
        kind="upload",
        filename=name,
        path=str(path),
        mime={
            "JPEG": "image/jpeg",
            "PNG": "image/png",
            "WEBP": "image/webp",
        }.get(fmt, "application/octet-stream"),
        width=width,
        height=height,
        size_bytes=size,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset_out(asset)


@router.get("/files/{asset_id}")
def get_file(asset_id: str, db: Session = Depends(get_db)):
    asset = db.scalars(
        select(models.Asset).where(
            models.Asset.id == asset_id,
            models.Asset.owner_id == config.DEFAULT_OWNER_ID,
        )
    ).first()
    if asset is None:
        return err(404, "NOT_FOUND", "素材不存在")
    return FileResponse(asset.path, media_type=asset.mime, filename=asset.filename)
