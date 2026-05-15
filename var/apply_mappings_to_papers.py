import csv

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


# Read training_papers.csv
input_file = 'training_papers.csv'
output_file = 'training_papers_standardized.csv'

rows = []

with open(input_file, 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        # Apply paper type mapping
        if 'Type of paper (informal)' in row:
            row['Type of paper (informal)'] = apply_paper_type_mapping(
                row['Type of paper (informal)']
            )

        # Apply testing method mappings
        for field in ['Testing method 1', 'Testing method 2']:
            if field in row:
                row[field] = apply_testing_method_mapping(row[field])

        rows.append(row)

# Write standardized output
with open(output_file, 'w') as f:
    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)

print(f'Created {output_file}')
print(f'Papers: {len(rows)}')
