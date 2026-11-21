class StructuredTool:
    def __init__(self, coroutine, name, description, args_schema):
        self.coroutine, self.name, self.description, self.args_schema = coroutine, name, description, args_schema
    @classmethod
    def from_function(cls, coroutine=None, name=None, description=None, args_schema=None):
        return cls(coroutine, name, description, args_schema)
