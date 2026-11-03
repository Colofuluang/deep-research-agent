from pydantic import BaseModel, ConfigDict, Field

class ResearchRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    topic: str = Field(
        min_length=1,
        description="研究主题",
    )

class ResearchResponse(BaseModel):
    run_id: str
    topic: str
    completed_tasks: int = Field(ge=0)
    report: str
    evaluation_results: list[dict]