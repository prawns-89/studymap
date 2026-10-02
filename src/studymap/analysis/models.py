"""analysis/topics.json and analysis/papers.json: the paper-analysis stage's output (BRIEF section 6.2).

Claude writes these files (the /study-papers command); the CLI validates them against the corpus and
derives everything else (weightage.json, report.md, the Plan tab) deterministically. The same schema is
the interface for a future --api mode: `studymap schema papers` prints it as JSON Schema.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ID = r"^[a-z0-9][a-z0-9-]*$"
QType = Literal["mcq", "short", "long-explain", "compare", "numerical", "derivation", "diagram",
                "code-write", "code-trace", "code-fix", "design", "simulation"]
Mode = Literal["recall", "understand", "apply"]
Difficulty = Literal["easy", "medium", "hard"]

# BRIEF 6.3 mode rules, by question type: what the type implies when the paper is the evidence
APPLY_TYPES = {"numerical", "diagram", "code-write", "code-trace", "code-fix", "design", "simulation"}
UNDERSTAND_TYPES = {"long-explain", "compare"}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Cluster(Strict):
    id: str = Field(pattern=ID)
    name: str
    order: int = 0


class Topic(Strict):
    """One thing a question can be about. M3 turns each topic into one or more content nodes."""
    id: str = Field(pattern=ID)
    name: str
    cluster: str
    sources: list[str] = Field(default=[], description="corpus refs, page ranges allowed: 'slides/7 - CPU Scheduling.pdf#p8-13'")
    note: str = ""


class UncoveredOk(Strict):
    ref: str = Field(description="glob over unit refs, e.g. 'slides/*#p1' or 'slides/1 - CourseOutline.pdf*'")
    reason: str


class TopicsFile(Strict):
    schema_version: Literal[1] = 1
    clusters: list[Cluster]
    topics: list[Topic]
    uncovered_ok: list[UncoveredOk] = Field(default=[], description="slides deliberately covered by no topic")


class Key(Strict):
    path: str = Field(description="course-relative path, optionally with a page: 'papers/2024-midsem.pdf#p3'")
    status: Literal["official", "unofficial"] = "official"
    note: str = ""


class Paper(Strict):
    id: str = Field(pattern=ID)
    path: str
    kind: Literal["exam", "sample"] = Field("exam", description="sample: unmarked practice questions")
    exam: str = Field(description="exam name as in course.yaml: midsem, compre, ...")
    year: int | None = None
    date: str = ""
    duration_min: int | None = None
    total_marks: float | None = None
    instructions: str = ""
    keys: list[Key] = []
    transcribed_from_image: bool = Field(False, description="question text was read off a scan, not a text layer")
    relevance: float = Field(1.0, ge=0, le=1, description="how much this paper predicts the next one (1 = fully)")
    relevance_reason: str = ""
    marks_note: str = Field("", description="why question marks don't add up to total_marks (e.g. a choice)")
    notes: str = ""


class Answer(Strict):
    text: str
    src: list[str] = Field(description="refs to the key pages the answer comes from")
    caveat: str = Field("", description="where the key looks wrong, incomplete or disputed")


class Question(Strict):
    id: str = Field(pattern=ID)
    paper: str
    number: str = Field(description="as printed: '1c(ii)', 'Q8b'")
    marks: float | None = None
    type: QType
    mode: Mode
    difficulty: Difficulty
    topics: list[str]
    text: str = Field(description="the question, transcribed; code in ``` fences")
    src: str = Field(description="page of the paper: 'papers/2025-midsem.pdf#p2'")
    answer: Answer | None = None
    repeats: list[str] = Field(default=[], description="ids of similar questions in other papers")
    unmapped_reason: str = Field("", description="required when topics is empty")


class Pattern(Strict):
    text: str = Field(description="one plain sentence a student can act on")
    questions: list[str]


class PapersFile(Strict):
    schema_version: Literal[1] = 1
    papers: list[Paper]
    questions: list[Question]
    patterns: list[Pattern] = []
    notes: list[str] = Field(default=[], description="caveats for the report, e.g. a change of instructor")
