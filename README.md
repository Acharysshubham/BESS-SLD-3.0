# BESS & Electrical SLD Designer

Streamlit engineering tool: BESS container sizing, PCS optimisation, IDT sizing, automatic single-line diagram,
rule/consistency checks, Pandapower load flow + short circuit, and exports.

## Run
```
pip install -r requirements.txt
streamlit run app.py
pytest -q tests
```
Deploy on Streamlit Cloud: push this folder to GitHub, set main file `app.py`.

## Workflow (sidebar)
Dashboard, Project, **2a BESS sizing**, BESS containers, PCS selection, IDT selection, Electrical equipment, SLD editor, Electrical analysis, Reports & export.
All inputs live in one project dictionary, so you can move backwards and change earlier steps without losing later ones.

## How it works
| Module | Role |
|---|---|
| `core/bess_sizing.py` + `sizing_ui.py` | Database-driven sizing: energy / power / both, BOL-EOL logic, 14-20 % oversizing search, POI-based AC chain, year tables, FAT/SAT, augmentation, RTE, what-if analyser |
| `core/bess_calculations.py` | Mixed containers; installed, usable BOL/EOL energy; C-rate power; overrides flagged |
| `core/pcs_optimizer.py` | AC power vs apparent power, PF/Q, N+1, loading, container pairing, DC checks, 3 configurations |
| `core/idt_optimizer.py` | IDT count bounded by thermal and LV-winding limits; even PCS distribution |
| `core/topology_generator.py` | Sizing results -> node table (parent/child) = single source of truth |
| `core/connectivity_engine.py`, `validation_engine.py` | NetworkX connectivity, design-vs-diagram consistency, PASS/WARN/FAIL/UNVERIFIED dashboard |
| `sld/drawing_engine.py` | Auto layout, symbols, SVG / PDF / PNG / DXF-ready primitives |
| `analysis/pandapower_model.py` | Equivalent steady-state network, load flow, short circuit (assumptions listed) |
| `reports/` | Excel workbook, PDF report, equipment schedule |

Quantities (PCS, IDT, blocks) are never hardcoded; the 16 x 5 MWh sample in `tests/test_sample.py` emerges from the calculations.

## Limits (read before relying on results)
- Equipment values in `core/defaults.py` are illustrative, not manufacturer data. Replace from datasheets.
- Steady-state only: protection coordination, earthing, harmonics, transients and grid-forming behaviour are shown as UNVERIFIED.
- Short-circuit result excludes PCS fault contribution. IDT windings are assumed to share the rating equally.
- Not yet implemented: drag-and-drop canvas, undo/redo, multi-sheet drawings, DC-coupled topology, cable sizing, RMU/CT/PT/relay symbols.
- GElectrical (GPL-3.0) was used as a feature reference only; no code was copied.

## BESS sizing (step 2a)
- Upload the product database (.xlsx: sheets `Containers`, `SOH`, `Calendar`). Download the template from the page for the exact columns. The built-in sample is illustrative only.
- Nearest C-rate container is selected; if several share it, each is sized separately. "Apply to container design" pushes the chosen result into step 2 / PCS / IDT / SLD.
- BOL only -> EOL = 80 % of BOL. EOL only -> BOL = 125 % of EOL. Yearly requirement is interpolated linearly BOL->EOL unless overridden per year.
- Assumptions beyond the written spec: mismatch loss applied to base and augmented cohorts; availability applied to augmented cohorts; augmented cohorts age from their own year; charge-side augmentation uses the charge formula (divide by efficiencies, add aux); extra aux and standby are added on the discharge side; measurement factor = 1 - error; power is not SOH-derated.
- The analyser is rule-based (before/after on the model), not a language-model chat.
