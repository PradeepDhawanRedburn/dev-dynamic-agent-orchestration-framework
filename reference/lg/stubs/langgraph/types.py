from dataclasses import dataclass, field
ANSWERS = []          # scripted human decisions, consumed in order
class Send:
    def __init__(self, node, arg, timeout=None): self.node, self.arg, self.timeout = node, arg, timeout
class RetryPolicy:
    def __init__(self, **kw): self.kw = kw
class TimeoutPolicy:
    def __init__(self, **kw): self.kw = kw
class Command:
    def __init__(self, **kw): self.kw = kw
def interrupt(value):
    return ANSWERS.pop(0)(value)
