"""Who the paper reports on, and how they group into families.

The roster every later pass is keyed to, and on a cohort paper the largest
thing we ask for -- paper 92 has twenty-three patients in one table. It gets a
response to itself so that enumerating them is the only job in it.
"""

from lib.agents.paper_extraction._shared import READING_THE_PAPER, _pdf_part, _run
from lib.models.patient import PatientExtractionOutput

PATIENT_INSTRUCTIONS = f"""You are an expert clinical genetics curator reading one paper.

{READING_THE_PAPER}

List the individuals this paper reports on and group them into families. Their
demographics, phenotypes and genotypes are extracted separately -- do not attempt those
here. This pass has one job: the roster, complete.

PATIENTS AND FAMILIES
- Identify every individual the paper reports data about, including unaffected relatives --
  they carry the segregation evidence. What qualifies someone is that the paper reports
  something about them: a genotype, a phenotype, an affected or carrier status, a test
  result. A relative shown only as an unannotated symbol in a figure, with nothing reported
  about them, is not a patient. Include the ones with findings even when the paper gives
  them no identifier of their own -- name those by relation to a patient it does name
  ("MMR63's unaffected sister"), never by a figure position alone. Where the paper describes
  several such relatives together -- "the parents were tested", "three unaffected siblings"
  -- return one patient for each of them, named individually ("F1:II.2's mother",
  "F1:II.2's father"). One entry standing for more than one person is never correct: it
  cannot carry a genotype, and segregation counts it once.
- Work through every place the paper names individuals, and start with its tables. A paper
  reporting a series or cohort lists its patients as table rows, one per individual, under
  the paper's own IDs -- enumerate every row of every such table, including rows under
  sub-headings, and do not stop at the ones discussed in the text. Twenty-three rows means
  twenty-three patients. A pedigree figure in the same paper usually illustrates one family
  out of that series; read it for relationships, sex and affected status, and for relatives
  the text does not name -- but it is never the roster on its own. Read such figures
  yourself: a family tree drawn only to arrange images by relative may label nobody, and
  unlabelled symbols are not patients you can name. Where a figure individual is a patient
  the paper names elsewhere, use that name, not the figure position, so one person does not
  become two.
- Proband: the primary affected individual through whom a family was ascertained. If none
  is named, the individual discussed in most detail is the proband; say so in the reasoning.
- Identifiers: the paper's own label exactly as written ("P1", "II-2", "TX-02", "Case 1"),
  preserving capitalisation; otherwise a descriptive label as written ("proband", "sister").
  Never a bare number. Where someone is only described by relation, name them relative to
  the proband ("Patient 2's brother"). For a single case report use "patient", proband.
- Skip individuals with no usable identifier, and skip aggregate statistics ("5 males").
  Do not extract authors, animal models or non-clinical mentions.
- Every patient belongs to exactly one family, named by family_identifier, which must match
  the identifier of one of the families you return -- that field alone assigns them, so
  spell it identically in both places. Group by the paper's own labels, by pedigree
  structure, by relational language and by shared family history. An individual with no
  identified relatives gets their own singleton family. Never merge unrelated patients,
  never split one family in two, never leave a patient unassigned.
- Family labels: the paper's own ("Family 1", "FAM-001") exactly; otherwise number them in
  order of appearance. Record consanguinity per family."""


def _extract_patients_sync(
    paper_id: int, pdf_bytes: bytes
) -> PatientExtractionOutput | None:
    return _run(
        'patients',
        paper_id,
        PatientExtractionOutput,
        PATIENT_INSTRUCTIONS,
        [
            _pdf_part(paper_id, pdf_bytes),
            {'type': 'text', 'text': 'List every individual this paper reports on.'},
        ],
    )
