from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Point(Strict):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    include: bool = True


class Annotation(Strict):
    frame: int = Field(ge=0)
    points: list[Point] = Field(default_factory=list, max_length=100)
    box: tuple[float, float, float, float] | None = None

    @model_validator(mode="after")
    def check_box(self):
        if self.box:
            x1, y1, x2, y2 = self.box
            if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
                raise ValueError("Box must be ordered normalized coordinates")
        return self


class FrameInterval(Strict):
    start: int = Field(ge=0)
    end: int = Field(gt=0)

    @model_validator(mode="after")
    def ordered(self):
        if self.end <= self.start:
            raise ValueError("Interval end must follow its start (end is exclusive)")
        return self


class VisibilityInterval(FrameInterval):
    state: Literal["absent", "fully_occluded", "partially_occluded"]
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def explained(self):
        if not self.reason.strip():
            raise ValueError("Visibility changes require an evidence-based reason")
        return self


class Subject(Strict):
    id: int = Field(ge=1, le=3)
    name: str = Field(default="Subject", max_length=100)
    references: list[str] = Field(default_factory=list, max_length=8)
    kind: Literal["human", "fictional"] = "human"
    portrait_asset: str | None = None
    consent_confirmed: bool = False
    intervals: list[FrameInterval] = Field(default_factory=list, max_length=30)
    visibility: list[VisibilityInterval] = Field(default_factory=list, max_length=100)
    seed_frame: int | None = Field(default=None, ge=0)
    annotations: list[Annotation] = Field(default_factory=list, max_length=100)


class Recipe(Strict):
    start: float = Field(default=0, ge=0)
    end: float = Field(default=5, gt=0)
    mode: Literal["advanced", "fast", "combined"] = "advanced"
    subjects: list[Subject] = Field(default_factory=list, max_length=3)
    allow_empty_frames: bool = False
    argolink_mode: Literal["edit", "reference"] = "reference"
    pitch: float = Field(default=3, ge=-12, le=12)
    pitch_backend: Literal["librosa", "rubberband"] = "librosa"
    segmentation: Literal["sam2-large", "sam2-small", "sam3"] = "sam2-large"
    audio: Literal["original", "custom"] = "original"
    custom_audio: str | None = None
    custom_mix_background: bool = False
    transcribe: bool = False
    describe: bool = False
    prompt: str = Field(
        default="Replace the selected characters completely using the reference images. Preserve movement, camera timing, background, and vocal synchronization.",
        max_length=20000,
    )

    @model_validator(mode="after")
    def check(self):
        if not 4 <= self.end - self.start <= 30:
            raise ValueError("Select a 4–30 second clip")
        if len({s.id for s in self.subjects}) != len(self.subjects):
            raise ValueError("Subject IDs must be unique")
        count = round((self.end - self.start) * 24)
        for subject in self.subjects:
            previous = 0
            for interval in subject.intervals:
                if interval.start < previous or interval.end > count:
                    raise ValueError(
                        "Intervals must be ordered, non-overlapping, and inside the clip"
                    )
                previous = interval.end
            previous = 0
            spans = subject.intervals or [FrameInterval(start=0, end=count)]
            for note in subject.visibility:
                if note.start < previous or not any(
                    span.start <= note.start < note.end <= span.end for span in spans
                ):
                    raise ValueError(
                        "Visibility must be ordered and contained in tracking intervals"
                    )
                previous = note.end
        if self.mode in {"fast", "combined"} and len(self.subjects) > 1:
            raise ValueError("Mesh modes initially support one subject")
        if self.audio == "custom" and not self.custom_audio:
            raise ValueError("Choose a custom speech asset")
        return self


class CreateJob(Strict):
    source: str
    name: str = Field(default="Untitled clip", max_length=150)
    budget_usd: float = Field(default=0, ge=0, le=10000)
    generation_limit: int | None = Field(default=None, ge=1, le=100)
    recipe: Recipe = Field(default_factory=Recipe)


class UpdateRecipe(Strict):
    revision: int
    recipe: Recipe


class Revision(Strict):
    revision: int


class PreviewRequest(Revision):
    quote_id: str
    operation_id: str = Field(min_length=8, max_length=100)
    pilot: bool = False


class FinalizeRequest(Revision):
    attempt_id: str
    route: Literal["native", "upscale", "original"]
    upscaler: Literal["seedvr2", "realesrgan"] = "seedvr2"
    operation_id: str = Field(min_length=8, max_length=100)
    quote_id: str | None = None
    pilot: bool = False


class Qualification(Strict):
    attempt_id: str
    actual_cost_usd: float = Field(ge=0)
    policy_reviewed: bool
    identity: int = Field(ge=1, le=5)
    motion: int = Field(ge=1, le=5)
    temporal: int = Field(ge=1, le=5)
    no_subject_swap: bool
    synchronized: bool


class Reconcile(Strict):
    remote_id: str | None = None
    confirmed_not_submitted: bool = False
    actual_cost_usd: float | None = Field(default=None, ge=0)
