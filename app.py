import streamlit as st
import pandas as pd
from datetime import date, timedelta
from io import StringIO

st.set_page_config(page_title="Medicine Expiry Optimizer", page_icon="💊", layout="wide")

# ---------- Styling ----------
st.markdown("""
<style>
.block-container {padding-top: 1.5rem; padding-bottom: 2rem;}
.hero {padding: 1.2rem 1.4rem; border-radius: 16px; background: linear-gradient(120deg,#102a43,#176b87); color: white; margin-bottom: 1rem;}
.hero h1 {color:white; margin:0;}
.hero p {color:#e6f4f7; margin:.35rem 0 0 0;}
.small-note {color: #64748b; font-size: .88rem;}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
<h1>💊 Medicine Expiry Optimizer</h1>
<p>Inventory visibility · Expiry risk alerts · Demand-aware medicine redistribution</p>
</div>
""", unsafe_allow_html=True)

TODAY = date.today()
STORAGE_OPTIONS = ["Ambient", "Refrigerated", "Frozen"]

# ---------- Data setup ----------
def sample_inventory():
    return pd.DataFrame([
        {"Batch ID":"B-1001","Medicine":"Paracetamol 500 mg","Quantity":500,"Expiry Date":TODAY + timedelta(days=25),"Location":"Warehouse A","Storage":"Ambient","Unit":"tablets"},
        {"Batch ID":"B-1002","Medicine":"Amoxicillin 250 mg","Quantity":180,"Expiry Date":TODAY + timedelta(days=75),"Location":"Warehouse A","Storage":"Ambient","Unit":"capsules"},
        {"Batch ID":"B-1003","Medicine":"Insulin","Quantity":90,"Expiry Date":TODAY + timedelta(days=18),"Location":"Warehouse B","Storage":"Refrigerated","Unit":"vials"},
        {"Batch ID":"B-1004","Medicine":"ORS Sachet","Quantity":350,"Expiry Date":TODAY + timedelta(days=220),"Location":"Warehouse B","Storage":"Ambient","Unit":"sachets"},
        {"Batch ID":"B-1005","Medicine":"Vaccine X (demo)","Quantity":60,"Expiry Date":TODAY + timedelta(days=45),"Location":"Warehouse A","Storage":"Refrigerated","Unit":"doses"},
    ])

def sample_requests():
    return pd.DataFrame([
        {"Request ID":"REQ-01","Medicine":"Paracetamol 500 mg","Destination":"Clinic North","Demand":160,"Distance (km)":18.0,"Required Storage":"Ambient"},
        {"Request ID":"REQ-02","Medicine":"Insulin","Destination":"Clinic South","Demand":40,"Distance (km)":12.0,"Required Storage":"Refrigerated"},
        {"Request ID":"REQ-03","Medicine":"Amoxicillin 250 mg","Destination":"Rural Health Centre","Demand":100,"Distance (km)":42.0,"Required Storage":"Ambient"},
    ])

if "inventory" not in st.session_state:
    st.session_state.inventory = sample_inventory()
if "requests" not in st.session_state:
    st.session_state.requests = sample_requests()

def clean_inventory(df):
    expected = ["Batch ID","Medicine","Quantity","Expiry Date","Location","Storage","Unit"]
    df = df.copy()
    for c in expected:
        if c not in df.columns:
            df[c] = "" if c not in ["Quantity"] else 0
    df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce").fillna(0).clip(lower=0).astype(int)
    df["Expiry Date"] = pd.to_datetime(df["Expiry Date"], errors="coerce").dt.date
    for c in ["Batch ID","Medicine","Location","Storage","Unit"]:
        df[c] = df[c].fillna("").astype(str)
    return df[expected]

def clean_requests(df):
    expected = ["Request ID","Medicine","Destination","Demand","Distance (km)","Required Storage"]
    df = df.copy()
    for c in expected:
        if c not in df.columns:
            df[c] = 0 if c in ["Demand","Distance (km)"] else ""
    df["Demand"] = pd.to_numeric(df["Demand"], errors="coerce").fillna(0).clip(lower=0).astype(int)
    df["Distance (km)"] = pd.to_numeric(df["Distance (km)"], errors="coerce").fillna(0).clip(lower=0)
    for c in ["Request ID","Medicine","Destination","Required Storage"]:
        df[c] = df[c].fillna("").astype(str)
    return df[expected]

st.sidebar.header("Project controls")
st.sidebar.caption("This is a hackathon prototype. Sample data is loaded on first open.")
if st.sidebar.button("Reset to sample data", use_container_width=True):
    st.session_state.inventory = sample_inventory()
    st.session_state.requests = sample_requests()
    st.rerun()

with st.sidebar.expander("Import inventory CSV"):
    inv_file = st.file_uploader("Upload inventory CSV", type=["csv"], key="inv_upload")
    if inv_file is not None:
        try:
            st.session_state.inventory = clean_inventory(pd.read_csv(inv_file))
            st.success("Inventory imported.")
        except Exception as e:
            st.error(f"Could not read inventory CSV: {e}")
with st.sidebar.expander("Import demand/request CSV"):
    req_file = st.file_uploader("Upload request CSV", type=["csv"], key="req_upload")
    if req_file is not None:
        try:
            st.session_state.requests = clean_requests(pd.read_csv(req_file))
            st.success("Requests imported.")
        except Exception as e:
            st.error(f"Could not read request CSV: {e}")

inventory = clean_inventory(st.session_state.inventory)
requests = clean_requests(st.session_state.requests)
inventory["Days to Expiry"] = inventory["Expiry Date"].apply(lambda d: (d - TODAY).days if pd.notna(d) else None)
inventory["Status"] = inventory["Days to Expiry"].apply(
    lambda n: "Unknown date" if pd.isna(n) else ("Expired" if n < 0 else ("Critical ≤ 30 days" if n <= 30 else ("Expiring ≤ 90 days" if n <= 90 else "Good")))
)

# ---------- Optimization logic ----------
def build_plan(inv, req):
    """Greedy demo planner: earliest-expiry-first, storage match, nearest demand first."""
    inv = clean_inventory(inv)
    req = clean_requests(req)
    inv["Days to Expiry"] = inv["Expiry Date"].apply(lambda d: (d - TODAY).days if pd.notna(d) else 999999)
    inv = inv[(inv["Quantity"] > 0) & (inv["Days to Expiry"] >= 0)].copy()
    req = req[req["Demand"] > 0].copy()
    plan = []
    remaining_stock = {idx: int(row["Quantity"]) for idx, row in inv.iterrows()}
    remaining_demand = {idx: int(row["Demand"]) for idx, row in req.iterrows()}
    # Prioritize requests with shorter distance, then allocate FEFO batches.
    req_order = sorted(req.index, key=lambda i: float(req.loc[i, "Distance (km)"]))
    for ri in req_order:
        r = req.loc[ri]
        matching = [ii for ii in inv.index
                    if str(inv.loc[ii, "Medicine"]).strip().casefold() == str(r["Medicine"]).strip().casefold()
                    and str(inv.loc[ii, "Storage"]).strip().casefold() == str(r["Required Storage"]).strip().casefold()
                    and remaining_stock[ii] > 0]
        matching.sort(key=lambda ii: inv.loc[ii, "Days to Expiry"])
        for ii in matching:
            if remaining_demand[ri] <= 0:
                break
            qty = min(remaining_stock[ii], remaining_demand[ri])
            days = int(inv.loc[ii, "Days to Expiry"])
            distance = float(r["Distance (km)"])
            urgency = "Critical" if days <= 30 else ("Soon" if days <= 90 else "Normal")
            plan.append({
                "Request ID": r["Request ID"], "Medicine": r["Medicine"],
                "Batch ID": inv.loc[ii, "Batch ID"], "Source": inv.loc[ii, "Location"],
                "Destination": r["Destination"], "Allocate Qty": qty, "Unit": inv.loc[ii, "Unit"],
                "Days to Expiry": days, "Distance (km)": distance,
                "Storage Match": "Yes", "Priority": urgency,
                "Reason": f"{urgency} expiry priority; compatible storage; {distance:g} km"
            })
            remaining_stock[ii] -= qty
            remaining_demand[ri] -= qty
    unmet = []
    for ri in req_order:
        if remaining_demand[ri] > 0:
            unmet.append({"Request ID": req.loc[ri, "Request ID"], "Medicine": req.loc[ri, "Medicine"],
                          "Destination": req.loc[ri, "Destination"], "Unfilled Demand": remaining_demand[ri],
                          "Required Storage": req.loc[ri, "Required Storage"]})
    return pd.DataFrame(plan), pd.DataFrame(unmet)

plan, unmet = build_plan(inventory, requests)

# ---------- Navigation ----------
page = st.sidebar.radio("Navigate", ["Dashboard", "Inventory", "Expiry alerts", "Transport optimizer", "Data & exports"])

if page == "Dashboard":
    st.subheader("Operations overview")
    total_units = int(inventory["Quantity"].sum())
    expired_units = int(inventory.loc[inventory["Status"] == "Expired", "Quantity"].sum())
    critical_batches = int((inventory["Status"] == "Critical ≤ 30 days").sum())
    soon_batches = int((inventory["Status"] == "Expiring ≤ 90 days").sum())
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Medicine batches", f"{len(inventory)}")
    c2.metric("Total units", f"{total_units:,}")
    c3.metric("Critical batches", f"{critical_batches}")
    c4.metric("Expired units", f"{expired_units:,}")
    st.caption("Expiry risk is calculated from today's date and each batch's expiry date.")
    left, right = st.columns(2)
    with left:
        st.markdown("#### Stock by medicine")
        if not inventory.empty:
            chart = inventory.groupby("Medicine", as_index=False)["Quantity"].sum().set_index("Medicine")
            st.bar_chart(chart)
        else:
            st.info("No inventory yet.")
    with right:
        st.markdown("#### Batches by expiry status")
        status_counts = inventory["Status"].value_counts()
        if not status_counts.empty:
            st.bar_chart(status_counts)
        else:
            st.info("No inventory yet.")
    st.markdown("#### Items needing attention")
    attention = inventory[inventory["Status"].isin(["Expired","Critical ≤ 30 days","Expiring ≤ 90 days"])].copy()
    if attention.empty:
        st.success("No batches currently need expiry attention.")
    else:
        st.dataframe(attention[["Batch ID","Medicine","Quantity","Expiry Date","Days to Expiry","Location","Storage","Status"]], use_container_width=True, hide_index=True)
    st.info("Demo only: recommendations are based on the sample/request data entered here. Confirm all transfers with qualified inventory and cold-chain staff.")

elif page == "Inventory":
    st.subheader("Medicine inventory")
    st.write("Add a batch below or edit the table. Use unique batch IDs for reliable tracking.")
    with st.form("add_batch_form", clear_on_submit=True):
        a,b,c = st.columns(3)
        batch_id = a.text_input("Batch ID", placeholder="e.g. B-2001")
        medicine = b.text_input("Medicine name", placeholder="e.g. Paracetamol 500 mg")
        quantity = c.number_input("Quantity", min_value=0, value=0, step=1)
        d,e,f = st.columns(3)
        expiry = d.date_input("Expiry date", value=TODAY + timedelta(days=90))
        location = e.text_input("Current location", placeholder="e.g. Warehouse A")
        storage = f.selectbox("Storage requirement", STORAGE_OPTIONS)
        unit = st.text_input("Unit", value="units", help="e.g. tablets, vials, packs")
        add = st.form_submit_button("Add medicine batch", type="primary")
        if add:
            if not batch_id.strip() or not medicine.strip() or not location.strip():
                st.error("Please fill in Batch ID, Medicine name, and Current location.")
            elif batch_id.strip().casefold() in st.session_state.inventory["Batch ID"].astype(str).str.casefold().values:
                st.error("That Batch ID already exists. Use a unique ID.")
            else:
                new = pd.DataFrame([{"Batch ID":batch_id.strip(),"Medicine":medicine.strip(),"Quantity":int(quantity),
                                     "Expiry Date":expiry,"Location":location.strip(),"Storage":storage,"Unit":unit.strip() or "units"}])
                st.session_state.inventory = pd.concat([clean_inventory(st.session_state.inventory),new], ignore_index=True)
                st.success("Batch added.")
                st.rerun()
    st.markdown("#### Current stock (editable)")
    edited = st.data_editor(clean_inventory(st.session_state.inventory), num_rows="dynamic", use_container_width=True, hide_index=True,
                            column_config={"Expiry Date":st.column_config.DateColumn("Expiry Date"),"Quantity":st.column_config.NumberColumn("Quantity", min_value=0, step=1),
                                           "Storage":st.column_config.SelectboxColumn("Storage", options=STORAGE_OPTIONS)})
    if st.button("Save inventory table", type="primary"):
        st.session_state.inventory = clean_inventory(edited)
        st.success("Inventory saved for this running session.")
        st.rerun()
    st.caption("Session data is temporary in this prototype. Export your CSV before closing/restarting the app.")

elif page == "Expiry alerts":
    st.subheader("Expiry alerts")
    days_filter = st.selectbox("Show batches expiring within", [30, 60, 90, 180, 365], index=2, format_func=lambda x: f"{x} days")
    alerts = inventory[(inventory["Days to Expiry"] < 0) | (inventory["Days to Expiry"] <= days_filter)].copy()
    if alerts.empty:
        st.success(f"No expired batches or batches expiring within {days_filter} days.")
    else:
        def alert_text(row):
            n = row["Days to Expiry"]
            if pd.isna(n): return "Missing expiry date"
            if n < 0: return f"EXPIRED {-int(n)} day(s) ago — isolate and follow local disposal/return policy"
            if n == 0: return "Expires today — urgent review"
            if n <= 30: return f"CRITICAL — expires in {int(n)} day(s)"
            return f"Expires in {int(n)} day(s)"
        alerts["Alert"] = alerts.apply(alert_text, axis=1)
        st.dataframe(alerts[["Batch ID","Medicine","Quantity","Expiry Date","Days to Expiry","Location","Storage","Alert"]].sort_values("Days to Expiry"), use_container_width=True, hide_index=True)
        st.download_button("Download expiry alerts CSV", alerts.to_csv(index=False).encode("utf-8"), "expiry_alerts.csv", "text/csv")
    st.warning("This page displays alerts when opened; it does not send automatic email/SMS notifications.")

elif page == "Transport optimizer":
    st.subheader("Transportation & redistribution optimizer")
    st.write("Enter demand requests. The prototype matches medicine and storage type, prioritizes nearer requests, and uses FEFO (First Expiry, First Out) batches.")
    with st.form("request_form", clear_on_submit=True):
        a,b,c = st.columns(3)
        rid = a.text_input("Request ID", placeholder="e.g. REQ-04")
        med = b.text_input("Medicine name (must match inventory)")
        dest = c.text_input("Destination", placeholder="e.g. Clinic East")
        d,e,f = st.columns(3)
        demand = d.number_input("Demand quantity", min_value=0, value=0, step=1)
        distance = e.number_input("Distance (km)", min_value=0.0, value=10.0, step=1.0)
        req_storage = f.selectbox("Required storage", STORAGE_OPTIONS, key="req_storage")
        add_req = st.form_submit_button("Add demand request", type="primary")
        if add_req:
            if not rid.strip() or not med.strip() or not dest.strip():
                st.error("Please fill in Request ID, Medicine name, and Destination.")
            elif rid.strip().casefold() in st.session_state.requests["Request ID"].astype(str).str.casefold().values:
                st.error("That Request ID already exists. Use a unique ID.")
            else:
                new_req = pd.DataFrame([{"Request ID":rid.strip(),"Medicine":med.strip(),"Destination":dest.strip(),
                                         "Demand":int(demand),"Distance (km)":float(distance),"Required Storage":req_storage}])
                st.session_state.requests = pd.concat([clean_requests(st.session_state.requests),new_req], ignore_index=True)
                st.success("Demand request added.")
                st.rerun()
    st.markdown("#### Demand requests (editable)")
    edited_req = st.data_editor(clean_requests(st.session_state.requests), num_rows="dynamic", use_container_width=True, hide_index=True,
                                column_config={"Demand":st.column_config.NumberColumn("Demand", min_value=0, step=1),
                                               "Distance (km)":st.column_config.NumberColumn("Distance (km)", min_value=0.0, step=0.5),
                                               "Required Storage":st.column_config.SelectboxColumn("Required Storage", options=STORAGE_OPTIONS)})
    if st.button("Save requests", type="primary"):
        st.session_state.requests = clean_requests(edited_req)
        st.success("Requests saved for this running session.")
        st.rerun()
    inventory = clean_inventory(st.session_state.inventory)
    requests = clean_requests(st.session_state.requests)
    plan, unmet = build_plan(inventory, requests)
    st.markdown("#### Suggested transfer plan")
    if plan.empty:
        st.info("No compatible transfers found. Check medicine names, stock quantities, and storage requirements.")
    else:
        c1,c2,c3 = st.columns(3)
        c1.metric("Suggested allocations", len(plan))
        c2.metric("Units allocated", f"{int(plan['Allocate Qty'].sum()):,}")
        c3.metric("Destinations served", plan["Destination"].nunique())
        st.dataframe(plan, use_container_width=True, hide_index=True)
        st.download_button("Download transfer plan CSV", plan.to_csv(index=False).encode("utf-8"), "suggested_transfer_plan.csv", "text/csv")
    if not unmet.empty:
        st.markdown("#### Unmet demand")
        st.dataframe(unmet, use_container_width=True, hide_index=True)
        st.warning("Some demand cannot be filled with currently available, unexpired stock that matches the required storage type.")
    st.caption("Important limitations: this is a transparent greedy demo, not a certified logistics solver. It does not calculate road routes, traffic, vehicle capacity, transit temperature, travel time, or legal/regulatory eligibility. Validate transfers before acting.")

elif page == "Data & exports":
    st.subheader("Data management & exports")
    st.write("Download current data to keep a copy. In this demo, edits live in the current Streamlit session and may be lost after a restart.")
    inv_export = clean_inventory(st.session_state.inventory)
    req_export = clean_requests(st.session_state.requests)
    c1,c2 = st.columns(2)
    with c1:
        st.markdown("#### Inventory")
        st.download_button("Download inventory CSV", inv_export.to_csv(index=False).encode("utf-8"), "medicine_inventory.csv", "text/csv", use_container_width=True)
        st.dataframe(inv_export, use_container_width=True, hide_index=True)
    with c2:
        st.markdown("#### Demand requests")
        st.download_button("Download requests CSV", req_export.to_csv(index=False).encode("utf-8"), "medicine_requests.csv", "text/csv", use_container_width=True)
        st.dataframe(req_export, use_container_width=True, hide_index=True)
    st.markdown("#### Expected CSV columns")
    st.code("Inventory: Batch ID, Medicine, Quantity, Expiry Date, Location, Storage, Unit\nRequests: Request ID, Medicine, Destination, Demand, Distance (km), Required Storage")
    st.info("For a real deployment with multiple users and durable records, add a database (such as PostgreSQL or Supabase), authentication, audit logs, and controlled access. Do not upload real patient or sensitive medical data to this demo.")

st.divider()
st.markdown('<p class="small-note">Hackathon prototype · Use synthetic/sample data for demonstrations · Always verify expiry, storage, and transfer decisions with authorized personnel.</p>', unsafe_allow_html=True)
