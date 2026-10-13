#!/usr/bin/env python3
"""
Process training_raw.csv to generate pmid_variants.tsv.
Combines standardization mappings and variant extraction with field normalization.
"""

import csv
import re

# Paper Type Mapping
PAPER_TYPE_MAPPING = {
    'Case study/report': 'Case Study',
    'Case series': 'Case Series',
    'Case control': 'Case Control',
    'Cohort analysis': 'Cohort Analysis',
    'Other': 'Other',
    'Research': 'Research',
}

# Testing Methods Mapping
TESTING_METHODS_MAPPING = {
    'Sanger sequencing': 'Sanger Sequencing',
    'Exome sequencing': 'Exome Sequencing',
    'Genome sequencing': 'Genome Sequencing',
    'Next generation sequencing panels': 'Next-generation Sequencing Panels',
}


def apply_paper_type_mapping(types_str):
    """Apply terminology mapping to comma-separated paper types"""
    if not types_str.strip():
        return ''
    parts = [t.strip() for t in types_str.split(',')]
    converted_parts = []
    for part in parts:
        if part in PAPER_TYPE_MAPPING:
            converted_parts.append(PAPER_TYPE_MAPPING[part])
        else:
            converted_parts.append(part)
    return ', '.join(converted_parts)


def apply_testing_method_mapping(method_str):
    """Apply mapping to a single testing method"""
    if not method_str.strip():
        return ''
    method = method_str.strip()
    if method in TESTING_METHODS_MAPPING:
        return TESTING_METHODS_MAPPING[method]
    else:
        return method


def normalize_zygosity(zygosity: str) -> str:
    """Normalize zygosity: title case, standardize variations."""
    if not zygosity or zygosity.lower() == 'unknown':
        return 'Unknown'
    return zygosity.strip().title()


def normalize_moi(moi: str) -> str:
    """Normalize mode of inheritance: strip prefixes, title case."""
    if not moi:
        return ''
    moi = moi.strip().lower()
    # Remove prefixes
    moi = moi.replace('autosomal ', '').replace('x-linked ', '').strip()
    return moi.title()


# Read and process training_raw.csv
print('Reading training_raw.csv...')
with open('var/training_raw.csv', 'r') as f:
    reader = csv.DictReader(f)

    with open('var/pmid_variants.tsv', 'w') as out:
        out.write(
            'pmid\tgene\ttranscript\thgvsc\thgvsp\tproband_id\tvariant_type\tzygosity\tmode_of_inheritance\n'
        )

        for row in reader:
            pmid = row.get('PMID', '')
            gene = row.get('EvAgg Gene', '')
            transcript = row.get('Variant HGVS (transcript)', '').strip()
            hgvsc = row.get('Variant HGVS (c.)', '').strip()
            hgvsp = row.get('Variant HGVS (p.)', '').strip()
            proband_id = row.get('Proband ID', '').strip()
            variant_type = row.get('Variant type', '').strip()

            # Apply testing method standardization to variant type
            variant_type = apply_testing_method_mapping(variant_type)

            # Normalize zygosity and MOI
            zygosity = normalize_zygosity(row.get('Zygosity of variant', ''))
            moi = normalize_moi(row.get('Mode of inheritance', ''))

            if not pmid or not gene:
                continue

            # Special case for PMID 33531950: extract paper nomenclature variants
            if pmid == '33531950':
                # Extract variants that come before "nomenclature in paper"
                paper_vars_c = re.findall(
                    r'(c\.\S+?)\s*:\s*nomenclature in paper', hgvsc
                )
                paper_vars_p = re.findall(
                    r'(p\.\S+?)\s*:\s*nomenclature in paper', hgvsp
                )

                if paper_vars_c:
                    clean_transcript = transcript.replace(' (ClinVar transcript)', '')
                    for i, var_c in enumerate(paper_vars_c):
                        var_p = paper_vars_p[i] if i < len(paper_vars_p) else ''
                        out.write(
                            f'{pmid}\t{gene}\t{clean_transcript}\t{var_c}\t{var_p}\t{proband_id}\t{variant_type}\t{zygosity}\t{moi}\n'
                        )
                continue

            # Default: output the row
            out.write(
                f'{pmid}\t{gene}\t{transcript}\t{hgvsc}\t{hgvsp}\t{proband_id}\t{variant_type}\t{zygosity}\t{moi}\n'
            )

print('Generated var/pmid_variants.tsv')
