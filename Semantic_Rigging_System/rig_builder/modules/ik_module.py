try:
    from .rig_module import RigModule
except ImportError:
    from modules.rig_module import RigModule


class IKModule(RigModule):
    def build(self):
        self.create_controls()
        self.create_solver()
        self.connect_graph()

    def create_controls(self):
        pass

    def create_solver(self):
        pass

    def connect_graph(self):
        pass
