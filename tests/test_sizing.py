import sys, io, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from core import bess_sizing as S

DB = S.load_db(io.BytesIO(S.template_db()))


def test_template_roundtrip_and_validation():
    assert len(DB["cont"]) == 4 and (DB["cont"].dc_rte > 1).all()
    try: S.load_db(io.BytesIO(b"junk")); assert False
    except Exception: pass


def test_nearest_crate_and_tie_gives_two_containers():
    assert len(S.run_all(DB, {**S.SZ, "c_rate": 0.5})) == 2           # two 0.5C containers -> both sized
    assert list(S.run_all(DB, {**S.SZ, "c_rate": 0.3})) == ["Sample-3.7MWh-0.25C"]
    assert list(S.run_all(DB, {**S.SZ, "time_mode": "Duration (h)", "t_h": 1.0})) == ["Sample-4.2MWh-1C"]   # 1 h -> 1 C


def test_bol_eol_assumptions():
    assert S.ref_energy({**S.SZ, "basis": "BOL only", "e_mwh": 100}) == (100, 80)
    assert S.ref_energy({**S.SZ, "basis": "EOL only", "e_mwh": 80}) == (100, 80)


def test_energy_sizing_meets_every_year_and_is_minimal():
    r = list(S.run_all(DB, {**S.SZ, "basis": "EOL only"}).values())[1]
    assert r["ok"] and (r["df"].Energy != "NOT MATCHED").all()
    c, sz = r["c"], {**S.SZ, "basis": "EOL only"}
    smaller = S.evaluate(c, sz, r["e"], r["n"] - 1, r["soh"], r["cal"])
    assert (smaller.Energy == "NOT MATCHED").any()                   # one container fewer fails


def test_poi_voltage_changes_ac_chain():
    lo = list(S.run_all(DB, {**S.SZ, "poi_kv": 33}).values())[0]; hi = list(S.run_all(DB, {**S.SZ, "poi_kv": 132}).values())[0]
    assert S.chain(hi["e"], {**S.SZ, "poi_kv": 132}, "dis") < S.chain(lo["e"], S.SZ, "dis")


def test_power_and_both_modes():
    p = list(S.run_all(DB, {**S.SZ, "fulfil": "Power", "p_mw": 80}).values())[0]
    assert p["df"]["POI power net (MW)"].iloc[0] >= 80 and p["n"] == p["n_power"]
    b = list(S.run_all(DB, {**S.SZ, "fulfil": "Both", "p_mw": 80}).values())[0]; assert b["n"] == max(b["n_power"], b["n_energy"])


def test_augmentation_adds_energy_only_from_its_year():
    sz = {**S.SZ, "aug_on": True, "aug_tbl": [{"year": 5, "containers": 3}]}; r = list(S.run_all(DB, sz).values())[0]; d = r["df"]
    assert (d.loc[d.Year < 5, "Augmented energy (MWh)"] == 0).all() and (d.loc[d.Year >= 5, "Augmented energy (MWh)"] > 0).all()


def test_aux_off_removes_aux_and_whatif_runs():
    r = list(S.run_all(DB, {**S.SZ, "aux_on": False}).values())[0]; assert (r["df"]["Aux energy dis (MWh)"] == 0).all()
    w = S.whatif(DB, S.SZ, "Sample-5.0MWh-0.5C", {"dod": 90.0}); assert w["n1"] >= w["n0"] and len(S.explain("dod", w, S.SZ)) >= 5


def test_existing_pipeline_still_works_with_sz_default():
    import copy
    from core.defaults import DEFAULTS
    from core.pipeline import run
    assert run(copy.deepcopy(DEFAULTS))["pcs"]["n"] == 16
