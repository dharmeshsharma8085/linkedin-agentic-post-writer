from dotenv import load_dotenv

from typing import TypedDict, Annotated

from langchain_openai import ChatOpenAI
from langchain_tavily import TavilySearch

from langgraph.graph import (
    StateGraph,
    START,
    END,
)

from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode


load_dotenv()


# ============================================================
# TOOLS
# ============================================================

search_tool = TavilySearch(
    max_results=3
)

tools = [search_tool]


# ============================================================
# MODELS
# ============================================================

llm = ChatOpenAI(
    model="gpt-5",
    temperature=0.7
)

# Writer has access to tools
writer_model = llm.bind_tools(tools)

# Reviewer does NOT need tools
reviewer_model = llm


# ============================================================
# STATE
# ============================================================

class State(TypedDict, total=False):
    topic: str

    messages: Annotated[
        list,
        add_messages
    ]

    draft: str

    review_feedback: str

    is_approved: bool

    attempt: int


# ============================================================
# WRITER PROMPT
# ============================================================

WRITER_SYSTEM_PROMPT = """
You are an expert LinkedIn content writer specializing in:

- AI/ML
- Generative AI
- LLMs
- RAG
- LangChain
- LangGraph
- AI agents
- Agentic workflows
- Tool calling
- Developer content

Your job is to turn my technical work, projects,
experiments, learning progress, and open-source journey
into authentic LinkedIn posts.

Write like a real developer/student.

Do not sound like corporate marketing.

Avoid:

- "I am thrilled to announce..."
- "Exciting news!"
- "Revolutionizing the world of AI"
- "The future is here"
- Generic motivational statements
- Excessive emojis
- Excessive buzzwords

Use strong, curiosity-driven hooks.

The hook should make the reader want to click
"see more".

The post should be:

- Human
- Authentic
- Technically accurate
- Easy to understand
- Interesting to developers
- Confident but not arrogant

Never invent:

- Features
- Benchmarks
- Accuracy
- Users
- GitHub stars
- Performance improvements
- Tools
- APIs
- Results

Only talk about what is actually provided.

If the topic requires current information,
use the available search tool.

If previous reviewer feedback is provided,
fix every meaningful issue mentioned in that feedback.

Do not repeat the same mistakes.

Return ONLY the final LinkedIn post.

Do not return:

- Analysis
- Hook explanation
- Technical accuracy check
- Separate explanation
- Meta commentary

Keep the post readable with short paragraphs.

Use 3-5 relevant hashtags at the end.
"""


# ============================================================
# WRITER NODE
# ============================================================

def writer_node(state: State) -> dict:
    """
    Generate or improve a LinkedIn post based on the current topic
    and reviewer feedback.

    Uses the writer LLM and available search tools when necessary.
    On subsequent attempts, the previous reviewer feedback is provided
    so the model can improve the draft.

    Args:
        state (State): Current workflow state.

    Returns:
        dict: Updated messages and attempt count.
    """

    attempt = state.get("attempt", 0) + 1

    topic = state["topic"]

    previous_feedback = state.get(
        "review_feedback",
        ""
    )

    if attempt == 1:

        user_message = f"""
Write a LinkedIn post about:

{topic}

Research the topic using the search tool if current
information is genuinely necessary.
"""

    else:

        user_message = f"""
Improve the LinkedIn post about:

{topic}

The previous draft was rejected.

Reviewer feedback:

{previous_feedback}

Create a new improved version.

Fix every meaningful issue mentioned by the reviewer.
Do not repeat the same mistakes.
"""

    messages = [
        (
            "system",
            WRITER_SYSTEM_PROMPT
        ),
        (
            "user",
            user_message
        )
    ]

    response = writer_model.invoke(messages)

    return {
        "messages": [
            (
                "user",
                user_message
            ),
            response
        ],
        "attempt": attempt
    }


# ============================================================
# TOOL NODE
# ============================================================

tool_node = ToolNode(tools)


# ============================================================
# EXTRACT DRAFT NODE
# ============================================================

def extract_draft_node(state: State) -> dict:
    """
    Extract the generated LinkedIn post from the latest AI message
    and store it as the current draft.

    Args:
        state (State): Current workflow state containing messages.

    Returns:
        dict: Updated state containing the generated draft.
    """

    last_message = state["messages"][-1]

    draft = last_message.content

    print("\n========== GENERATED POST ==========\n")
    print(draft)
    print("\n====================================\n")

    return {
        "draft": draft
    }


# ============================================================
# REVIEWER PROMPT
# ============================================================

REVIEWER_SYSTEM_PROMPT = """
You are an expert LinkedIn content reviewer specializing in:

- AI/ML
- Generative AI
- LLMs
- RAG
- LangChain
- LangGraph
- AI agents
- Developer content

Your job is to critically review a LinkedIn post.

Review the post for:

1. Hook strength
2. Authenticity
3. Technical accuracy
4. Clarity
5. Storytelling
6. Formatting
7. Overall quality

Check whether:

- The first 1-3 lines create curiosity.
- The post sounds human.
- The post avoids generic AI-generated language.
- Technical claims are accurate.
- No features or results are invented.
- The story has a clear flow.
- The post provides useful insight.
- The post avoids unnecessary hype.
- The post does not use excessive emojis.
- The post does not use forced engagement bait.

Be critical but fair.

Do not rewrite the post.

If there are meaningful problems,
provide specific actionable feedback.

If the post is already strong,
approve it.

Return a structured review containing:

is_approved:
true or false

feedback:
specific actionable feedback
"""


# ============================================================
# REVIEW RESULT
# ============================================================

class ReviewResult(TypedDict):
    is_approved: bool
    feedback: str


reviewer_structured = reviewer_model.with_structured_output(
    ReviewResult
)


# ============================================================
# REVIEWER NODE
# ============================================================

def reviewer_node(state: State) -> dict:
    """
    Review the generated LinkedIn draft for quality, authenticity,
    technical accuracy, clarity, and storytelling.

    Determines whether the draft should be approved or sent back
    to the writer for revision.

    Args:
        state (State): Current workflow state containing the draft.

    Returns:
        dict: Updated state containing review feedback and approval status.
    """

    draft = state["draft"]

    prompt = f"""
Review the following LinkedIn post:

--------------------
{draft}
--------------------
"""

    review = reviewer_structured.invoke(
        [
            (
                "system",
                REVIEWER_SYSTEM_PROMPT
            ),
            (
                "user",
                prompt
            )
        ]
    )

    is_approved = review["is_approved"]

    feedback = review["feedback"]

    verdict = (
        "APPROVED"
        if is_approved
        else "REJECTED"
    )

    print(f"\n[Verdict: {verdict}]")
    print(f"[Feedback: {feedback}]\n")

    return {
        "review_feedback": feedback,
        "is_approved": is_approved
    }

# ============================================================
# ROUTING
# ============================================================

def should_use_tool(state: State):
    last_message = state["messages"][-1]

    if getattr(last_message, "tool_calls", None):
        return "tools"

    return "extract_draft"


def review_router(state: State):

    if state["is_approved"]:
        print("Post has been approved.")
        return "end"

    if state["attempt"] >= 3:
        print("Reached maximum attempts.")
        return "end"

    return "writer"


# ============================================================
# GRAPH
# ============================================================

graph = StateGraph(State)


# -------------------- NODES --------------------

graph.add_node(
    "writer",
    writer_node
)

graph.add_node(
    "tools",
    tool_node
)

graph.add_node(
    "extract_draft",
    extract_draft_node
)

graph.add_node(
    "reviewer",
    reviewer_node
)


# -------------------- START --------------------

graph.add_edge(
    START,
    "writer"
)


# -------------------- WRITER ROUTING --------------------

graph.add_conditional_edges(
    "writer",
    should_use_tool,
    {
        "tools": "tools",
        "extract_draft": "extract_draft"
    }
)


# -------------------- TOOL → WRITER --------------------

graph.add_edge(
    "tools",
    "writer"
)


# -------------------- DRAFT → REVIEWER --------------------

graph.add_edge(
    "extract_draft",
    "reviewer"
)


# -------------------- REVIEWER ROUTING --------------------

graph.add_conditional_edges(
    "reviewer",
    review_router,
    {
        "writer": "writer",
        "end": END
    }
)


# ============================================================
# COMPILE
# ============================================================

app = graph.compile()
