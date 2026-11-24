import sys, copy, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from core.defaults import DEFAULTS
from core.pipeline import run


def test_sample_case_emerges_from_calculation():
    R = run(copy.deepcopy(DEFAULTS))
    assert R["bess"]["n"] == 16 and abs(R["bess"]["e_total"] - 80) < 1e-9 and abs(R["bess"]["p_dis"] - 40) < 1e-9
    assert R["pcs"]["n"] == 16 and R["pcs"]["model"].startswith("Illustrative 2.5")
    assert R["idt"]["n"] == 8 and all(r["n_pcs"] == 2 for r in R["idt"]["rows"])
    ids = R["nodes"]["id"]
    assert ids.str.startswith("IDT").sum() == 8 and ids.str.startswith("PCS").sum() == 16 and ids.str.startswith("BESS").sum() == 16
    assert not (R["val"]["Status"] == "FAIL").any(), R["val"][R["val"]["Status"] == "FAIL"]


def test_reactive_power_and_redundancy_change_quantities():
    P = copy.deepcopy(DEFAULTS); P["pcs_q"] = 15.0; P["pcs_red"] = "N+1"
    R = run(P); assert R["pcs"]["n_op"] > 16 and R["pcs"]["spare"] == 1


def test_mixed_containers_and_undersized_idt():
    P = copy.deepcopy(DEFAULTS); P["containers"] = [dict(DEFAULTS["containers"][0], qty=3), dict(DEFAULTS["containers"][0], qty=2, mwh=2.0, model="Small")]
    R = run(P); assert R["bess"]["n"] == 5 and abs(R["bess"]["e_total"] - 19) < 1e-9
    P = copy.deepcopy(DEFAULTS); P["idt_s"] = 2.0; R = run(P); assert not R["idt"]["feasible"] and (R["val"]["Status"] == "FAIL").any()


def test_diagram_edit_is_flagged():
    P = copy.deepcopy(DEFAULTS); R = run(P)
    from core.validation_engine import validate
    n = R["nodes"][R["nodes"]["id"] != "PCS16"]; v = validate(P, R, n)
    assert ((v["Category"] == "Model consistency") & (v["Status"] == "FAIL")).any()
