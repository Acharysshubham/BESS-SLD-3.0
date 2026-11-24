import networkx as nx


def graph(df):
    g = nx.DiGraph()
    for r in df.fillna("").astype(str).to_dict("records"):
        if r["id"]:
            g.add_node(r["id"], type=r["type"])
            if r["parent"]: g.add_edge(r["parent"], r["id"])
    return g


def energy_paths(g):
    """Every battery must have PCS, transformer and bus upstream; every PCS must feed a battery."""
    bad = []
    for n, d in g.nodes(data=True):
        if d.get("type") == "battery":
            up = {g.nodes[a].get("type") for a in nx.ancestors(g, n)}
            if not {"pcs", "transformer", "bus"} <= up: bad.append(f"{n}: incomplete path to MV bus (needs PCS, transformer, bus upstream)")
        if d.get("type") == "pcs" and not any(g.nodes[x].get("type") == "battery" for x in nx.descendants(g, n)): bad.append(f"{n}: PCS has no battery connected")
    return bad
