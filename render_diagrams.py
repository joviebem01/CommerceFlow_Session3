"""
render_diagrams.py — recreate the three ECom360 Session 1 diagrams from code.

Outputs:
- docs/ecommerce_uml.png
- docs/entity-model-session1.png
- architecture/architecture-session1.png

Graphviz's ``dot`` executable must be installed and available on PATH.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import config as cfg


BLUE = "#2E74B5"
LIGHT_BLUE = "#D9EAF7"
AMBER = "#C55A11"
LIGHT_AMBER = "#FFF2CC"
GREEN = "#548235"
LIGHT_GREEN = "#E2EFDA"
GREY = "#767171"
NAVY = "#1F3864"


def evidence() -> dict:
    """Load measured values produced by the pipeline, with safe fallbacks."""
    data = {
        "clickstream_rows": 500_000,
        "customer_raw_rows": 50_000,
        "customer_rows": 48_200,
        "orders_rows": 300_000,
        "product_rows": 500,
        "support_rows": 30_000,
        "states": 50,
        "min_per_state": 5_547,
        "median_per_state": 5_981,
        "max_per_state": 6_348,
        "skew": 1.14,
        "crm_duplicate_rows": 1_800,
    }

    if cfg.OUT_PROFILE.exists():
        prof = json.loads(cfg.OUT_PROFILE.read_text(encoding="utf-8"))
        p = prof.get("profiles", {})
        data["clickstream_rows"] = p.get("clickstream", {}).get(
            "rows", data["clickstream_rows"]
        )
        data["customer_raw_rows"] = p.get("customers", {}).get(
            "rows", data["customer_raw_rows"]
        )
        data["orders_rows"] = p.get("orders", {}).get(
            "rows", data["orders_rows"]
        )
        data["product_rows"] = p.get("products", {}).get(
            "rows", data["product_rows"]
        )
        data["support_rows"] = p.get("support", {}).get(
            "rows", data["support_rows"]
        )
        integ = prof.get("integrity", {})
        data["crm_duplicate_rows"] = integ.get(
            "crm_duplicate_rows_to_remove",
            data["crm_duplicate_rows"],
        )
        data["customer_rows"] = (
            data["customer_raw_rows"] - data["crm_duplicate_rows"]
        )

    if cfg.OUT_PARTITION_STRATEGY.exists():
        part = json.loads(
            cfg.OUT_PARTITION_STRATEGY.read_text(encoding="utf-8")
        )
        pred = part.get("prediction", {})
        data["states"] = pred.get("distinct", data["states"])
        data["min_per_state"] = pred.get("min", data["min_per_state"])
        data["median_per_state"] = pred.get(
            "median", data["median_per_state"]
        )
        data["max_per_state"] = pred.get("max", data["max_per_state"])
        data["skew"] = pred.get("skew_ratio", data["skew"])

    return data


def entity_dot(d: dict) -> str:
    return f"""
digraph EntityModel {{
  rankdir=TB;
  bgcolor="white";
  splines=polyline;
  nodesep=0.95;
  ranksep=1.05;
  fontname="Helvetica";
  labelloc="t";
  fontsize=18;
  label=<<b>ECom360 — Session 1 Entity Model</b><br/>
         <font point-size="11">B2C e-commerce revenue intelligence dataset</font><br/>>;

  node [shape=plaintext fontname="Helvetica"];
  edge [color="{BLUE}" fontname="Helvetica" fontsize=10 penwidth=1.6 arrowhead=none];

  Product [label=<
    <table border="0" cellborder="1" cellspacing="0" cellpadding="5">
      <tr><td bgcolor="{LIGHT_BLUE}"><b>Product</b><br/><font point-size="9">Entity · {d["product_rows"]:,} rows</font></td></tr>
      <tr><td align="left"><b>product_id : String «PK»</b></td></tr>
      <tr><td align="left">product_name : String</td></tr>
      <tr><td align="left">category : String</td></tr>
      <tr><td align="left">price : Decimal</td></tr>
    </table>
  >];

  Customer [label=<
    <table border="0" cellborder="1" cellspacing="0" cellpadding="5">
      <tr><td bgcolor="{LIGHT_BLUE}"><b>Customer</b><br/><font point-size="9">Entity · {d["customer_raw_rows"]:,} raw rows · {d["customer_rows"]:,} unique IDs</font></td></tr>
      <tr><td align="left"><b>customer_id : UUID «natural key»</b></td></tr>
      <tr><td align="left">signup_date : Date</td></tr>
      <tr><td align="left" bgcolor="#FFF2CC">state : String <b>«partitionKey»</b></td></tr>
      <tr><td align="left">source : String</td></tr>
    </table>
  >];

  Order [label=<
    <table border="0" cellborder="1" cellspacing="0" cellpadding="5">
      <tr><td bgcolor="{LIGHT_BLUE}"><b>Order</b><br/><font point-size="9">Event · {d["orders_rows"]:,} rows</font></td></tr>
      <tr><td align="left"><b>order_id : UUID «PK»</b></td></tr>
      <tr><td align="left">customer_id : UUID «FK»</td></tr>
      <tr><td align="left">product_id : String «FK»</td></tr>
      <tr><td align="left">order_amount : Decimal</td></tr>
      <tr><td align="left">order_date : Date «eventTime»</td></tr>
      <tr><td align="left">status : String</td></tr>
    </table>
  >];

  Clickstream [label=<
    <table border="0" cellborder="1" cellspacing="0" cellpadding="5">
      <tr><td bgcolor="{LIGHT_BLUE}"><b>ClickstreamEvent</b><br/><font point-size="9">Event · {d["clickstream_rows"]:,} rows</font></td></tr>
      <tr><td align="left"><b>event_id : UUID «PK»</b></td></tr>
      <tr><td align="left">customer_id : UUID «optional FK»</td></tr>
      <tr><td align="left">session_id : UUID</td></tr>
      <tr><td align="left">event_type : String</td></tr>
      <tr><td align="left">timestamp : Timestamp</td></tr>
    </table>
  >];

  Support [label=<
    <table border="0" cellborder="1" cellspacing="0" cellpadding="5">
      <tr><td bgcolor="{LIGHT_BLUE}"><b>SupportTicket</b><br/><font point-size="9">Event · {d["support_rows"]:,} rows</font></td></tr>
      <tr><td align="left"><b>ticket_id : UUID «PK»</b></td></tr>
      <tr><td align="left">customer_id : UUID «FK»</td></tr>
      <tr><td align="left">issue_type : String</td></tr>
      <tr><td align="left">resolution_time_hours : Double</td></tr>
      <tr><td align="left">sentiment : String</td></tr>
    </table>
  >];

  Product -> Order [taillabel="1" headlabel="0..*" label="appears in" labeldistance=2.1];
  Customer -> Order [taillabel="1" headlabel="0..*" label="places" color="{AMBER}" penwidth=2.4 labeldistance=2.1];
  Customer -> Clickstream [taillabel="0..1" headlabel="0..*" label="generates (anonymous allowed)" style=dashed labeldistance=2.1];
  Customer -> Support [taillabel="1" headlabel="0..*" label="opens" labeldistance=2.1];

  note [shape=note style=filled fillcolor="#FFF9E6" color="{AMBER}" fontsize=10 label=<
    <b>Partition key: state</b><br align="left"/>
    {d["states"]} distinct values<br align="left"/>
    {d["min_per_state"]:,} / {d["median_per_state"]:,} / {d["max_per_state"]:,} orders per state<br align="left"/>
    skew ratio {float(d["skew"]):.2f} : 1<br align="left"/><br align="left"/>
    <b>Monetization:</b> normalized successful,<br align="left"/>
    positive-value orders produce revenue_amount.<br align="left"/>
    CRM contains {d["crm_duplicate_rows"]:,} duplicate rows and is canonicalized first.
  >];

  note -> Customer [style=invis];
  {{ rank=same; note; Customer; Product; }}
}}
"""


def uml_dot(d: dict) -> str:
    return f"""
digraph UML {{
  rankdir=TB;
  bgcolor="white";
  splines=ortho;
  nodesep=0.75;
  ranksep=0.9;
  fontname="Helvetica";
  labelloc="t";
  fontsize=17;
  label=<<b>UML Class Diagram — E-Commerce Multi-File Dataset</b>>;

  node [shape=plaintext fontname="Helvetica"];
  edge [color="#666666" fontname="Helvetica" fontsize=10 arrowhead=none];

  Product [label=<
    <table border="0" cellborder="1" cellspacing="0" cellpadding="5">
      <tr><td bgcolor="#E2EFDA"><b>Product</b></td></tr>
      <tr><td align="left"><b>PK</b> product_id</td></tr>
      <tr><td align="left">product_name</td></tr>
      <tr><td align="left">category</td></tr>
      <tr><td align="left">price</td></tr>
    </table>
  >];

  Customer [label=<
    <table border="0" cellborder="1" cellspacing="0" cellpadding="5">
      <tr><td bgcolor="{LIGHT_BLUE}"><b>Customer</b></td></tr>
      <tr><td align="left"><b>PK?</b> customer_id (dirty duplicates)</td></tr>
      <tr><td align="left">first_name, last_name</td></tr>
      <tr><td align="left">email, phone_number</td></tr>
      <tr><td align="left">gender, dob, signup_date</td></tr>
      <tr><td align="left">address, city, state, country</td></tr>
      <tr><td align="left">device_id(s), source</td></tr>
    </table>
  >];

  Order [label=<
    <table border="0" cellborder="1" cellspacing="0" cellpadding="5">
      <tr><td bgcolor="#FFF2CC"><b>Order</b></td></tr>
      <tr><td align="left"><b>PK</b> order_id</td></tr>
      <tr><td align="left"><b>FK</b> customer_id</td></tr>
      <tr><td align="left"><b>FK</b> product_id</td></tr>
      <tr><td align="left">order_amount</td></tr>
      <tr><td align="left">order_date</td></tr>
      <tr><td align="left">payment_method</td></tr>
      <tr><td align="left">status, quantity</td></tr>
    </table>
  >];

  Clickstream [label=<
    <table border="0" cellborder="1" cellspacing="0" cellpadding="5">
      <tr><td bgcolor="#F4DDF4"><b>ClickstreamEvent</b></td></tr>
      <tr><td align="left"><b>PK</b> event_id</td></tr>
      <tr><td align="left">session_id</td></tr>
      <tr><td align="left"><b>FK?</b> customer_id (nullable)</td></tr>
      <tr><td align="left">event_type, page_url</td></tr>
      <tr><td align="left">device_id, timestamp, ingest_run_id</td></tr>
    </table>
  >];

  Support [label=<
    <table border="0" cellborder="1" cellspacing="0" cellpadding="5">
      <tr><td bgcolor="#F4CCCC"><b>SupportTicket</b></td></tr>
      <tr><td align="left"><b>PK</b> ticket_id</td></tr>
      <tr><td align="left"><b>FK</b> customer_id</td></tr>
      <tr><td align="left">issue_type</td></tr>
      <tr><td align="left">ticket_created, ticket_resolved</td></tr>
      <tr><td align="left">resolution_time_hours</td></tr>
      <tr><td align="left">sentiment, support_agent</td></tr>
    </table>
  >];

  Product -> Order [label="1        0..*"];
  Customer -> Order [label="1        0..*"];
  Customer -> Clickstream [label="0..1        0..*"];
  Customer -> Support [label="1        0..*"];

  note [shape=note style=filled fillcolor="#F2F2F2" label="Relationship checks from the CSVs:\\l• all order customer_ids resolve to CRM\\l• all support customer_ids resolve to CRM\\l• all non-null clickstream customer_ids resolve to CRM\\l• all order product_ids resolve to Product\\l• CRM customer_id has duplicate raw rows\\l"];
  Order -> note [style=dashed];
}}
"""


def architecture_dot(d: dict) -> str:
    return f"""
digraph Architecture {{
  rankdir=LR;
  bgcolor="white";
  compound=true;
  nodesep=0.42;
  ranksep=0.9;
  fontname="Helvetica";
  labelloc="t";
  fontsize=17;
  label=<<b>ECom360 — Session 1 In-Memory Parallel Compute Architecture</b><br/>
         <font point-size="11">CRM + clickstream + product + order + support analytics</font><br/>>;

  node [shape=box style="rounded,filled" fontname="Helvetica" fontsize=10 penwidth=1.3 margin="0.14,0.09"];
  edge [color="{BLUE}" penwidth=1.4 fontname="Helvetica" fontsize=9];

  subgraph cluster_source {{
    label=<<b>Source CSVs</b>>;
    color="{GREY}";
    style=dashed;

    click [label="clickstream_500k_events.csv\\n{d["clickstream_rows"]:,} events" fillcolor="{LIGHT_BLUE}"];
    support [label="support_tickets_30000_dirty.csv\\n{d["support_rows"]:,} tickets" fillcolor="{LIGHT_BLUE}"];
    orders [label="orders_300k_dirty.csv\\n{d["orders_rows"]:,} order events" fillcolor="{LIGHT_BLUE}"];
    crm [label="crm_50000_customers_dirty_v3.csv\\n{d["customer_raw_rows"]:,} CRM rows" fillcolor="{LIGHT_BLUE}"];
    product [label="product_catalog_dirty_30pct.csv\\n{d["product_rows"]:,} products" fillcolor="{LIGHT_BLUE}"];
  }}

  subgraph cluster_integrate {{
    label=<<b>Profiling + Integration</b>>;
    color="{GREY}";
    style=dashed;

    reduce [label="customer-level feature reduction\\nclickstream + support" fillcolor="{LIGHT_AMBER}" color="{AMBER}"];
    profile [label="profile_files.py\\neligibility + integrity + quality" fillcolor="{LIGHT_AMBER}" color="{AMBER}"];
    join [label="load_and_join.py\\norder-grain working dataset\\n{d["orders_rows"]:,} → {d["orders_rows"]:,}" fillcolor="{LIGHT_AMBER}" color="{AMBER}"];
  }}

  subgraph cluster_compute {{
    label=<<b>Parallel Compute</b>>;
    color="{GREY}";
    style=dashed;

    repart [label="repartition({cfg.CHOSEN_PARTITIONS}, 'state')\\nbounded parallelism" fillcolor="{LIGHT_GREEN}" color="{GREEN}"];
    agg [label="parallel_compute.py\\ngroupBy(state)\\norders · successful orders · revenue · AOV" fillcolor="{LIGHT_GREEN}" color="{GREEN}"];
    base [label="sequential_baseline.py\\npandas reference" fillcolor="#FCE4D6" color="{AMBER}"];
    valid [label="validate()\\ncounts exact · floats < {cfg.TOLERANCE:.0e}" fillcolor="#FCE4D6" color="{AMBER}"];
  }}

  subgraph cluster_results {{
    label=<<b>Results</b>>;
    color="{GREY}";
    style=dashed;

    parts [label="partition_sizes.csv" fillcolor="white"];
    parquet [label="state_revenue.parquet" fillcolor="{LIGHT_BLUE}" color="{NAVY}" penwidth=2.1];
    bench [label="session1_benchmark.csv" fillcolor="white"];
  }}

  click -> reduce;
  support -> reduce;
  click -> profile [style=dotted];
  support -> profile [style=dotted];
  orders -> profile;
  crm -> profile;
  product -> profile;

  reduce -> join;
  profile -> join [label="eligible"];
  orders -> join [style=dotted];
  crm -> join [style=dotted];
  product -> join [style=dotted];

  join -> repart;
  join -> base [label="same logical data"];
  repart -> agg;
  agg -> valid;
  base -> valid [label="reference"];
  valid -> parquet [label="passed" color="{GREEN}" penwidth=2.0];

  repart -> parts [style=dotted];
  agg -> bench [style=dotted];
}}
"""


def render(dot_source: str, out_png: Path) -> None:
    out_png.parent.mkdir(parents=True, exist_ok=True)
    dot_file = out_png.with_suffix(".dot")
    dot_file.write_text(dot_source, encoding="utf-8")

    dot_exe = shutil.which("dot")
    if not dot_exe:
        raise RuntimeError(
            "Graphviz 'dot' was not found on PATH. "
            f"The DOT source was saved at {dot_file}."
        )

    subprocess.run(
        [
            dot_exe,
            "-Tpng",
            "-Gdpi=150",
            str(dot_file),
            "-o",
            str(out_png),
        ],
        check=True,
    )
    print(f"Wrote {out_png}")


def main() -> int:
    d = evidence()
    render(uml_dot(d), cfg.OUT_UML_DIAGRAM)
    render(entity_dot(d), cfg.OUT_ENTITY_DIAGRAM)
    render(architecture_dot(d), cfg.OUT_ARCH_DIAGRAM)
    return 0


if __name__ == "__main__":
    sys.exit(main())
