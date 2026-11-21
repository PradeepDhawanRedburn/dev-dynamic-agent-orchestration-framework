class AgentMiddleware:
    def __init__(self, *a, **k): pass
class ModelCallLimitMiddleware(AgentMiddleware): pass
class ToolCallLimitMiddleware(AgentMiddleware): pass
class ModelRetryMiddleware(AgentMiddleware): pass
