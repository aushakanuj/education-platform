from pydantic import BaseModel, Field


class TopicSummary(BaseModel):
    id: str
    title: str
    has_lesson: bool
    has_quiz: bool


class LessonSlide(BaseModel):
    number: int
    title: str
    content: str


class LessonMaterial(BaseModel):
    id: str
    title: str
    markdown: str
    slides: list[LessonSlide] = Field(default_factory=list)


class QuizOption(BaseModel):
    label: str
    text: str


class QuizQuestion(BaseModel):
    number: int
    difficulty: str | None = None
    prompt: str
    options: list[QuizOption]


class QuizMaterial(BaseModel):
    id: str
    title: str
    questions: list[QuizQuestion]
