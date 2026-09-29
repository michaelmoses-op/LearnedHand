import uuid

from app.schemas.common import StrictModel


class SectionAxisOut(StrictModel):
    id: uuid.UUID
    title: str
    ordinal: int
    chunks: int
    fully_read: bool


class ConceptCellOut(StrictModel):
    section_id: uuid.UUID
    chunks: int  # chunks in the section that mention the concept
    intensity: float  # chunks / section chunks, 0..1


class ConceptRowOut(StrictModel):
    id: uuid.UUID
    name: str
    sections: int
    chunks: int
    cells: list[ConceptCellOut]


class ConceptMapOut(StrictModel):
    """Concept × section heat map, limited to what the reader has reached."""

    progress: int | None
    sections: list[SectionAxisOut]
    concepts: list[ConceptRowOut]


class TrajectoryPointOut(StrictModel):
    section_id: uuid.UUID
    section_title: str
    section_ordinal: int
    first_ordinal: int
    chunks: int
    note: str | None  # null until the reader has finished the section


class TrajectoryOut(StrictModel):
    concept_id: uuid.UUID
    name: str
    points: list[TrajectoryPointOut]
