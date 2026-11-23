# Segregation

How a family's segregation evidence is counted and scored, and how the testing method recorded on an occurrence feeds the methodology that picks the points. The rules follow the ClinGen Gene-Disease Validity SOP v12 (pp. 29-36 and the appendix, pp. 64-66). `docs/pipeline.md` records why each rule changed.

```
Individual Variant Occurrences ─┐
                                ├─► Segregation Evidence Extraction ─► Segregation Analysis ─► points
Individual Demographics ────────┘     (reads the paper)                  (counts and scores, with tools)
```

## Two testing methods

"Testing method" means two different things here:

| | Occurrence | Segregation |
|---|---|---|
| Field | `testing_methods` on each individual-variant link | `sequencing_methodology` for each family |
| Enum | `TestingMethod`, 16 values, up to 2 per link | `SequencingMethodology`: Exome/Genome, All Genes in Linkage Region, Candidate Gene, Unknown |
| Question it answers | Was this person tested, and how? | Which row of the SOP points table does this family use? |
| Used for | Telling each member's genotype apart (tested or inferred) | Picking the points, together with the LOD |

## 1. Occurrences record how each link was established

The occurrence agent (`lib/agents/individual_variant_occurrence_agent.py`) fills `testing_methods` on each link:

| What the paper says | `testing_methods` | Meaning |
|---|---|---|
| Names a method ("Sanger confirmed…") | that method, e.g. `[Sanger Sequencing]` | tested |
| Reports a result without naming a method | `[Unknown]` | tested, method unstated |
| Nothing; the link is inferred (obligate carrier, a parent of a homozygous child) | `[]` | not tested |

`Genotyping` means a genotyping assay the paper names. It is never used as a placeholder. Links record carriers only. There is no negative link, so someone who tested negative has no link at all.

## 2. The handler turns links into a genotype per member

`family_info` is built in `lib/tasks/handlers.py`:

- **Segregating variants** (`segregation_basis`) are the proband's linked variants. If no proband has a link, the handler uses every variant linked in the family, and the agent flags it as inferred.
- **Genotype**, set per member for each segregating variant by `segregation_genotype`:
  - `tested carrier`: has a link that names a method.
  - `untested carrier`: has a link, but no method on it.
  - `no result`: has no link. This person may be untested, tested negative or missed, and the handler can't tell which.
- **`sequencing_methods`**: the proband's testing methods, with `source = 'the proband'`. In the fallback case it is every tested member's methods instead.
- No flags are passed in as input.

## 3. The evidence extractor reads the paper

`lib/agents/segregation_evidence_extractor.py`:

- **Published LOD**, taken as the paper gives it. A joint LOD across several families is given to each of them, with an ambiguous flag.
- **`has_unexplainable_non_segregations`** is true only when the paper reports an affected member who tested negative and doesn't explain it, and it cites that report. A missing link is never the evidence.

## 4. Segregation Analysis counts and scores

`lib/agents/segregation_analysis_computed_agent.py`. Each tool is a plain function behind a `@function_tool` wrapper, and the plain functions are what the tests call.

1. **`compute_scoring_method`** maps the family's inheritance values to Dominant, X-linked, Recessive or Semidominant. If the values are mostly Unknown or not Mendelian, the family gets no scoring method, isn't scored, and gets an unresolved flag.
   - For Semidominant, the agent counts the family both ways, then **`choose_semidominant_model`** picks whichever model meets its minimum, or the higher LOD if both do.
2. **Counting** uses genotypes only. The tools never see `testing_methods` here, only whether a link was tested:

   | Inheritance | Who counts |
   |---|---|
   | Dominant / X-linked | Affected tested carriers and obligate carriers (tested or not). Never an untested affected relative or anyone with `no result`. For X-linked, each daughter of an affected father is recorded as a certain segregation (`certain_segregations`). |
   | Recessive | The proband and their siblings only, with affected counted including the proband. Unaffected means a sibling who is a tested carrier of one variant. Siblings with `no result` are left out, a deliberately conservative choice that can only lower the LOD. If a compound-het proband has no tested-carrier parent, no siblings count and the family is flagged inferred. `affected_parent` is set when one parent is affected. |

3. **`calculate_lod_score`**:
   - If the paper gave a LOD, that value is used.
   - Dominant: segregations × log10(2).
   - X-linked: (segregations − certain) × log10(2).
   - Recessive: (affected − 1) × log10(4) + unaffected × log10(4/3), or (affected − 1 + unaffected) × log10(2) when a parent is affected.
4. **`check_minimum_criteria`** applies only to an estimated LOD: at least 4 segregations for Dominant or X-linked, at least 3 affected (including the proband) for Recessive, and no unexplainable non-segregations. A published LOD is exempt.
5. **`compute_sequencing_methodology`** maps the proband's `TestingMethod`s through `_TESTING_TO_METHODOLOGY` and takes the broadest:

   | Methodology | `TestingMethod` values that map to it |
   |---|---|
   | Exome/Genome | exome, genome, chromosomal microarray |
   | All Genes in Linkage Region | linkage analysis, homozygosity mapping |
   | Candidate Gene | Sanger, panels, PCR, Genotyping, MLPA and the other targeted assays |
   | Unknown | Unknown, Other, or no method at all |

   The broadest-wins order is Exome/Genome, then Linkage Region, then Candidate Gene, then Unknown (`_METHODOLOGY_BREADTH`). Relatives confirmed by Sanger therefore can't pull an exome proband down to Candidate Gene.

**`assign_points`** then takes the LOD and the methodology to the SOP points table. Points are per family.

## Known differences from the SOP

- **Summing:** the SOP sums LODs across families before assigning points. We don't; that's out of scope for now.
- **Not stored or editable:** the scoring method and methodology are worked out on each run, and a curator can't override them.
- **Not checked:** the SOP's conditions for using an estimated LOD at all (a rare, highly penetrant disorder with few phenocopies).
- **Phase:** for a compound het, one tested-carrier parent is enough to count siblings, which is slightly looser than strict proof that the variants are in trans.
