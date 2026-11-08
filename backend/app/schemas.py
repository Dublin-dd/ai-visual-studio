from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    workspace: str = Field(default="ecommerce", pattern="^(ecommerce|drama)$")


class ProjectRename(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class ProjectCover(BaseModel):
    asset_id: str | None = Field(..., max_length=36)


class BoardBackground(BaseModel):
    color: str = Field(pattern="^#[0-9a-fA-F]{6}$")


class LayerIn(BaseModel):
    asset_id: str
    x: float = 0.0
    y: float = 0.0
    width: float = Field(default=300.0, gt=0, le=8000)
    height: float = Field(default=300.0, gt=0, le=8000)
    z: int = 1
    rotation: float = 0.0


class LayersUpdate(BaseModel):
    layers: list[LayerIn] = Field(default_factory=list, max_length=200)


class ExportRequest(BaseModel):
    pass


class TaskCreate(BaseModel):
    project_id: str = Field(min_length=1)
    kind: str = Field(
        default="image_generate",
        pattern="^(image_generate|cutout|image_edit|sku_variants)$",
    )
    prompt: str = Field(default="", max_length=2000)
    source_asset_id: str | None = None
    colors: list[str] = Field(default_factory=list, max_length=8)
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)
    width: int = Field(default=1024, ge=256, le=2048)
    height: int = Field(default=1024, ge=256, le=2048)
    count: int = Field(default=1, ge=1, le=4)
    tier: str = Field(default="standard", pattern="^(draft|standard|hq)$")
