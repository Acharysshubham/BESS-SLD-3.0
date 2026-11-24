import sys, copy, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from core.defaults import DEFAULTS
from core.pipeline import run
from core.connectivity_engine import graph
import networkx as nx


def _ok(R):
    g = graph(R["nodes"]); assert nx.is_directed_acyclic_graph(g)
    assert not (R["val"]["Category"].isin(["Connectivity", "Model consistency"]) & (R["val"]["Status"] == "FAIL")).any()


def test_hv_grid_pv_dg_industrial_variants():
    P = copy.deepcopy(DEFAULTS); P.update(ptype="Grid + Solar PV + BESS", grid_kv=220.0, pv_inv_mw=30.0, pv_mwp=40.0, pv_n=10, dg_on=True)
    R = run(P); _ok(R); ids = set(R["nodes"].id); assert {"MPT", "PV01", "DG01", "TRPV", "TRDG"} <= ids
    P = copy.deepcopy(DEFAULTS); P["ptype"] = "Complete industrial electrical distribution system"; R = run(P); _ok(R); assert "MDB" in set(R["nodes"].id)


def test_string_pcs_splits_containers_and_representative_drawing():
    P = copy.deepcopy(DEFAULTS); P["containers"][0]["qty"] = 4; P["pcs_nover"] = 8; P["idt_s"] = 2.5; P["idt_nlv"] = 1
    R = run(P); assert R["nodes"].id.str.startswith("BESS").sum() == 8
    P = copy.deepcopy(DEFAULTS); P["max_draw"] = 3; R = run(P); _ok(R); assert R["nodes"].id.str.startswith("IDT").sum() == 3
