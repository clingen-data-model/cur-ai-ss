import logging

from lib.evagg.utils.run import set_run_complete
from lib.evagg.content import PromptBasedContentExtractor
from lib.evagg.library import SinglePaperLibrary
from lib.evagg.io import JSONOutputWriter

logger = logging.getLogger(__name__)


class SinglePMIDApp:
    def __init__(
        self,
        pmid: str,
        gene_symbol: str,
        library: SinglePaperLibrary,
        extractor: PromptBasedContentExtractor,
        writer: JSONOutputWriter,
    ) -> None:
        self._pmid = pmid
        self._gene_symbol = gene_symbol
        self._library = library
        self._extractor = extractor
        self._writer = writer

    def execute(self) -> None:
        # Get the papers that match this query.
        papers = self._library.get_papers({"pmid": self._pmid})
        assert len(papers) == 1
        logger.info(f"Found {len(papers)} papers for pmid: {self._pmid}")
        output_file = self._writer.write(
            self._extractor.extract(papers[0], self._gene_symbol)
        )
        set_run_complete(output_file)
