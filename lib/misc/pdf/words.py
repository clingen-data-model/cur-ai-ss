from pydantic import BaseModel


class Polygon(BaseModel):
    """Polygon with 4 corner coordinates (top-left, top-right, bottom-right, bottom-left)."""

    x0: float
    y0: float
    x1: float
    y1: float
    x2: float
    y2: float
    x3: float
    y3: float


class WordLoc(Polygon):
    page_idx: int
    word: str

    def to_polygon(self) -> Polygon:
        """Convert to a Polygon, discarding word-specific fields."""
        return Polygon(
            x0=self.x0,
            y0=self.y0,
            x1=self.x1,
            y1=self.y1,
            x2=self.x2,
            y2=self.y2,
            x3=self.x3,
            y3=self.y3,
        )
