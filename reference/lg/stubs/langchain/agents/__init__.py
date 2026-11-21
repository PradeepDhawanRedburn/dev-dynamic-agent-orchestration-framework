SCRIPT = {}     # agent role title -> async fn(tools) -> SpecialistOutput | None
class _Msg:
    usage_metadata = {"input_tokens": 1200, "output_tokens": 300}
class _Agent:
    def __init__(self, **kw): self.kw = kw
    async def ainvoke(self, inp, config=None):
        state = {"messages": list(inp["messages"])}
        mws = [m for m in self.kw["middleware"] if hasattr(m, "abefore_model")]
        for m in mws: await m.abefore_model(state, None)
        state["messages"].append(_Msg())
        for m in mws: await m.aafter_model(state, None)
        tools = {t.name: t for t in self.kw["tools"]}
        out = await SCRIPT[config["run_name"]](tools, inp)
        for m in mws: await m.abefore_model(state, None)
        state["messages"].append(_Msg())
        for m in mws: await m.aafter_model(state, None)
        return {"messages": state["messages"], "structured_response": out}
def create_agent(**kw): return _Agent(**kw)
