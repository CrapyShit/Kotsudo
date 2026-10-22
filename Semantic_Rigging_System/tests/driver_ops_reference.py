"""Reference evaluation of exported driver ops (plain python, shared by the tests).

The exporter writes "slider -> maths -> target" as a list of ops (see
export_rig_manifest._attribute_driver). This is what both sides must agree
with: the Maya tests check it against Maya's own results, the offline Unreal
tests check the Control Rig graph against it.
"""


def apply_ops(value, ops):
    for op in ops or []:
        kind = op["op"]
        if kind == "mul":
            value *= op["value"]
        elif kind == "div":
            value /= op["value"]
        elif kind == "pow":
            value = value ** op["value"]
        elif kind == "add":
            value += op["value"]
        elif kind == "reverse":
            value = 1.0 - value
        elif kind == "clamp":
            value = min(max(value, op["min"]), op["max"])
        elif kind == "remap":
            (a, b), (c, d) = op["from"], op["to"]
            t = 0.0 if b == a else min(max((value - a) / (b - a), 0.0), 1.0)
            value = c + (d - c) * t
        elif kind == "curve":
            keys = op["keys"]
            if value <= keys[0][0]:
                value = keys[0][1]
            elif value >= keys[-1][0]:
                value = keys[-1][1]
            else:
                for (x0, y0), (x1, y1) in zip(keys, keys[1:]):
                    if x0 <= value <= x1:
                        value = y0 + (y1 - y0) * (value - x0) / (x1 - x0)
                        break
        elif kind == "compare":
            ok = {"eq": value == op["value"], "ne": value != op["value"], "gt": value > op["value"],
                  "ge": value >= op["value"], "lt": value < op["value"], "le": value <= op["value"]}[op["test"]]
            value = op["true"] if ok else op["false"]
        else:
            raise ValueError("unknown op {}".format(kind))
    return value
