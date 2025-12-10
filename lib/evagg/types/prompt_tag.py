"""Enum for prompt tags used throughout the application."""

from enum import Enum


class PromptTag(str, Enum):
    """Enum for all prompt tags used in LLM calls.

    This enum ensures type safety and consistency when tagging prompts
    for logging and tracking purposes.
    """

    # Default/Generic tags
    OBSERVATION = 'observation'
    PROMPT = 'prompt'

    # Observation-related tags
    OBSERVATION_CHECK_PATIENTS = 'observation__check_patients'
    OBSERVATION_FIND_PATIENTS = 'observation__find_patients'
    OBSERVATION_SPLIT_PATIENTS = 'observation__split_patients'
    OBSERVATION_FIND_VARIANTS = 'observation__find_variants'
    OBSERVATION_SPLIT_VARIANTS = 'observation__split_variants'
    OBSERVATION_FIND_GENOME_BUILD = 'observation__find_genome_build'
    OBSERVATION_LINK_ENTITIES = 'observation__link_entities'
    OBSERVATION_SANITY_CHECK = 'observation__sanity_check'
    OBSERVATION_CHECK_VARIANT_GENE_RELATIONSHIP = (
        'observation__check_variant_gene_relationship'
    )

    # Phenotype-related tags
    PHENOTYPES_CANDIDATES = 'phenotypes_candidates'
    PHENOTYPES_SIMPLIFY = 'phenotypes_simplify'
    PHENOTYPES_ALL = 'phenotypes_all'
    PHENOTYPES_OBSERVATION = 'phenotypes_observation'
    PHENOTYPES_ACRONYMS = 'phenotypes_acronyms'

    # Field extraction tags
    ZYGOSITY = 'zygosity'
    VARIANT_INHERITANCE = 'variant_inheritance'
    VARIANT_TYPE = 'variant_type'
    ENGINEERED_CELLS = 'engineered_cells'
    PATIENT_CELLS_TISSUES = 'patient_cells_tissues'
    ANIMAL_MODEL = 'animal_model'
    STUDY_TYPE = 'study_type'
