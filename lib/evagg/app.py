import logging

from lib.evagg.llm import OpenAIClient
from lib.evagg.content import (
    PromptBasedContentExtractor,
    HGVSVariantComparator,
    HGVSVariantFactory,
    ObservationFinder,
)
from lib.evagg.ref import (
    MutalyzerClient,
    NcbiLookupClient,
    WebHPOClient,
    PyHPOClient,
    RefSeqLookupClient,
    VepClient,
)
from lib.evagg.utils.web import RequestsWebContentClient, WebClientSettings
from lib.evagg.ref.ncbi import get_ncbi_response_translator
from typing import Dict, Sequence

logger = logging.getLogger(__name__)


class SinglePMIDApp:
    def __init__(
        self,
        pmid: str,
        gene_symbol: str,
    ) -> None:
        self._pmid = pmid
        self._gene_symbol = gene_symbol
        self._ncbi_lookup_client = NcbiLookupClient(
            web_client=RequestsWebContentClient(
                WebClientSettings(status_code_translator=get_ncbi_response_translator())
            )
        )
        self._vep_client = VepClient(
            web_client=RequestsWebContentClient(
                WebClientSettings(status_code_translator=get_ncbi_response_translator())
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

    def execute(self, override_cache: False) -> Sequence[Dict[str, str]]:
        paper = self._ncbi_lookup_client.fetch(self._pmid, include_fulltext=True)
        if not paper:
            raise RuntimeError(f"pmid {self._pmid} not found")
        extracted_fields = self._extractor.extract(paper, self._gene_symbol)
        return self._vep_client.enrich(extracted_fields)
