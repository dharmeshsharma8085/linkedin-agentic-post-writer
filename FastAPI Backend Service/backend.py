import json
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# Importing project loads .env and compiles the LangGraph app
from project import app as graph_app


# ============================================================
# FASTAPI SETUP
# ============================================================

api = FastAPI(
    title="LinkedIn Post Generator API",
    description="Writer + Reviewer LangGraph workflow that generates LinkedIn posts.",
    version="1.0.0",
)

api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restrict to your frontend URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# SCHEMAS
# ============================================================

class GenerateRequest(BaseModel):
    topic: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description="What the LinkedIn post should be about.",
        examples=["I built a multi-agent LinkedIn writer using LangGraph"],
    )


class GenerateResponse(BaseModel):
    topic: str
    post: str
    is_approved: bool
    attempts: int
    review_feedback: Optional[str] = None


# ============================================================
# HELPERS
# ============================================================

GRAPH_CONFIG = {"recursion_limit": 25}


def build_initial_state(topic: str) -> dict:
    return {
        "topic": topic.strip(),
        "messages": [],
        "draft": "",
        "review_feedback": "",
        "is_approved": False,
        "attempt": 0,
    }


def content_to_text(content) -> str:
    """Model content can be a str or a list of content blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)
    return str(content)


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# ============================================================
# ROUTES
# ============================================================

@api.get("/")
def root():
    return {"service": "LinkedIn Post Generator", "docs": "/docs"}


@api.get("/health")
def health():
    return {"status": "ok"}


# Sync `def` so FastAPI runs the blocking graph in a worker thread
# instead of blocking the event loop.
@api.post("/generate", response_model=GenerateResponse)
def generate_post(req: GenerateRequest):
    try:
        result = graph_app.invoke(
            build_initial_state(req.topic),
            config=GRAPH_CONFIG,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {e}")

    return GenerateResponse(
        topic=req.topic,
        post=content_to_text(result.get("draft", "")),
        is_approved=bool(result.get("is_approved", False)),
        attempts=result.get("attempt", 0),
        review_feedback=result.get("review_feedback"),
    )


@api.post("/generate/stream")
def generate_post_stream(req: GenerateRequest):
    """
    Server-Sent Events stream. Emits one event per graph node update:
      - writer         -> writer finished an attempt
      - tools          -> search tool ran
      - draft          -> a draft was extracted
      - review         -> reviewer verdict + feedback
      - done           -> final result
      - error          -> something failed
    """

    def event_stream():
        final = {
            "post": "",
            "is_approved": False,
            "attempts": 0,
            "review_feedback": "",
        }
        try:
            for chunk in graph_app.stream(
                build_initial_state(req.topic),
                config=GRAPH_CONFIG,
                stream_mode="updates",
            ):
                for node, update in chunk.items():
                    if node == "writer":
                        final["attempts"] = update.get("attempt", final["attempts"])
                        yield sse("writer", {"attempt": final["attempts"]})

                    elif node == "tools":
                        yield sse("tools", {"message": "Search tool used"})

                    elif node == "extract_draft":
                        final["post"] = content_to_text(update.get("draft", ""))
                        yield sse("draft", {"post": final["post"]})

                    elif node == "reviewer":
                        final["is_approved"] = bool(update.get("is_approved", False))
                        final["review_feedback"] = update.get("review_feedback", "")
                        yield sse(
                            "review",
                            {
                                "is_approved": final["is_approved"],
                                "feedback": final["review_feedback"],
                            },
                        )

            yield sse("done", final)

        except Exception as e:
            yield sse("error", {"detail": str(e)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ============================================================
# RUN
# ============================================================
# pip install fastapi uvicorn
# uvicorn backend:api --reload --port 8000

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend:api", host="0.0.0.0", port=8000, reload=True)