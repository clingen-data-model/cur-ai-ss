/* The "Quick run" box every re-run dialog offers: run this task, and the
 * tasks it triggers, on the deployment's cheaper extraction model
 * (EXTRACTION_BUDGET_MODEL; tasks.budget_model on the row). One component so
 * the four dialogs cannot drift into different wording. It never names a
 * model: curators choose between quick and thorough, and which models those
 * are is the deployment's business (CLAUDE.md, EXTRACTION_BUDGET_MODEL).
 * Unchecked by default, so a run is thorough unless someone opts out. */

export const QUICK_RUN_LABEL = 'Quick run'

export const QUICK_RUN_NOTE =
  'Faster and lower cost, for this task and the tasks it triggers. Less thorough on complex papers; good for a first look or a small change.'

export function QuickRunCheckbox({
  checked,
  onChange,
}: {
  checked: boolean
  onChange: (checked: boolean) => void
}) {
  return (
    <div className="space-y-1.5">
      <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          className="cursor-pointer"
        />
        {QUICK_RUN_LABEL}
      </label>
      <p className="text-xs text-muted-foreground">{QUICK_RUN_NOTE}</p>
    </div>
  )
}
