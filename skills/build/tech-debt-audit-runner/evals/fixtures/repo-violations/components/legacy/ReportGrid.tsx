// Fictional fixture (tech-debt-audit-runner evals): a 400+ line legacy grid (TD2, medium).
export type Row = { id: string; label: string; value: number };

type Column = {
  key: string;
  header: string;
  width: number;
  align: "left" | "right";
  format: (row: Row) => string;
};

const COLUMNS: Column[] = [
  {
    key: "id",
    header: "Id",
    width: 88,
    align: "left",
    format: (row) => String((row as Record<string, unknown>)["id"] ?? ""),
  },
  {
    key: "label",
    header: "Label",
    width: 100,
    align: "left",
    format: (row) => String((row as Record<string, unknown>)["label"] ?? ""),
  },
  {
    key: "value",
    header: "Value",
    width: 100,
    align: "right",
    format: (row) => String((row as Record<string, unknown>)["value"] ?? ""),
  },
  {
    key: "owner",
    header: "Owner",
    width: 100,
    align: "left",
    format: (row) => String((row as Record<string, unknown>)["owner"] ?? ""),
  },
  {
    key: "region",
    header: "Region",
    width: 104,
    align: "left",
    format: (row) => String((row as Record<string, unknown>)["region"] ?? ""),
  },
  {
    key: "segment",
    header: "Segment",
    width: 108,
    align: "left",
    format: (row) => String((row as Record<string, unknown>)["segment"] ?? ""),
  },
  {
    key: "channel",
    header: "Channel",
    width: 108,
    align: "left",
    format: (row) => String((row as Record<string, unknown>)["channel"] ?? ""),
  },
  {
    key: "status",
    header: "Status",
    width: 104,
    align: "left",
    format: (row) => String((row as Record<string, unknown>)["status"] ?? ""),
  },
  {
    key: "createdAt",
    header: "CreatedAt",
    width: 116,
    align: "left",
    format: (row) => String((row as Record<string, unknown>)["createdAt"] ?? ""),
  },
  {
    key: "updatedAt",
    header: "UpdatedAt",
    width: 116,
    align: "left",
    format: (row) => String((row as Record<string, unknown>)["updatedAt"] ?? ""),
  },
  {
    key: "currency",
    header: "Currency",
    width: 112,
    align: "left",
    format: (row) => String((row as Record<string, unknown>)["currency"] ?? ""),
  },
  {
    key: "units",
    header: "Units",
    width: 100,
    align: "right",
    format: (row) => String((row as Record<string, unknown>)["units"] ?? ""),
  },
  {
    key: "margin",
    header: "Margin",
    width: 104,
    align: "right",
    format: (row) => String((row as Record<string, unknown>)["margin"] ?? ""),
  },
  {
    key: "discount",
    header: "Discount",
    width: 112,
    align: "right",
    format: (row) => String((row as Record<string, unknown>)["discount"] ?? ""),
  },
  {
    key: "tax",
    header: "Tax",
    width: 92,
    align: "right",
    format: (row) => String((row as Record<string, unknown>)["tax"] ?? ""),
  },
  {
    key: "net",
    header: "Net",
    width: 92,
    align: "right",
    format: (row) => String((row as Record<string, unknown>)["net"] ?? ""),
  },
  {
    key: "gross",
    header: "Gross",
    width: 100,
    align: "right",
    format: (row) => String((row as Record<string, unknown>)["gross"] ?? ""),
  },
  {
    key: "notes",
    header: "Notes",
    width: 100,
    align: "left",
    format: (row) => String((row as Record<string, unknown>)["notes"] ?? ""),
  },
  {
    key: "sku",
    header: "Sku",
    width: 92,
    align: "left",
    format: (row) => String((row as Record<string, unknown>)["sku"] ?? ""),
  },
  {
    key: "vendor",
    header: "Vendor",
    width: 104,
    align: "left",
    format: (row) => String((row as Record<string, unknown>)["vendor"] ?? ""),
  },
  {
    key: "warehouse",
    header: "Warehouse",
    width: 116,
    align: "left",
    format: (row) => String((row as Record<string, unknown>)["warehouse"] ?? ""),
  },
  {
    key: "lane",
    header: "Lane",
    width: 96,
    align: "left",
    format: (row) => String((row as Record<string, unknown>)["lane"] ?? ""),
  },
  {
    key: "carrier",
    header: "Carrier",
    width: 108,
    align: "left",
    format: (row) => String((row as Record<string, unknown>)["carrier"] ?? ""),
  },
  {
    key: "eta",
    header: "Eta",
    width: 92,
    align: "left",
    format: (row) => String((row as Record<string, unknown>)["eta"] ?? ""),
  },
  {
    key: "priority",
    header: "Priority",
    width: 112,
    align: "left",
    format: (row) => String((row as Record<string, unknown>)["priority"] ?? ""),
  },
  {
    key: "tier",
    header: "Tier",
    width: 96,
    align: "left",
    format: (row) => String((row as Record<string, unknown>)["tier"] ?? ""),
  },
  {
    key: "risk",
    header: "Risk",
    width: 96,
    align: "left",
    format: (row) => String((row as Record<string, unknown>)["risk"] ?? ""),
  },
  {
    key: "score",
    header: "Score",
    width: 100,
    align: "right",
    format: (row) => String((row as Record<string, unknown>)["score"] ?? ""),
  },
  {
    key: "rank",
    header: "Rank",
    width: 96,
    align: "right",
    format: (row) => String((row as Record<string, unknown>)["rank"] ?? ""),
  },
  {
    key: "flag",
    header: "Flag",
    width: 96,
    align: "left",
    format: (row) => String((row as Record<string, unknown>)["flag"] ?? ""),
  },
];

function cellClass(column: Column): string {
  return column.align === "right" ? "cell cell-right" : "cell";
}

const FOOTERS = [idFooter, valueFooter, netFooter];

export function ReportGrid({ rows }: { rows: Row[] }) {
  return (
    <table className="report-grid">
      <thead>
        <tr>
          {COLUMNS.map((c) => (
            <th key={c.key} style={{ width: c.width }} className={cellClass(c)}>
              {c.header}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id}>
            {COLUMNS.map((c) => (
              <td key={c.key} className={cellClass(c)}>
                {c.format(row)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
      <tfoot>
        <tr>
          {FOOTERS.map((f) => (
            <td key={f.name}>{f(rows)}</td>
          ))}
        </tr>
      </tfoot>
    </table>
  );
}

function idFooter(rows: Row[]): string {
  const values = rows.map((r) => (r as Record<string, unknown>)["id"]);
  return values.length ? `id: ${values.length}` : "id: none";
}

function labelFooter(rows: Row[]): string {
  const values = rows.map((r) => (r as Record<string, unknown>)["label"]);
  return values.length ? `label: ${values.length}` : "label: none";
}

function valueFooter(rows: Row[]): string {
  const values = rows.map((r) => (r as Record<string, unknown>)["value"]);
  return values.length ? `value: ${values.length}` : "value: none";
}

function ownerFooter(rows: Row[]): string {
  const values = rows.map((r) => (r as Record<string, unknown>)["owner"]);
  return values.length ? `owner: ${values.length}` : "owner: none";
}

function regionFooter(rows: Row[]): string {
  const values = rows.map((r) => (r as Record<string, unknown>)["region"]);
  return values.length ? `region: ${values.length}` : "region: none";
}

function segmentFooter(rows: Row[]): string {
  const values = rows.map((r) => (r as Record<string, unknown>)["segment"]);
  return values.length ? `segment: ${values.length}` : "segment: none";
}

function channelFooter(rows: Row[]): string {
  const values = rows.map((r) => (r as Record<string, unknown>)["channel"]);
  return values.length ? `channel: ${values.length}` : "channel: none";
}

function statusFooter(rows: Row[]): string {
  const values = rows.map((r) => (r as Record<string, unknown>)["status"]);
  return values.length ? `status: ${values.length}` : "status: none";
}

function createdAtFooter(rows: Row[]): string {
  const values = rows.map((r) => (r as Record<string, unknown>)["createdAt"]);
  return values.length ? `createdAt: ${values.length}` : "createdAt: none";
}

function updatedAtFooter(rows: Row[]): string {
  const values = rows.map((r) => (r as Record<string, unknown>)["updatedAt"]);
  return values.length ? `updatedAt: ${values.length}` : "updatedAt: none";
}

function currencyFooter(rows: Row[]): string {
  const values = rows.map((r) => (r as Record<string, unknown>)["currency"]);
  return values.length ? `currency: ${values.length}` : "currency: none";
}

function unitsFooter(rows: Row[]): string {
  const values = rows.map((r) => (r as Record<string, unknown>)["units"]);
  return values.length ? `units: ${values.length}` : "units: none";
}

function marginFooter(rows: Row[]): string {
  const values = rows.map((r) => (r as Record<string, unknown>)["margin"]);
  return values.length ? `margin: ${values.length}` : "margin: none";
}

function discountFooter(rows: Row[]): string {
  const values = rows.map((r) => (r as Record<string, unknown>)["discount"]);
  return values.length ? `discount: ${values.length}` : "discount: none";
}

function taxFooter(rows: Row[]): string {
  const values = rows.map((r) => (r as Record<string, unknown>)["tax"]);
  return values.length ? `tax: ${values.length}` : "tax: none";
}

function netFooter(rows: Row[]): string {
  const values = rows.map((r) => (r as Record<string, unknown>)["net"]);
  return values.length ? `net: ${values.length}` : "net: none";
}

function grossFooter(rows: Row[]): string {
  const values = rows.map((r) => (r as Record<string, unknown>)["gross"]);
  return values.length ? `gross: ${values.length}` : "gross: none";
}

function notesFooter(rows: Row[]): string {
  const values = rows.map((r) => (r as Record<string, unknown>)["notes"]);
  return values.length ? `notes: ${values.length}` : "notes: none";
}

function skuFooter(rows: Row[]): string {
  const values = rows.map((r) => (r as Record<string, unknown>)["sku"]);
  return values.length ? `sku: ${values.length}` : "sku: none";
}

function vendorFooter(rows: Row[]): string {
  const values = rows.map((r) => (r as Record<string, unknown>)["vendor"]);
  return values.length ? `vendor: ${values.length}` : "vendor: none";
}

function warehouseFooter(rows: Row[]): string {
  const values = rows.map((r) => (r as Record<string, unknown>)["warehouse"]);
  return values.length ? `warehouse: ${values.length}` : "warehouse: none";
}

function laneFooter(rows: Row[]): string {
  const values = rows.map((r) => (r as Record<string, unknown>)["lane"]);
  return values.length ? `lane: ${values.length}` : "lane: none";
}

function carrierFooter(rows: Row[]): string {
  const values = rows.map((r) => (r as Record<string, unknown>)["carrier"]);
  return values.length ? `carrier: ${values.length}` : "carrier: none";
}

function etaFooter(rows: Row[]): string {
  const values = rows.map((r) => (r as Record<string, unknown>)["eta"]);
  return values.length ? `eta: ${values.length}` : "eta: none";
}

function priorityFooter(rows: Row[]): string {
  const values = rows.map((r) => (r as Record<string, unknown>)["priority"]);
  return values.length ? `priority: ${values.length}` : "priority: none";
}

function tierFooter(rows: Row[]): string {
  const values = rows.map((r) => (r as Record<string, unknown>)["tier"]);
  return values.length ? `tier: ${values.length}` : "tier: none";
}

function riskFooter(rows: Row[]): string {
  const values = rows.map((r) => (r as Record<string, unknown>)["risk"]);
  return values.length ? `risk: ${values.length}` : "risk: none";
}

function scoreFooter(rows: Row[]): string {
  const values = rows.map((r) => (r as Record<string, unknown>)["score"]);
  return values.length ? `score: ${values.length}` : "score: none";
}

function rankFooter(rows: Row[]): string {
  const values = rows.map((r) => (r as Record<string, unknown>)["rank"]);
  return values.length ? `rank: ${values.length}` : "rank: none";
}

function flagFooter(rows: Row[]): string {
  const values = rows.map((r) => (r as Record<string, unknown>)["flag"]);
  return values.length ? `flag: ${values.length}` : "flag: none";
}
