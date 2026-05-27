import type {
  FamilyResp,
  PatientResp,
  VariantResp,
  PatientVariantOccurrenceResp,
  PhenotypeResp,
} from '@/api/generated'
import type { ElementDefinition } from 'cytoscape'

export interface GraphElement {
  data: Record<string, unknown>
  classes?: string | string[]
}

export interface GraphElements {
  nodes: ElementDefinition[]
  edges: ElementDefinition[]
}

export function buildGraphElements(
  families: FamilyResp[],
  patients: PatientResp[],
  variants: VariantResp[],
  occurrences: PatientVariantOccurrenceResp[],
  phenotypes: PhenotypeResp[],
): ElementDefinition[] {
  const nodes: ElementDefinition[] = []
  const edges: ElementDefinition[] = []

  const familyMap = new Map(families.map((f) => [f.id, f]))
  const patientMap = new Map(patients.map((p) => [p.id, p]))
  const variantMap = new Map(variants.map((v) => [v.id, v]))

  // Family nodes
  for (const family of families) {
    nodes.push({
      data: {
        id: `family-${family.id}`,
        label: family.identifier,
        type: 'family',
      },
    })
  }

  // Patient nodes
  for (const patient of patients) {
    const isProband = patient.proband_status === 'Proband'
    nodes.push({
      data: {
        id: `patient-${patient.id}`,
        label: patient.identifier,
        type: 'patient',
        proband: isProband,
      },
      classes: isProband ? 'patient-proband' : 'patient-other',
    })

    // Patient → Family edge
    if (patient.family_id) {
      edges.push({
        data: {
          id: `pat-fam-${patient.id}-${patient.family_id}`,
          source: `patient-${patient.id}`,
          target: `family-${patient.family_id}`,
          type: 'patient-family',
        },
      })
    }
  }

  // Variant nodes
  for (const variant of variants) {
    nodes.push({
      data: {
        id: `variant-${variant.id}`,
        label: variant.variant_description || variant.variant || `Variant ${variant.id}`,
        type: 'variant',
      },
    })
  }

  // Patient → Variant edges (via occurrences)
  for (const occ of occurrences) {
    edges.push({
      data: {
        id: `occ-${occ.id}`,
        source: `patient-${occ.patient_id}`,
        target: `variant-${occ.variant_id}`,
        type: 'patient-variant',
        zygosity: occ.zygosity,
        inheritance: occ.inheritance,
      },
    })
  }

  // Phenotype nodes & Patient → Phenotype edges
  for (const pheno of phenotypes) {
    const phenoLabel = pheno.hpo?.value?.name || pheno.concept
    nodes.push({
      data: {
        id: `phenotype-${pheno.id}`,
        label: phenoLabel,
        type: 'phenotype',
        concept: pheno.concept,
        hpo: pheno.hpo?.value?.id,
        negated: pheno.negated,
        uncertain: pheno.uncertain,
      },
      classes: pheno.negated ? 'phenotype-negated' : 'phenotype-affirmed',
    })

    // Patient → Phenotype edge
    edges.push({
      data: {
        id: `pat-pheno-${pheno.patient_id}-${pheno.id}`,
        source: `patient-${pheno.patient_id}`,
        target: `phenotype-${pheno.id}`,
        type: 'patient-phenotype',
        negated: pheno.negated,
      },
      classes: pheno.negated ? 'edge-negated' : '',
    })
  }

  return [...nodes, ...edges]
}

export const cyStylesheet: Record<string, unknown>[] = [
  {
    selector: 'node',
    style: {
      'background-color': '#94a3b8',
      'border-width': 1,
      'border-color': '#64748b',
      label: 'data(label)',
      'font-size': 11,
      'text-valign': 'center',
      'text-halign': 'center',
      color: '#1e293b',
      'font-family': 'system-ui, -apple-system, sans-serif',
    },
  },

  // Family nodes
  {
    selector: 'node[type="family"]',
    style: {
      shape: 'roundrectangle',
      'background-color': '#6366f1',
      'border-color': '#4f46e5',
      'padding-relative-to': 'width',
      padding: 6,
    },
  },

  // Patient nodes
  {
    selector: 'node[type="patient"]',
    style: {
      shape: 'ellipse',
      'background-color': '#fb923c',
    },
  },

  {
    selector: 'node.patient-proband',
    style: {
      'background-color': '#f97316',
      'border-width': 2,
      'border-color': '#c2410c',
    },
  },

  // Variant nodes
  {
    selector: 'node[type="variant"]',
    style: {
      shape: 'diamond',
      'background-color': '#10b981',
      'border-color': '#059669',
    },
  },

  // Phenotype nodes
  {
    selector: 'node[type="phenotype"]',
    style: {
      shape: 'tag',
      'background-color': '#8b5cf6',
      'border-color': '#7c3aed',
    },
  },

  {
    selector: 'node.phenotype-negated',
    style: {
      'background-color': '#94a3b8',
      'border-width': 2,
      'border-style': 'dashed',
      'border-color': '#64748b',
    },
  },

  // Edges
  {
    selector: 'edge',
    style: {
      'line-color': '#cbd5e1',
      'target-arrow-color': '#cbd5e1',
      'target-arrow-shape': 'triangle',
      width: 1.5,
    },
  },

  {
    selector: 'edge[type="patient-family"]',
    style: {
      'line-color': '#a5b4fc',
      'target-arrow-color': '#a5b4fc',
    },
  },

  {
    selector: 'edge[type="patient-variant"]',
    style: {
      'line-color': '#6ee7b7',
      'target-arrow-color': '#6ee7b7',
    },
  },

  {
    selector: 'edge[type="patient-phenotype"]',
    style: {
      'line-color': '#d8b4fe',
      'target-arrow-color': '#d8b4fe',
    },
  },

  {
    selector: 'edge.edge-negated',
    style: {
      'line-style': 'dashed',
    },
  },
]
