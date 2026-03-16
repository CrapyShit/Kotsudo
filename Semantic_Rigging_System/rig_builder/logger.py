class RigLogger:
    def __init__(self):
        self.indent = 0

    def log(self, message):
        print("  " * self.indent + message)

    def push(self, message):
        self.log(message)
        self.indent += 1

    def pop(self):
        if self.indent > 0:
            self.indent -= 1