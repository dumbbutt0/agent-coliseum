"""Typed, non-sensitive failures for the visualization boundary."""


class VisualizationError(ValueError):
    """A run cannot safely cross the visualization validation boundary."""

    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def refuse(code: str, detail: str):
    raise VisualizationError(code, detail)
