# NOTE: all equipment values below are ILLUSTRATIVE defaults, not manufacturer data. Replace from datasheets.
from .bess_sizing import SZ as _SZ
DEFAULTS = dict(
    sz=_SZ,
    name="Sample BESS Project", client="", location="", ptype="Grid + BESS", coupling="AC-coupled",
    apps=["Energy shifting"], f_hz=50.0, mv_kv=33.0, grid_kv=33.0, isc_ka=25.0, vcb_ka=31.5, n_incomers=1,
    p_export=0.0, p_import=0.0, poi_pf=1.0,
    containers=[dict(model="Illustrative 5 MWh LFP", qty=16, mwh=5.0, chem="LFP", vdc_min=1000.0, vdc_nom=1200.0, vdc_max=1500.0,
                     c_dis=0.5, c_chg=0.5, dod=1.0, soh_bol=1.0, soh_eol=0.8, aux_kw=30.0)],
    ovr_pdis=0.0, ovr_pchg=0.0,
    pcs_arch="Central PCS", pcs_lv_kv=0.8, pcs_ptarget=0.0, pcs_q=0.0, pcs_pf=1.0, pcs_red="None", pcs_spare=1,
    pcs_maxload=1.0, pcs_derate=1.0, pcs_choice="Balanced", pcs_nover=0,
    pcs_cat=[dict(model="Illustrative 2.5 MW PCS", p_mw=2.5, s_mva=2.5, eff=0.985, vdc_min=900.0, vdc_max=1500.0, idc_max=3000.0,
                  n_ch=1, max_cont=1, pf_min=0.9),
             dict(model="Illustrative 5 MVA PCS", p_mw=5.0, s_mva=5.0, eff=0.985, vdc_min=900.0, vdc_max=1500.0, idc_max=6000.0,
                  n_ch=2, max_cont=2, pf_min=0.9)],
    idt_s=5.0, idt_kvp=33.0, idt_kvs=0.8, idt_nlv=2, idt_ppw=1, idt_vg="Dyn11-Dyn11", idt_z=8.0, idt_cool="ONAN",
    idt_lim=1.0, idt_derate=1.0, idt_eff=99.0, idt_spare=0,
    aux_on=True, opt_meter=True, opt_arrester=True, opt_scada=True, max_draw=0, detail=True,
    pv_on=False, pv_mwp=0.0, pv_inv_mw=0.0, pv_n=1, pv_kv=0.69, dg_on=False, dg_n=1, dg_kva=1000.0, dg_kv=0.415,
    loads=[dict(name="Process line", kw=500.0, qty=2)],
)
