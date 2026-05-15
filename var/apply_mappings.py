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

    # Check if it's a long description (probably misplaced)
    if len(method) > 50:
        return method  # Return as-is, will be flagged

    if method in TESTING_METHODS_MAPPING:
        return TESTING_METHODS_MAPPING[method]
    else:
        return method


# Read training data
input_file = 'training_raw.csv'
output_file = 'training_standardized.csv'

rows = []
issues = []

with open(input_file, 'r') as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader, start=2):  # Start at 2 (header is 1)
        original = dict(row)

        # Apply paper type mapping
        if 'Type of paper (informal)' in row:
            row['Type of paper (informal)'] = apply_paper_type_mapping(
                row['Type of paper (informal)']
            )

        # Apply testing method mappings
        for field in ['Testing method 1', 'Testing method 2']:
            if field in row:
                original_method = row[field]
                converted_method = apply_testing_method_mapping(original_method)
                row[field] = converted_method

                # Flag long descriptions
                if len(original_method.strip()) > 50:
                    issues.append(
                        {
                            'pmid': row.get('PMID', 'Unknown'),
                            'field': field,
                            'issue': 'Long description in testing method field',
                            'value': original_method[:80] + '...',
                        }
                    )

        rows.append(row)

# Write standardized output
with open(output_file, 'w') as f:
    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)

print(f'Created {output_file}\n')

# Summary of changes
print('MAPPING APPLIED:')
print('=' * 100)
print('\nPaper Type Mapping:')
for training, api in sorted(PAPER_TYPE_MAPPING.items()):
    print(f"  '{training}' → '{api}'")

print('\nTesting Methods Mapping:')
for training, api in sorted(TESTING_METHODS_MAPPING.items()):
    print(f"  '{training}' → '{api}'")

# Count changes
paper_type_changes = 0
testing_method_changes = 0

with open(input_file, 'r') as f_in:
    reader_in = csv.DictReader(f_in)
    rows_in = list(reader_in)

with open(output_file, 'r') as f_out:
    reader_out = csv.DictReader(f_out)
    rows_out = list(reader_out)

for in_row, out_row in zip(rows_in, rows_out):
    if in_row.get('Type of paper (informal)', '') != out_row.get(
        'Type of paper (informal)', ''
    ):
        paper_type_changes += 1
    for field in ['Testing method 1', 'Testing method 2']:
        if in_row.get(field, '') != out_row.get(field, ''):
            testing_method_changes += 1

print(f'\nChanges Applied:')
print(f'  Paper type conversions: {paper_type_changes} rows')
print(f'  Testing method conversions: {testing_method_changes} rows')

if issues:
    print(
        f'\nData Quality Issues Found: {len(issues)} rows have long descriptions in testing method fields'
    )
    for issue in issues[:5]:  # Show first 5
        print(f'  PMID {issue["pmid"]}, {issue["field"]}: {issue["value"]}')
    if len(issues) > 5:
        print(f'  ... and {len(issues) - 5} more')
