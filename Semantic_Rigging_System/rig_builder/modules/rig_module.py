class RigModule:
    def __init__(self, rig, chain, recipe, name):
        self.rig = rig
        self.chain = chain
        self.recipe = recipe
        self.name = name

    def build(self):
        raise NotImplementedError
