from pydantic import BaseModel, Field


class ScriptIn(BaseModel):
    title: str = Field(default="", max_length=255)
    content: str = Field(min_length=1, max_length=20000)


class ShotIn(BaseModel):
    index: int = Field(default=1, ge=1, le=999)
    scene: str = Field(default="中景", max_length=16)
    camera: str = Field(default="固定", max_length=16)
    description: str = Field(min_length=1, max_length=2000)
    dialogue: str = Field(default="", max_length=2000)
    duration: int = Field(default=5, ge=2, le=10)
    character_names: list[str] = Field(default_factory=list, max_length=8)


class ShotsReplace(BaseModel):
    shots: list[ShotIn] = Field(default_factory=list, max_length=60)


class CharacterIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=1000)


class CharacterPatch(BaseModel):
    name: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=1000)
