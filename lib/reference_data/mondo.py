from pydantic import BaseModel


class MondoTerm(BaseModel):
    mondo_id: str
    term: str


def find_mondo_term_for_disease(disease_name: str) -> MondoTerm | None:
    """Return the selected MONDO term for a plaintext disease name.

    The ontology lookup/agent implementation will replace this placeholder.
    Keeping the function no-op for now lets the pipeline and persistence shape
    land independently.
    """
    _ = disease_name
    return None
