/* All variant fields, editable where Streamlit allows it -- the SPA analog
 * of lib/ui/paper/variants.py's per-variant expander:
 * - Raw: extracted fields, read-only (Streamlit disables these too), with
 *   evidence popovers
 * - Harmonized: editable, backed by one shared reasoning block (no per-field
 *   evidence/note -- matches VariantUpdateRequest.harmonized_variant)
 * - Properties: editable, each with its own evidence + human-edit-note
 * - Annotations: read-only ClinVar/gnomAD/in-silico display
 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { TriangleAlert } from 'lucide-react'
import { updateVariantPapersPaperIdVariantsVariantIdPatch } from '@/api/generated'
import type { HarmonizedVariantUpdate, VariantResp, VariantUpdateRequest } from '@/api/generated/types.gen'
import {
  EditableSelectRow,
  EditableSwitchRow,
  ReadOnlyRow,
  SimpleTextRow,
} from '@/components/EditableField'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ScopedRerunButton } from '@/components/ScopedRerunButton'
import { VARIANT_TYPE_OPTIONS } from '@/lib/variantType'
import { gnomadUrl, clinGenUrl } from '@/lib/variantLinks'
import { formatGnomadPopulation } from '@/lib/gnomadPopulations'
import { harmonizationWarning } from '@/lib/harmonization'
import { apiErrorMessage } from '@/lib/apiError'

function formatAlleleCounts(ac?: number | null, an?: number | null): string {
  if (ac == null || an == null) return 'N/A'
  return `${ac.toLocaleString()} / ${an.toLocaleString()}`
}

export function VariantDetailPanel({ paperId, variant }: { paperId: number; variant: VariantResp }) {
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState('raw')
  const harmonized = variant.harmonized_variant.value
  const annotated = variant.annotated_variant
  const warning = harmonizationWarning(harmonized)

  const mutation = useMutation({
    mutationFn: (body: VariantUpdateRequest) =>
      updateVariantPapersPaperIdVariantsVariantIdPatch({
        path: { paper_id: paperId, variant_id: variant.id },
        body,
        throwOnError: true,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['variants', paperId] })
      // Editing a variant sets updated_by_user_id, which backs the papers
      // table's touched_by filter -- without this, "worked on by" stays
      // stale until the 5-minute staleTime lapses on its own.
      queryClient.invalidateQueries({ queryKey: ['papers'] })
    },
    onError: (error) => toast.error(apiErrorMessage(error, 'Failed to save variant')),
  })

  const save = (body: VariantUpdateRequest) => mutation.mutate(body)
  const saveHarmonized = (patch: HarmonizedVariantUpdate) => save({ harmonized_variant: patch })

  return (
    <div className="p-4 bg-muted/30">
      <h4 className="text-sm font-semibold mb-2">Variant</h4>
      {warning && (
        <Alert variant="destructive" className="mb-3 max-w-2xl">
          <TriangleAlert />
          <AlertDescription>{warning}</AlertDescription>
        </Alert>
      )}
      <Tabs
        value={activeTab}
        onValueChange={(value) => setActiveTab(value as string)}
        className="max-w-2xl"
      >
        <div className="flex items-center justify-between">
          <TabsList>
            <TabsTrigger value="raw">Raw</TabsTrigger>
            <TabsTrigger value="harmonized">Harmonized</TabsTrigger>
            <TabsTrigger value="properties">Properties</TabsTrigger>
            <TabsTrigger value="annotations">Annotations</TabsTrigger>
          </TabsList>
          {activeTab === 'harmonized' && (
            <ScopedRerunButton
              paperId={paperId}
              taskType="Variant Harmonization"
              scope={{ variant_id: variant.id }}
              label="Re-harmonize"
              description="Re-runs variant harmonization for this variant, overwriting the fields below."
            />
          )}
          {activeTab === 'annotations' && (
            <ScopedRerunButton
              paperId={paperId}
              taskType="Variant Annotation"
              scope={{ variant_id: variant.id }}
              label="Re-annotate"
              description="Re-runs variant annotation for this variant, overwriting the fields below."
            />
          )}
        </div>

        <TabsContent value="raw" className="pt-3">
          <ReadOnlyRow label="Variant Description" value={variant.variant_evidence.value ?? 'N/A'} evidence={variant.variant_evidence} />
          <ReadOnlyRow label="Transcript" value={variant.transcript_evidence.value ?? 'N/A'} evidence={variant.transcript_evidence} />
          <ReadOnlyRow label="Protein Accession" value={variant.protein_accession_evidence.value ?? 'N/A'} evidence={variant.protein_accession_evidence} />
          <ReadOnlyRow label="Genomic Accession" value={variant.genomic_accession_evidence.value ?? 'N/A'} evidence={variant.genomic_accession_evidence} />
          <ReadOnlyRow label="LRG Accession" value={variant.lrg_accession_evidence.value ?? 'N/A'} evidence={variant.lrg_accession_evidence} />
          <ReadOnlyRow label="Gene Accession" value={variant.gene_accession_evidence.value ?? 'N/A'} evidence={variant.gene_accession_evidence} />
          <ReadOnlyRow label="Genomic Coordinates" value={variant.genomic_coordinates_evidence.value ?? 'N/A'} evidence={variant.genomic_coordinates_evidence} />
          <ReadOnlyRow label="Genome Build" value={variant.genome_build_evidence.value ?? 'N/A'} evidence={variant.genome_build_evidence} />
          <ReadOnlyRow label="HGVS c." value={variant.hgvs_c_evidence.value ?? 'N/A'} evidence={variant.hgvs_c_evidence} />
          <ReadOnlyRow label="HGVS p." value={variant.hgvs_p_evidence.value ?? 'N/A'} evidence={variant.hgvs_p_evidence} />
          <ReadOnlyRow label="HGVS g." value={variant.hgvs_g_evidence.value ?? 'N/A'} evidence={variant.hgvs_g_evidence} />
          <ReadOnlyRow label="rsID" value={variant.rsid_evidence.value ?? 'N/A'} evidence={variant.rsid_evidence} />
          <ReadOnlyRow label="CAID" value={variant.caid_evidence.value ?? 'N/A'} evidence={variant.caid_evidence} />
        </TabsContent>

        <TabsContent value="harmonized" className="pt-3">
          {harmonized ? (
            <>
              <SimpleTextRow
                label="gnomAD-style coordinates"
                value={harmonized.gnomad_style_coordinates ?? ''}
                evidence={variant.harmonized_variant}
                onSave={(value) => saveHarmonized({ gnomad_style_coordinates: value || null })}
                caption={
                  harmonized.gnomad_style_coordinates && (
                    <a
                      href={gnomadUrl(harmonized.gnomad_style_coordinates)}
                      target="_blank"
                      rel="noreferrer"
                      className="text-xs text-primary hover:underline"
                    >
                      View in gnomAD
                    </a>
                  )
                }
              />
              <SimpleTextRow
                label="rsID"
                value={harmonized.rsid ?? ''}
                evidence={variant.harmonized_variant}
                onSave={(value) => saveHarmonized({ rsid: value || null })}
              />
              <SimpleTextRow
                label="CAID"
                value={harmonized.caid ?? ''}
                evidence={variant.harmonized_variant}
                onSave={(value) => saveHarmonized({ caid: value || null })}
                caption={
                  harmonized.caid && (
                    <a
                      href={clinGenUrl(harmonized.caid)}
                      target="_blank"
                      rel="noreferrer"
                      className="text-xs text-primary hover:underline"
                    >
                      View in ClinGen
                    </a>
                  )
                }
              />
              <SimpleTextRow
                label="HGVS c."
                value={harmonized.hgvs_c ?? ''}
                evidence={variant.harmonized_variant}
                onSave={(value) => saveHarmonized({ hgvs_c: value || null })}
              />
              <SimpleTextRow
                label="HGVS p."
                value={harmonized.hgvs_p ?? ''}
                evidence={variant.harmonized_variant}
                onSave={(value) => saveHarmonized({ hgvs_p: value || null })}
              />
              <SimpleTextRow
                label="HGVS g."
                value={harmonized.hgvs_g ?? ''}
                evidence={variant.harmonized_variant}
                onSave={(value) => saveHarmonized({ hgvs_g: value || null })}
              />
            </>
          ) : (
            <p className="text-sm text-muted-foreground">Harmonization not yet completed for this variant.</p>
          )}
        </TabsContent>

        <TabsContent value="properties" className="pt-3">
          <EditableSelectRow
            label="Variant Type"
            value={variant.variant_type}
            options={VARIANT_TYPE_OPTIONS}
            evidence={variant.variant_type_evidence}
            isSaving={mutation.isPending}
            onSave={(value, note) =>
              save({ variant_type: value, variant_type_human_edit_note: note })
            }
          />
          <EditableSwitchRow
            label="Functional Evidence Present"
            value={variant.functional_evidence}
            evidence={variant.functional_evidence_evidence}
            isSaving={mutation.isPending}
            onSave={(value, note) =>
              save({ functional_evidence: value, functional_evidence_human_edit_note: note })
            }
          />
          <EditableSwitchRow
            label="Main Focus of Study"
            value={variant.main_focus}
            evidence={variant.main_focus_evidence}
            isSaving={mutation.isPending}
            onSave={(value, note) => save({ main_focus: value, main_focus_human_edit_note: note })}
          />
        </TabsContent>

        <TabsContent value="annotations" className="pt-3">
          {!annotated ? (
            <p className="text-sm text-muted-foreground">Enrichment not yet completed for this variant.</p>
          ) : (
            <>
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mt-1 mb-1">ClinVar</p>
              <ReadOnlyRow label="Pathogenicity" value={annotated.pathogenicity ?? 'N/A'} />
              <ReadOnlyRow label="Submissions" value={annotated.submissions ?? 'N/A'} />
              <ReadOnlyRow label="Review Status" value={annotated.stars != null ? '⭐'.repeat(annotated.stars) || '0⭐' : 'N/A'} />

              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mt-3 mb-1">In Silico</p>
              <ReadOnlyRow label="REVEL" value={annotated.revel != null ? annotated.revel.toFixed(3) : 'N/A'} />
              <ReadOnlyRow label="AlphaMissense Class" value={annotated.alphamissense_class ?? 'N/A'} />
              <ReadOnlyRow
                label="AlphaMissense Score"
                value={annotated.alphamissense_score != null ? annotated.alphamissense_score.toFixed(3) : 'N/A'}
              />
              <ReadOnlyRow label="Exon" value={annotated.exon ?? 'N/A'} />
              <ReadOnlyRow label="VEP Consequence" value={annotated.vep_consequence ?? 'N/A'} />

              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mt-3 mb-1">gnomAD</p>
              <ReadOnlyRow label="Top-level AF" value={annotated.gnomad_top_level_af ?? 'N/A'} />
              <ReadOnlyRow
                label="Top-level Alleles (AC / AN)"
                value={formatAlleleCounts(annotated.gnomad_ac, annotated.gnomad_an)}
              />
              <ReadOnlyRow label="Popmax AF" value={annotated.gnomad_popmax_af ?? 'N/A'} />
              <ReadOnlyRow label="Popmax Population" value={formatGnomadPopulation(annotated.gnomad_popmax_population)} />
              <ReadOnlyRow
                label="Popmax Alleles (AC / AN)"
                value={formatAlleleCounts(annotated.gnomad_popmax_ac, annotated.gnomad_popmax_an)}
              />
            </>
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}
