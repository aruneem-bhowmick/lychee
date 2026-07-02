import { visit } from 'unist-util-visit';
import { fromMarkdown } from 'mdast-util-from-markdown';
import type { VFile } from 'vfile';
import type { AlignType, Paragraph, PhrasingContent, Root, Table, TableCell, TableRow } from 'mdast';

const SEPARATOR_CELL = /^:?-+:?$/;

/**
 * Splits one raw table row into its cell strings on unescaped `|`
 * characters, treating any span between a pair of backticks as an
 * indivisible unit so that inline code containing a literal pipe (e.g. a
 * union type like `` `str|null` ``) is never split. Leading/trailing empty
 * cells produced by a row's outer pipes are dropped.
 *
 * @param line - One physical line of a pipe-table block.
 * @returns The row's trimmed cell strings.
 */
function splitRow(line: string): string[] {
  const cells: string[] = [];
  let current = '';
  let inCode = false;

  for (const ch of line) {
    if (ch === '`') {
      inCode = !inCode;
      current += ch;
      continue;
    }
    if (ch === '|' && !inCode) {
      cells.push(current);
      current = '';
      continue;
    }
    current += ch;
  }
  cells.push(current);

  if (cells.length && cells[0].trim() === '') cells.shift();
  if (cells.length && cells[cells.length - 1].trim() === '') cells.pop();

  return cells.map((cell) => cell.trim());
}

/**
 * Derives a column's alignment from its delimiter-row cell (e.g. `:---:`).
 *
 * @param separatorCell - A single trimmed cell from the delimiter row.
 * @returns The mdast alignment value for the column.
 */
function cellAlign(separatorCell: string): AlignType {
  const left = separatorCell.startsWith(':');
  const right = separatorCell.endsWith(':');
  if (left && right) return 'center';
  if (right) return 'right';
  if (left) return 'left';
  return null;
}

/**
 * Parses a single cell's raw markdown text into phrasing content, reusing
 * the standard markdown inline tokenizer so that code spans, emphasis, and
 * links inside cells render exactly as they would outside a table.
 *
 * @param text - The cell's raw (trimmed) markdown source.
 * @returns The parsed phrasing nodes for the cell.
 */
function parseCellPhrasing(text: string): PhrasingContent[] {
  if (!text) return [];
  const tree = fromMarkdown(text);
  const first = tree.children[0];
  return first && first.type === 'paragraph' ? (first as Paragraph).children : [];
}

/**
 * Builds an mdast `table` node from the physical lines of a pipe-table
 * block, or returns `null` when the lines don't form a valid table (no
 * delimiter row immediately following the header row).
 *
 * @param lines - The physical lines spanned by a candidate paragraph node.
 * @returns The constructed table node, or `null` if not a table.
 */
function buildTable(lines: string[]): Table | null {
  if (lines.length < 2) return null;

  const headerCells = splitRow(lines[0]);
  const separatorCells = splitRow(lines[1]);
  if (
    headerCells.length === 0 ||
    separatorCells.length === 0 ||
    !separatorCells.every((cell) => SEPARATOR_CELL.test(cell))
  ) {
    return null;
  }

  const align = separatorCells.map(cellAlign);

  const toRow = (rawCells: string[]): TableRow => ({
    type: 'tableRow',
    children: rawCells.map(
      (cellText): TableCell => ({
        type: 'tableCell',
        children: parseCellPhrasing(cellText),
      })
    ),
  });

  const bodyLines = lines.slice(2).filter((line) => line.trim() !== '');
  const rows = [toRow(headerCells), ...bodyLines.map((line) => toRow(splitRow(line)))];

  return { type: 'table', align, children: rows };
}

/**
 * Minimal, dependency-free stand-in for `remark-gfm`'s table support,
 * covering exactly the pipe-table syntax used across `docs/*.md` (GFM
 * features such as strikethrough, task lists, and autolinks are out of
 * scope since none of the source docs use them). A paragraph is recognized
 * as a table when its second physical line is a valid delimiter row; the
 * paragraph's original source text is recovered via its position offsets
 * and re-split into cells, whose content is re-parsed as markdown so
 * inline formatting inside cells still works. The resulting `table` /
 * `tableRow` / `tableCell` nodes render as real `<table>` HTML because
 * `mdast-util-to-hast` ships handlers for them independently of
 * `remark-gfm`.
 *
 * @returns A remark transformer that replaces table-shaped paragraphs with table nodes.
 */
export function remarkGfmTables() {
  return (tree: Root, file: VFile) => {
    const source = String(file);

    visit(tree, 'paragraph', (node: Paragraph, index, parent) => {
      if (index === undefined || !parent || !node.position) return;

      const start = node.position.start.offset;
      const end = node.position.end.offset;
      if (start === undefined || end === undefined) return;

      const raw = source.slice(start, end);
      const table = buildTable(raw.split('\n'));
      if (table) {
        parent.children[index] = table;
      }
    });
  };
}
