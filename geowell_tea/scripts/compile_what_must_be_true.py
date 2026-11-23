import pandas as pd, json, numpy as np
from pathlib import Path
pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 45)
O = Path("outputs")
rows = []
for c in ("case_a_pa", "case_a_nl", "case_b_nd", "case_b_nl"):
    for ku, f in (("3.2", O / c / "what_must_be_true.csv"), ("4.4", O / c / "validity_ku4.4/what_must_be_true.csv"),
                  ("6", O / c / "validity_ku6/what_must_be_true.csv")):
        d = pd.read_csv(f)
        for cov, g in d.groupby("coverage", sort=False):
            g = g.set_index("ts_case")
            get = lambda key: g.loc[[i for i in g.index if i.startswith(key)][0]]
            rows.append(dict(case=c, ku=ku, coverage="full" if cov.startswith("full") else "any",
                             TS_FOAK=get("FOAK").ts_lcoh, TS_base=get("today").ts_lcoh, TS_NOAK=get("1.").ts_lcoh,
                             TS_all_levers=get("4.").ts_lcoh, coax_today=g.coax_lcoh_today.iloc[0],
                             incumbent=g.incumbent.iloc[0], ts_NOAK_design=get("1.").ts_design,
                             unmet_NOAK=get("1.").ts_unmet_max,
                             CO2_parity_NOAK=get("1.").carbon_price_for_parity,
                             CO2_parity_all=get("4.").carbon_price_for_parity))
df = pd.DataFrame(rows)
df.to_csv(O / "what_must_be_true_summary.csv", index=False)
print(df.round(1).to_string())
