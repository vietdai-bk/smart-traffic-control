import { Fragment, type ReactNode } from "react";

/** Trình hiển thị markdown tối giản cho phản hồi LLM: tiêu đề, danh sách, bảng, **đậm**, `code`. Không dùng HTML thô. */
function inline(text: string, key: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const t = m[0];
    if (t.startsWith("**")) out.push(<strong key={`${key}-${i++}`} className="font-semibold text-ink">{t.slice(2, -2)}</strong>);
    else if (t.startsWith("`")) out.push(<code key={`${key}-${i++}`} className="num rounded bg-panel px-1 py-0.5 text-[0.92em]">{t.slice(1, -1)}</code>);
    else out.push(<em key={`${key}-${i++}`}>{t.slice(1, -1)}</em>);
    last = m.index + t.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

const cells = (row: string) => row.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());

export function Markdown({ text, className }: { text: string; className?: string }) {
  const lines = text.replace(/\r/g, "").split("\n");
  const blocks: ReactNode[] = [];
  let i = 0;
  let k = 0;
  while (i < lines.length) {
    const line = lines[i];
    const key = `b${k++}`;
    if (!line.trim()) {
      i++;
      continue;
    }
    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) {
      const lvl = h[1].length;
      const cls =
        lvl === 1 ? "mt-1 text-lg font-bold text-ink" : lvl === 2 ? "mt-4 border-b border-line/60 pb-1 text-[15px] font-bold text-ink" : "mt-3 text-[13px] font-bold text-ink";
      blocks.push(<div key={key} className={cls}>{inline(h[2], key)}</div>);
      i++;
      continue;
    }
    if (/^\s*>/.test(line)) {
      const quote: string[] = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) quote.push(lines[i++].replace(/^\s*>\s?/, ""));
      blocks.push(
        <blockquote key={key} className="my-2 border-l-[3px] border-[#8B5CF6]/60 bg-[#8B5CF6]/5 py-1 pl-3 pr-2 text-ink-dim">
          {quote.map((q, j) => <div key={j}>{inline(q, `${key}${j}`)}</div>)}
        </blockquote>,
      );
      continue;
    }
    if (/^\s*(---|\*\*\*|___)\s*$/.test(line)) {
      blocks.push(<hr key={key} className="my-3 border-line/60" />);
      i++;
      continue;
    }
    if (/^\s*\|/.test(line) && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
      const head = cells(line);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && /^\s*\|/.test(lines[i])) rows.push(cells(lines[i++]));
      blocks.push(
        <div key={key} className="my-2 overflow-x-auto rounded-ctl border border-line/70">
          <table className="w-full text-xs">
            <thead className="bg-panel/50">
              <tr>{head.map((c, j) => <th key={j} className="px-2.5 py-1.5 text-left font-semibold text-ink">{inline(c, `${key}h${j}`)}</th>)}</tr>
            </thead>
            <tbody>
              {rows.map((r, ri) => (
                <tr key={ri} className="border-t border-line/50">
                  {r.map((c, j) => <td key={j} className="num px-2.5 py-1.5 text-ink-dim">{inline(c, `${key}${ri}${j}`)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }
    if (/^\s*([-*•]|\d+[.)])\s+/.test(line)) {
      const ordered = /^\s*\d+[.)]/.test(line);
      const items: string[] = [];
      while (i < lines.length && /^\s*([-*•]|\d+[.)])\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*([-*•]|\d+[.)])\s+/, ""));
        i++;
      }
      const List = ordered ? "ol" : "ul";
      blocks.push(
        <List key={key} className={`my-1.5 space-y-1 pl-5 ${ordered ? "list-decimal" : "list-disc"} marker:text-ink-mute`}>
          {items.map((it, j) => <li key={j}>{inline(it, `${key}${j}`)}</li>)}
        </List>,
      );
      continue;
    }
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,4}\s|\s*[-*•]\s|\s*\d+[.)]\s|\s*\||\s*>)/.test(lines[i])) para.push(lines[i++]);
    if (!para.length) para.push(lines[i++]);
    blocks.push(
      <p key={key} className="my-1.5">
        {para.map((p, j) => (
          <Fragment key={j}>
            {j > 0 && <br />}
            {inline(p, `${key}${j}`)}
          </Fragment>
        ))}
      </p>,
    );
  }
  return <div className={`text-[13px] leading-relaxed text-ink-dim ${className ?? ""}`}>{blocks}</div>;
}
