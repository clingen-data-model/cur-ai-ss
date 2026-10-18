import type { TaskType } from '@/api/generated/types.gen'

/** What each pipeline step is for, in one sentence, for the Rerun Agent dialog.
 *
 * Keyed by every task type a person can re-run ('General Paper Question' is
 * only ever created by the chat router), so adding a task type to the backend
 * is a type error here until it has a line of help text. */
export const TASK_HELP = {
  'PDF Parsing': 'Reads the PDF into the text, tables and figures that every other step works from.',
  'Paper Classifier':
    'Decides whether the paper has identifiable cases for this gene worth extracting; if not, the pipeline stops.',
  'Paper Metadata': 'Finds the title, authors, journal and year, and matches the paper to its PubMed record.',
  'Variant Extraction': 'Finds the genetic variants the paper reports, written as the paper writes them.',
  'Pedigree Description':
    "Looks through the paper's figures for a family tree and describes the relationships and affected status it shows.",
  'Patient Extraction':
    'Identifies each patient the paper describes, marks the probands and groups patients into families.',
  'Patient Demographics':
    "Fills in each patient's sex, ages, ancestry, affected status and relationship to the proband.",
  'Segregation Evidence Extraction':
    'Collects what the paper says about whether variants track with disease in each family, such as LOD scores.',
  'Segregation Analysis Computed':
    'Calculates segregation counts and points for each family from its extracted patients and variants.',
  'Variant Harmonization':
    'Converts each variant to standard coordinates and identifiers (HGVS, rsID, ClinGen allele) using ClinVar, the Allele Registry and VariantValidator.',
  'Variant Annotation': 'Adds predictions and scores, such as SpliceAI, to each harmonized variant.',
  'Patient Variant Occurrences': 'Links each patient to the variants they carry, with inheritance and testing details.',
  'Compound Het Evaluation':
    "Works out whether a patient's two variants sit on opposite copies of the gene (compound heterozygous).",
  'Phenotype Extraction': "Pulls each patient's clinical features out of the text as the paper describes them.",
  'HPO Linking': "Matches each patient's clinical features to standard HPO terms.",
  'Paper MONDO Linking': "Matches the paper's disease name to a MONDO disease term.",
  'Occurrence MONDO Linking': 'Matches the disease named for a patient-variant pair to a MONDO disease term.',
  'Extraction Verification':
    'Reviews the finished extraction and merges flags that raise the same decision more than once.',
} satisfies Record<Exclude<TaskType, 'General Paper Question'>, string>
