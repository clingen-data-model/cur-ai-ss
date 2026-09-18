// Hand-written following the shadcn DataTable pattern — not copied from the registry.
import * as React from 'react'
import {
  type ColumnDef,
  type ExpandedState,
  type SortingState,
  flexRender,
  getCoreRowModel,
  getExpandedRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table'
import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp, ChevronsUpDown } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'
import { ELLIPSIS, pageItems } from '@/lib/pagination'

interface DataTableProps<TData, TValue> {
  columns: ColumnDef<TData, TValue>[]
  data: TData[]
  filterPlaceholder?: string
  pageSize?: number
  renderSubComponent?: (props: { row: TData }) => React.ReactNode
  getRowCanExpand?: (row: TData) => boolean
  className?: string
  /** Stable row identity (e.g. a database id) instead of array index -- needed
   * when a caller drives `expanded` itself and has to key into it. */
  getRowId?: (row: TData) => string
  /** Controlled expansion, for a caller that opens a row from something other
   * than the row's own click (e.g. a specific cell's button). Uncontrolled
   * (internal state) when omitted. */
  expanded?: ExpandedState
  onExpandedChange?: React.Dispatch<React.SetStateAction<ExpandedState>>
  /** Clicking anywhere in the row toggles it expanded. Default true; a caller
   * with its own expand triggers (see `expanded` above) sets this false so a
   * stray click inside a cell doesn't also toggle the row. */
  expandOnRowClick?: boolean
}

export function DataTable<TData, TValue>({
  columns,
  data,
  filterPlaceholder = 'Filter...',
  pageSize = 10,
  renderSubComponent,
  getRowCanExpand,
  className,
  getRowId,
  expanded: expandedProp,
  onExpandedChange: onExpandedChangeProp,
  expandOnRowClick = true,
}: DataTableProps<TData, TValue>) {
  const [sorting, setSorting] = React.useState<SortingState>([])
  const [globalFilter, setGlobalFilter] = React.useState('')
  const [expandedState, setExpandedState] = React.useState<ExpandedState>({})
  const expanded = expandedProp ?? expandedState
  const onExpandedChange = onExpandedChangeProp ?? setExpandedState

  const table = useReactTable({
    data,
    columns,
    state: { sorting, globalFilter, expanded },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    onExpandedChange,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
    getRowCanExpand: getRowCanExpand ? (row) => getRowCanExpand(row.original) : undefined,
    getRowId: getRowId ? (row) => getRowId(row) : undefined,
    initialState: { pagination: { pageSize } },
  })

  const pageIndex = table.getState().pagination.pageIndex
  const pageCount = table.getPageCount()

  return (
    <div className={cn('space-y-2', className)}>
      <Input
        placeholder={filterPlaceholder}
        value={globalFilter}
        onChange={(e) => setGlobalFilter(e.target.value)}
        className="max-w-sm"
      />
      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <TableHead key={header.id} style={{ width: header.getSize() !== 150 ? header.getSize() : undefined }}>
                    {header.isPlaceholder ? null : header.column.getCanSort() ? (
                      <button
                        type="button"
                        className="flex items-center gap-1 cursor-pointer select-none"
                        onClick={header.column.getToggleSortingHandler()}
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {header.column.getIsSorted() === 'asc' ? (
                          <ChevronUp className="size-3.5" />
                        ) : header.column.getIsSorted() === 'desc' ? (
                          <ChevronDown className="size-3.5" />
                        ) : (
                          <ChevronsUpDown className="size-3.5 text-muted-foreground" />
                        )}
                      </button>
                    ) : (
                      flexRender(header.column.columnDef.header, header.getContext())
                    )}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.length ? (
              table.getRowModel().rows.map((row) => (
                <React.Fragment key={row.id}>
                  <TableRow
                    onClick={
                      expandOnRowClick && row.getCanExpand()
                        ? () => row.toggleExpanded()
                        : undefined
                    }
                    className={
                      expandOnRowClick && row.getCanExpand() ? 'cursor-pointer' : undefined
                    }
                  >
                    {row.getVisibleCells().map((cell) => (
                      <TableCell key={cell.id}>
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </TableCell>
                    ))}
                  </TableRow>
                  {row.getIsExpanded() && renderSubComponent && (
                    <TableRow className="hover:bg-transparent">
                      <TableCell colSpan={columns.length} className="p-0">
                        {renderSubComponent({ row: row.original })}
                      </TableCell>
                    </TableRow>
                  )}
                </React.Fragment>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={columns.length} className="h-24 text-center text-muted-foreground">
                  No results.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      <nav
        className="flex items-center justify-end gap-1"
        aria-label="Table pagination"
      >
        <Button
          variant="outline"
          size="icon-sm"
          aria-label="Previous page"
          onClick={() => table.previousPage()}
          disabled={!table.getCanPreviousPage()}
        >
          <ChevronLeft />
        </Button>
        {pageItems(pageIndex, pageCount).map((item, i) =>
          item === ELLIPSIS ? (
            // Keyed by position: the ellipses are interchangeable and there is
            // nothing stabler to key them by.
            <span
              key={`gap-${i}`}
              className="px-1 text-sm text-muted-foreground select-none"
              aria-hidden
            >
              &hellip;
            </span>
          ) : (
            <Button
              key={item}
              variant={item === pageIndex + 1 ? 'default' : 'outline'}
              size="icon-sm"
              aria-label={`Page ${item}`}
              aria-current={item === pageIndex + 1 ? 'page' : undefined}
              onClick={() => table.setPageIndex(item - 1)}
            >
              {item}
            </Button>
          ),
        )}
        <Button
          variant="outline"
          size="icon-sm"
          aria-label="Next page"
          onClick={() => table.nextPage()}
          disabled={!table.getCanNextPage()}
        >
          <ChevronRight />
        </Button>
      </nav>
    </div>
  )
}

export type { ColumnDef }
