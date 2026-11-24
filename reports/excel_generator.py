import io
import pandas as pd
from .equipment_schedule import schedule


def sizing_tables(P, R):
    b, c, i = R["bess"], R["pcs"], R["idt"]
    bt = pd.DataFrame([("Containers", b["n"]), ("Installed energy (MWh)", b["e_total"]), ("Usable BOL (MWh)", b["e_bol"]), ("Usable EOL (MWh)", b["e_eol"]),
                       ("DC discharge power (MW)", b["p_dis"]), ("DC charge power (MW)", b["p_chg"]), ("Duration at rated power (h)", b["duration_h"])], columns=["Item", "Value"])
    pt = pd.DataFrame([("Model", c["model"]), ("Redundancy", c["red"]), ("AC active power required (MW)", c["p_ac"]), ("Apparent power required (MVA)", c["s_req"]),
                       ("Operating PCS", c["n_op"]), ("Spare PCS", c["spare"]), ("Installed PCS", c["n"]), ("Installed MVA", c["s_inst"]),
                       ("Loading (%)", c["loading"]), ("Capacity after 1 failure (MVA)", c["after_fail"])], columns=["Item", "Value"])
    it = pd.DataFrame(i["rows"]) if i["rows"] else pd.DataFrame()
    return bt, pt, it


def to_excel(P, R, nodes, val):
    bt, pt, it = sizing_tables(P, R); buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        pd.DataFrame(P["containers"]).to_excel(w, sheet_name="Containers", index=False); bt.to_excel(w, sheet_name="BESS sizing", index=False)
        R["pcs_table"].to_excel(w, sheet_name="PCS configs", index=False); pt.to_excel(w, sheet_name="PCS selected", index=False)
        it.to_excel(w, sheet_name="IDT allocation", index=False); schedule(nodes).to_excel(w, sheet_name="Equipment schedule", index=False)
        nodes.to_excel(w, sheet_name="Network model", index=False); val.to_excel(w, sheet_name="Validation", index=False)
        for ws in w.book.worksheets:
            for col in ws.columns: ws.column_dimensions[col[0].column_letter].width = min(48, max(10, max(len(str(c.value or "")) for c in col) + 2))
    return buf.getvalue()
