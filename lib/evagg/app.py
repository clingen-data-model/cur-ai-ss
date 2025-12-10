import logging

from lib.evagg.llm import OpenAIClient
<<<<<<< HEAD
=======
from lib.evagg.utils.run import set_run_complete
>>>>>>> 897a9b3455bfa525248463ac6e607e56b329c189
from lib.evagg.content import (
    PromptBasedContentExtractor,
    HGVSVariantComparator,
    HGVSVariantFactory,
    ObservationFinder,
)
<<<<<<< HEAD
=======
from lib.evagg.library import SinglePaperLibrary
from lib.evagg.io import JSONOutputWriter
>>>>>>> 897a9b3455bfa525248463ac6e607e56b329c189
from lib.evagg.ref import (
    MutalyzerClient,
    NcbiLookupClient,
    WebHPOClient,
    PyHPOClient,
    RefSeqLookupClient,
)
from lib.evagg.utils.web import RequestsWebContentClient, WebClientSettings
from lib.evagg.ref.ncbi import get_ncbi_response_translator
<<<<<<< HEAD
from typing import Dict, Sequence
=======
>>>>>>> 897a9b3455bfa525248463ac6e607e56b329c189

logger = logging.getLogger(__name__)


class SinglePMIDApp:
    def __init__(
        self,
        pmid: str,
        gene_symbol: str,
    ) -> None:
        self._pmid = pmid
        self._gene_symbol = gene_symbol
<<<<<<< HEAD
        self._ncbi_lookup_client = NcbiLookupClient(
            web_client=RequestsWebContentClient(
                WebClientSettings(status_code_translator=get_ncbi_response_translator())
            )
=======
        self._library = SinglePaperLibrary(
            ncbi_lookup_client=NcbiLookupClient(
                web_client=RequestsWebContentClient(
                    WebClientSettings(
                        status_code_translator=get_ncbi_response_translator()
                    )
                )
            )
        )
        self._extractor = PromptBasedContentExtractor(
            fields=[
                "evidence_id",
                "gene",
                "paper_id",
                "hgvs_c",
                "hgvs_p",
                "paper_variant",
                "transcript",
                "validation_error",
                "gnomad_frequency",
                "individual_id",
                "phenotype",
                "zygosity",
                "variant_inheritance",
                "variant_type",
                "study_type",
                "source_type",
                "engineered_cells",
                "patient_cells_tissues",
                "animal_model",
                "citation",
                "link",
                "paper_title",
            ],
            llm_client=OpenAIClient(),
            phenotype_searcher=WebHPOClient(
                web_client=RequestsWebContentClient(),
            ),
            phenotype_fetcher=PyHPOClient(),
            observation_finder=ObservationFinder(
                llm_client=OpenAIClient(),
                variant_factory=HGVSVariantFactory(
                    mutalyzer_client=MutalyzerClient(
                        web_client=RequestsWebContentClient(
                            WebClientSettings(
                                no_raise_codes=[422],
                            )
                        )
                    ),
                    ncbi_lookup_client=NcbiLookupClient(
                        web_client=RequestsWebContentClient(
                            WebClientSettings(
                                status_code_translator=get_ncbi_response_translator()
                            )
                        )
                    ),
                    refseq_client=RefSeqLookupClient(
                        web_client=RequestsWebContentClient(
                            WebClientSettings(
                                status_code_translator=get_ncbi_response_translator()
                            )
                        )
                    ),
                ),
                variant_comparator=HGVSVariantComparator(),
            ),
        )
        self._writer = JSONOutputWriter()

    def execute(self) -> None:
        # Get the papers that match this query.
        papers = self._library.get_papers({"pmid": self._pmid})
        assert len(papers) == 1
        logger.info(f"Found {len(papers)} papers for pmid: {self._pmid}")
        output_file = self._writer.write(
            self._extractor.extract(papers[0], self._gene_symbol)
>>>>>>> 897a9b3455bfa525248463ac6e607e56b329c189
        )
        self._extractor = PromptBasedContentExtractor(
            fields=[
                "evidence_id",
                "gene",
                "paper_id",
                "hgvs_c",
                "hgvs_p",
                "paper_variant",
                "transcript",
                "validation_error",
                "gnomad_frequency",
                "individual_id",
                "phenotype",
                "zygosity",
                "variant_inheritance",
                "variant_type",
                "study_type",
                "source_type",
                "engineered_cells",
                "patient_cells_tissues",
                "animal_model",
                "citation",
                "link",
                "paper_title",
            ],
            llm_client=OpenAIClient(),
            phenotype_searcher=WebHPOClient(
                web_client=RequestsWebContentClient(),
            ),
            phenotype_fetcher=PyHPOClient(),
            observation_finder=ObservationFinder(
                llm_client=OpenAIClient(),
                variant_factory=HGVSVariantFactory(
                    mutalyzer_client=MutalyzerClient(
                        web_client=RequestsWebContentClient(
                            WebClientSettings(
                                no_raise_codes=[422],
                            )
                        )
                    ),
                    ncbi_lookup_client=self._ncbi_lookup_client,
                    refseq_client=RefSeqLookupClient(
                        web_client=RequestsWebContentClient(
                            WebClientSettings(
                                status_code_translator=get_ncbi_response_translator()
                            )
                        )
                    ),
                ),
                variant_comparator=HGVSVariantComparator(),
            ),
        )

    def execute(self) -> Sequence[Dict[str, str]]:
        paper = self._ncbi_lookup_client.fetch(self._pmid, include_fulltext=True)
        if not paper:
            raise RuntimeError(f"pmid {self._pmid} not found")
        return self._extractor.extract(paper, self._gene_symbol)
