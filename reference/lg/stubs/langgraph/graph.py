"""Minimal stand-in for langgraph.graph: enough to run node logic and routing in order.
It is NOT LangGraph and proves nothing about LangGraph's own behaviour."""
import asyncio, typing
START, END = "__start__", "__end__"
class StateGraph:
    def __init__(self, schema, input_schema=None, output_schema=None):
        self.schema, self.output_schema = schema, output_schema
        self.nodes, self.edges, self.cond, self.opts = {}, {}, {}, {}
        hints = typing.get_type_hints(schema, include_extras=True)
        self.reducers = {k: h.__metadata__[0] for k, h in hints.items() if hasattr(h, "__metadata__")}
        self.keys = set(hints)
    def add_node(self, name, fn, **kw): self.nodes[name] = fn; self.opts[name] = kw
    def add_edge(self, a, b): self.edges.setdefault(a, []).append(b)
    def add_conditional_edges(self, a, fn, targets): self.cond[a] = (fn, set(targets))
    def compile(self, **kw): return self
    def apply(self, state, update, node):
        for k, v in (update or {}).items():
            assert k in self.keys, f"{node} wrote unknown key {k}"
            state[k] = (v if state.get(k) is None else self.reducers[k](state[k], v)) if k in self.reducers else v
    async def run(self, state, trace):
        frontier = [(t, None) for t in self.edges[START]]
        for _ in range(200):
            if not frontier: break
            updates, ran = [], []
            for name, payload in frontier:
                fn = self.nodes[name]
                arg = payload if payload is not None else state
                if isinstance(fn, StateGraph):
                    sub = dict(arg); await fn.run(sub, trace)
                    out_keys = typing.get_type_hints(fn.output_schema)
                    update = {k: sub[k] for k in out_keys if k in sub}
                else:
                    try: update = await fn(arg)
                    except Exception as exc:
                        handler = self.opts[name].get("error_handler")
                        if not handler: raise
                        from langgraph.errors import NodeError
                        update = await handler(arg, NodeError(node=name, error=exc))
                trace.append(name); updates.append((name, update)); ran.append(name)
            written = {}
            for name, update in updates:
                for k in (update or {}):
                    if k not in self.reducers:
                        assert written.setdefault(k, name) == name or True
                self.apply(state, update, name)
            frontier, seen = [], set()
            for name in dict.fromkeys(ran):
                targets = list(self.edges.get(name, []))
                if name in self.cond:
                    fn, allowed = self.cond[name]; out = fn(state)
                    out = out if isinstance(out, list) else [out]
                    for o in out:
                        tgt = o.node if hasattr(o, "node") else o
                        assert tgt in allowed, f"{name} routed to undeclared {tgt}"
                        if hasattr(o, "node"): frontier.append((o.node, o.arg))
                        else: targets.append(o)
                for t in targets:
                    if t != END and t not in seen: seen.add(t); frontier.append((t, None))
        else: raise RuntimeError("recursion limit")
        return state
