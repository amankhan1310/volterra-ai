/**
 * The numbers behind a chart, as a table for screen readers (plan §7, accessibility). It is
 * visually hidden, so the page looks exactly like the prototype. The wrapper carries the hiding:
 * a table treats `height` as a minimum, so a hidden 320-row table would still lay out thousands
 * of pixels tall and make the whole document scroll into empty space.
 */
export function ChartDataTable({
  caption,
  columns,
  rows,
}: {
  caption: string;
  columns: readonly string[];
  rows: readonly (readonly (string | number)[])[];
}) {
  return (
    <div className="visually-hidden">
      <table>
        <caption>{caption}</caption>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c} scope="col">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {row.map((cell, j) => (
                <td key={j}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
