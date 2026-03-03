from lib.agents.paper_extraction_agent import PaperExtractionOutput
from lib.models import PaperDB


def paper_extraction_to_db(output: PaperExtractionOutput, paper_db: PaperDB) -> None:
    """Update PaperDB with metadata from PaperExtractionOutput."""
    paper_db.title = output.title
    paper_db.first_author = output.first_author
    paper_db.journal = output.journal_name
    paper_db.abstract = output.abstract
    paper_db.pub_year = output.publication_year
    paper_db.doi = output.doi
    paper_db.pmid = output.pmid
    paper_db.pmcid = output.pmcid
    paper_db.paper_types = [pt.value for pt in output.paper_types]
