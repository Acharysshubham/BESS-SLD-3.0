import pandas as pd


def schedule(nodes):
    d = nodes.fillna("").copy()
    g = d.groupby(["type", "spec1", "spec2"]).agg(qty=("id", "count"), tags=("label", lambda s: ", ".join(list(s)[:6]) + (" ..." if len(s) > 6 else ""))).reset_index()
    return g.rename(columns={"type": "Equipment", "spec1": "Rating 1", "spec2": "Rating 2", "qty": "Qty", "tags": "Tags"})
