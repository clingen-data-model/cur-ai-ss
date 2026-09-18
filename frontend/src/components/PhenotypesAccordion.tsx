import { useQuery } from '@tanstack/react-query'
import { getPhenotypesPapersPaperIdPatientsPatientIdPhenotypesGet } from '@/api/generated'
import type { PhenotypeResp } from '@/api/generated/types.gen'
import { EvidencePopover, type EvidenceLike } from '@/components/EvidencePopover'
import { Badge } from '@/components/ui/badge'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import { cn } from 'cn'

const STALE_TIME = 5 * 60 * 1000

export function PhenotypesAccordion({ paperId, patientId }: { paperId: number; patientId: number }) {
  const phenotypesQuery = useQuery({
    queryKey: ['phenotypes', paperId, patientId],
    queryFn: () =>
      getPhenotypesPapersPaperIdPatientsPatientIdPhenotypesGet({
        path: { paper_id: paperId, patient_id: patientId },
      }),
    staleTime: STALE_TIME,
  })

  if (phenotypesQuery.isPending) {
    return <p className="text-sm text-muted-foreground">Loading phenotypes…</p>
  }

  if (!phenotypesQuery.data || phenotypesQuery.data.length === 0) {
    return <p className="text-sm text-muted-foreground">No phenotypes extracted.</p>
  }

  const phenotypes = phenotypesQuery.data

  return (
    <div className="space-y-2">
      <h4 className="text-sm font-semibold">Phenotypes</h4>
      <Accordion className="w-full">
        {phenotypes.map((phenotype) => (
          <AccordionItem key={phenotype.id}>
            <AccordionTrigger className="hover:no-underline">
              <div className="flex items-center gap-2 text-left">
                <span className="text-sm">{phenotype.concept}</span>
                {phenotype.negated && <Badge variant="outline" className="text-xs">Negated</Badge>}
                {phenotype.uncertain && <Badge variant="outline" className="text-xs">Uncertain</Badge>}
                {phenotype.family_history && <Badge variant="outline" className="text-xs">Family history</Badge>}
              </div>
            </AccordionTrigger>
            <AccordionContent>
              <div className="space-y-3 pt-2">
                {/* Evidence block */}
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <p className="text-xs font-medium text-muted-foreground">Evidence</p>
                    <EvidencePopover block={phenotype.concept_evidence} />
                  </div>
                  <p className="text-xs text-foreground">{phenotype.concept_evidence.value}</p>
                </div>

                {/* HPO match section */}
                <div className="space-y-1 border-t pt-2">
                  <p className="text-xs font-medium text-muted-foreground">HPO Match</p>
                  {phenotype.hpo.value ? (
                    <div className="space-y-1.5">
                      <div className="text-sm font-medium">{phenotype.hpo.value.name}</div>
                      <p className="text-xs text-muted-foreground">{phenotype.hpo.reasoning}</p>
                    </div>
                  ) : (
                    <p className="text-xs text-muted-foreground">No HPO match found</p>
                  )}
                </div>

                {/* Additional metadata */}
                {(phenotype.onset || phenotype.location || phenotype.severity || phenotype.modifier) && (
                  <div className="space-y-1 border-t pt-2">
                    <p className="text-xs font-medium text-muted-foreground">Additional Info</p>
                    <dl className="grid grid-cols-2 gap-1 text-xs">
                      {phenotype.onset && (
                        <>
                          <dt className="text-muted-foreground">Onset</dt>
                          <dd>{phenotype.onset}</dd>
                        </>
                      )}
                      {phenotype.location && (
                        <>
                          <dt className="text-muted-foreground">Location</dt>
                          <dd>{phenotype.location}</dd>
                        </>
                      )}
                      {phenotype.severity && (
                        <>
                          <dt className="text-muted-foreground">Severity</dt>
                          <dd>{phenotype.severity}</dd>
                        </>
                      )}
                      {phenotype.modifier && (
                        <>
                          <dt className="text-muted-foreground">Modifier</dt>
                          <dd>{phenotype.modifier}</dd>
                        </>
                      )}
                    </dl>
                  </div>
                )}
              </div>
            </AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>
    </div>
  )
}
