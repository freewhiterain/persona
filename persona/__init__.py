"""persona — a lightweight virtual-persona chat framework.

Rewritten clean-room from the luoyun_project architecture:
multi-agent generator pipeline, multi-route memory recall, a message
queue with an advisory lock for delayed / interruptible replies, and an
affinity / proactive-message system.  Storage is a single SQLite file;
the LLM is any OpenAI-compatible endpoint.
"""

__version__ = "0.1.0"
