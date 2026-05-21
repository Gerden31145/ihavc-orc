export interface TableExportData {
  headers: string[]
  rows: string[][]
}

/** RFC 4180 转义单个单元格 */
export function escapeCsvCell(value: unknown): string {
  const str = value == null ? '' : String(value)
  if (/[",\r\n]/.test(str)) {
    return `"${str.replace(/"/g, '""')}"`
  }
  return str
}

function formatCsvRow(cells: unknown[], colCount: number): string {
  const padded = [...cells]
  while (padded.length < colCount) padded.push('')
  return padded.slice(0, colCount).map(escapeCsvCell).join(',')
}

function normalizeHeaderCell(value: unknown): string {
  return String(value ?? '')
    .trim()
    .replace(/\s+/g, '')
    .toLowerCase()
}

function joinedHeaderText(cells: string[]): string {
  return cells.map(normalizeHeaderCell).filter(Boolean).join('')
}

const SCORE_TABLE_HEADER_KEYWORDS = [
  '院校',
  '专业组',
  '专业名称',
  '投档数',
  '投档线',
  '投档最低',
  '录取数',
  '录取最低',
  '最低排位',
  '最低分'
]

/** 根据单元格文案判断是否为高考表头行 */
export function isLikelyScoreTableHeaderRow(row: string[]): boolean {
  if (!row?.length) return false
  let labelHits = 0
  for (const cell of row) {
    const t = String(cell ?? '').trim()
    if (!t || t.length > 24) continue
    if (SCORE_TABLE_HEADER_KEYWORDS.some(kw => t.includes(kw))) labelHits++
  }
  if (labelHits < 3) return false
  const numericCells = row.filter(c => /^\d{3,}$/.test(String(c).trim())).length
  return numericCells <= 1
}

function hasNonEmptyHeader(headers: string[]): boolean {
  return headers.some(h => String(h ?? '').trim())
}

/** 若 headers 为空，从 rows 首行提升表头 */
export function ensureTableHeaders(table: TableExportData): TableExportData {
  let headers = [...table.headers]
  let rows = table.rows.map(r => [...(r ?? [])])

  if (!hasNonEmptyHeader(headers) && rows.length > 0) {
    const candidate = rows[0]
    if (isLikelyScoreTableHeaderRow(candidate)) {
      headers = candidate
      rows = rows.slice(1)
    }
  }
  return { headers, rows }
}

/** 检测横向重复表头（至少重复 2 次才判定） */
export function detectRepeatedHeaderPattern(headers: string[]): {
  repeated: boolean
  patternLength: number
} {
  const normalized = headers.map(normalizeHeaderCell)
  if (normalized.length < 2) {
    return { repeated: false, patternLength: normalized.length }
  }

  const maxLen = Math.floor(normalized.length / 2)
  for (let plen = 1; plen <= maxLen; plen++) {
    if (normalized.length % plen !== 0) continue
    const pattern = normalized.slice(0, plen)
    const repeats = normalized.length / plen
    if (repeats < 2) continue

    let ok = true
    for (let i = 1; i < repeats; i++) {
      const seg = normalized.slice(i * plen, (i + 1) * plen)
      for (let j = 0; j < plen; j++) {
        if (pattern[j] !== seg[j]) {
          ok = false
          break
        }
      }
      if (!ok) break
    }
    if (ok) return { repeated: true, patternLength: plen }
  }
  return { repeated: false, patternLength: headers.length }
}

/** 判断数据行是否与已知表头重复（严格匹配，不用启发式误删） */
export function isDuplicateHeaderRow(row: string[], referenceHeaders: string[]): boolean {
  if (!referenceHeaders.length || !row?.length) return false

  const ref = referenceHeaders.map(normalizeHeaderCell).filter(Boolean)
  if (!ref.length) return false

  const cells = row.map(normalizeHeaderCell)
  const compareLen = Math.min(ref.length, cells.length)
  if (compareLen > 0) {
    let matched = 0
    for (let i = 0; i < compareLen; i++) {
      if (ref[i] === cells[i]) matched++
    }
    if (matched / ref.length >= 0.75) return true
  }

  const refJoined = joinedHeaderText(referenceHeaders)
  const rowJoined = joinedHeaderText(row)
  if (rowJoined && refJoined) {
    if (rowJoined === refJoined) return true
    const shorter = Math.min(rowJoined.length, refJoined.length)
    const longer = Math.max(rowJoined.length, refJoined.length)
    if (
      shorter > 0 &&
      longer > 0 &&
      shorter / longer >= 0.85 &&
      (refJoined.includes(rowJoined) || rowJoined.includes(refJoined))
    ) {
      return true
    }
  }

  return false
}

/** 去掉 rows 中与表头重复的行 */
export function dataRowsWithoutHeader(table: TableExportData, referenceHeaders?: string[]): string[][] {
  const refs: string[][] = []
  if (referenceHeaders?.length && hasNonEmptyHeader(referenceHeaders)) {
    refs.push(referenceHeaders)
  }
  if (table.headers.length && hasNonEmptyHeader(table.headers)) {
    refs.push(table.headers)
  }
  if (!refs.length) return table.rows

  return table.rows.filter(row => !refs.some(h => isDuplicateHeaderRow(row ?? [], h)))
}

/** 导出前规范化：恢复表头、横向去重、去掉嵌入表头行 */
export function normalizeTableForExport(table: TableExportData): TableExportData {
  let { headers, rows } = ensureTableHeaders(table)

  const { repeated, patternLength } = detectRepeatedHeaderPattern(headers)
  if (repeated && patternLength > 0) {
    headers = headers.slice(0, patternLength)
    rows = rows.map(row =>
      (row?.length ?? 0) >= patternLength ? row.slice(0, patternLength) : row ?? []
    )
  }

  rows = dataRowsWithoutHeader({ headers, rows }, headers)
  return { headers, rows }
}

export interface TableCsvMeta {
  headers: string[]
  values: string[]
}

export function tableToCsv(table: TableExportData, meta?: TableCsvMeta): string {
  const normalized = normalizeTableForExport(table)
  const metaHeaders = meta?.headers ?? []
  const metaValues = meta?.values ?? []

  const dataHeaders = hasNonEmptyHeader(normalized.headers)
    ? normalized.headers
    : normalized.rows.length && isLikelyScoreTableHeaderRow(normalized.rows[0])
      ? normalized.rows[0]
      : []

  let dataRows = normalized.rows
  if (!hasNonEmptyHeader(normalized.headers) && dataHeaders.length && dataRows[0] === dataHeaders) {
    dataRows = dataRows.slice(1)
  }

  const headerRow = [...metaHeaders, ...dataHeaders]
  const colCount = headerRow.length
  if (!colCount) return ''

  const lines: string[] = [formatCsvRow(headerRow, colCount)]
  const dataColCount = dataHeaders.length

  for (const row of dataRows) {
    const cells = [...metaValues, ...(row ?? [])]
    while (cells.length < metaHeaders.length + dataColCount) cells.push('')
    lines.push(formatCsvRow(cells, colCount))
  }

  return lines.join('\r\n')
}

export interface TableCsvSection {
  metaValues?: string[]
  table: TableExportData
}

/** 多表合并为单个 CSV，仅保留一行表头 */
export function mergeMultipleTablesCsv(
  sections: TableCsvSection[],
  metaHeaders: string[] = []
): string {
  const valid = sections
    .map(s => ({ ...s, table: normalizeTableForExport(s.table) }))
    .filter(s => hasNonEmptyHeader(s.table.headers) || s.table.rows.length > 0)
  if (!valid.length) return ''

  const dataHeaders =
    valid.find(s => hasNonEmptyHeader(s.table.headers))?.table.headers ?? []

  if (!dataHeaders.length) return ''

  const headerRow = [...metaHeaders, ...dataHeaders]
  const colCount = Math.max(
    headerRow.length,
    metaHeaders.length +
      Math.max(
        dataHeaders.length,
        ...valid.map(s =>
          Math.max(s.table.headers.length, ...s.table.rows.map(r => r?.length ?? 0), 0)
        )
      )
  )
  while (headerRow.length < colCount) {
    headerRow.push(`列${headerRow.length - metaHeaders.length + 1}`)
  }

  const lines: string[] = [formatCsvRow(headerRow, colCount)]

  for (const section of valid) {
    const meta = [...(section.metaValues ?? [])]
    while (meta.length < metaHeaders.length) meta.push('')
    for (const row of section.table.rows) {
      const cells = [...meta.slice(0, metaHeaders.length), ...(row ?? [])]
      while (cells.length < colCount) cells.push('')
      lines.push(formatCsvRow(cells, colCount))
    }
  }
  return lines.join('\r\n')
}

export function mergeSplitTablesCsv(
  tables: TableExportData[],
  baseMeta?: TableCsvMeta
): string {
  const metaHeaders = [...(baseMeta?.headers ?? []), '子表格']
  const baseValues = baseMeta?.values ?? []
  const sections: TableCsvSection[] = tables.map((table, t) => ({
    metaValues: [...baseValues, `表格${t + 1}`],
    table: normalizeTableForExport(table)
  }))
  return mergeMultipleTablesCsv(sections, metaHeaders)
}

export function sanitizeFilename(name: string): string {
  return name.replace(/[<>:"/\\|?*\x00-\x1f]/g, '_').replace(/\s+/g, '_').slice(0, 80)
}

export function buildExportFilename(base: string, ext = 'csv'): string {
  const stamp = new Date().toISOString().slice(0, 19).replace(/[-:T]/g, '')
  return `${sanitizeFilename(base)}_${stamp}.${ext}`
}

export function downloadCsv(csvContent: string, filename: string): void {
  const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename.endsWith('.csv') ? filename : `${filename}.csv`
  link.click()
  URL.revokeObjectURL(url)
}
