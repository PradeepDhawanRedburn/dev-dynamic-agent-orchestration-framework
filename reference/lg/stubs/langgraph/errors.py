from dataclasses import dataclass
@dataclass(frozen=True)
class NodeError:
    node: str
    error: BaseException
