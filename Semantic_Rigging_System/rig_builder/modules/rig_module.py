class RigModule:
    def __init__(self, context, chain, recipe, name, logger=None):
        self.context = context
        self.chain = chain
        self.recipe = recipe
        self.name = name
        self.logger = logger

    def validate(self):
        pass

    def build(self):
        raise NotImplementedError()
