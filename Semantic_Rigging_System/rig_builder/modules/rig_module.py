class RigModule:
    module_type = None

    def __init__(self, context, chain, recipe, name, logger=None,
                 parent_module_name=None, parent_attach_point=None):
        self.context = context
        self.chain = chain
        self.recipe = recipe
        self.name = name
        self.logger = logger
        # Name of the module whose attach point this module roots under, or None.
        self.parent_module_name = parent_module_name
        # Which attach point on the parent to use for control parenting (e.g. "fk_tip_ctrl").
        self.parent_attach_point = parent_attach_point

    @classmethod
    def describe_contract(cls):
        return {
            "module_type": cls.module_type,
            "chain": {
                "min_length": None,
                "max_length": None,
                "exact_length": None,
                "roles": [],
            },
            "required_metadata": [],
            "required_recipe_fields": [],
            "attachment_points": [],
            "build_products": ["controls", "nodes", "attach_points"],
        }

    @staticmethod
    def normalize_property_name(name):
        return "".join(character for character in str(name).lower() if character.isalnum())

    @staticmethod
    def read_unreal_property(obj, property_name):
        if hasattr(obj, "get_editor_property"):
            try:
                return obj.get_editor_property(property_name)
            except Exception:
                pass

        return getattr(obj, property_name)

    def resolve_recipe_fields(self, recipe_fields, fallback_names=None):
        resolved_fields = dict(recipe_fields)
        if not self.recipe:
            return resolved_fields

        fallback_names = fallback_names or {}

        try:
            available_names = [name for name in dir(self.recipe) if not name.startswith("_")]
        except Exception:
            available_names = []

        for field_name in resolved_fields.keys():
            candidate_names = [field_name] + fallback_names.get(field_name, []) + [field_name.lower()]
            resolved = False
            for candidate_name in dict.fromkeys(candidate_names):
                try:
                    resolved_fields[field_name] = self.read_unreal_property(self.recipe, candidate_name)
                    resolved = True
                    break
                except Exception:
                    continue

            if resolved:
                continue

            normalized_field_name = self.normalize_property_name(field_name)
            fuzzy_matches = sorted(
                [
                    candidate_name
                    for candidate_name in available_names
                    if self.normalize_property_name(candidate_name).startswith(normalized_field_name)
                ],
                key=len,
            )

            for candidate_name in fuzzy_matches:
                try:
                    resolved_fields[field_name] = self.read_unreal_property(self.recipe, candidate_name)
                    break
                except Exception:
                    continue

        return resolved_fields

    def validate(self):
        pass

    def build_result(self, controls=None, nodes=None, attach_points=None, outputs=None, recipe_data=None, metadata=None):
        return {
            "module_name": self.name,
            "module_type": self.module_type,
            "chain": list(self.chain),
            "controls": controls or [],
            "nodes": nodes or [],
            "attach_points": attach_points or {},
            "outputs": outputs or {},
            "recipe": recipe_data or {},
            "metadata": metadata or {},
        }

    def build(self):
        raise NotImplementedError()
