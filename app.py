import streamlit as st
import pandas as pd
from datetime import date, timedelta
import streamlit as st
import requests
import requests as http_requests

def get_qpiai_headers():
    token = st.secrets.get("QPIAI_OPT_TOKEN")

    if not token:
        return None

    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

st.set_page_config(page_title="MedicineLink | Hospital Exchange", page_icon="🏥", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 1.3rem; padding-bottom: 2rem;}
.hero {padding: 1.25rem 1.5rem; border-radius: 16px; background: linear-gradient(115deg,#102a43,#087e8b); color: white; margin-bottom: 1rem;}
.hero h1 {color: white; margin: 0;}
.hero p {color: #e8f7f8; margin: .35rem 0 0 0;}
div[data-testid="stMetric"] {border: 1px solid rgba(128,128,128,.25); padding: 12px; border-radius: 12px;}
</style>
""", unsafe_allow_html=True)

TODAY = date.today()
HOSPITALS = ["City General Hospital", "Northside Medical Centre", "Lakeside Hospital", "Rural Care Hospital"]
URGENCY_RULES = {
    "Emergency": {"max_hours": 6, "priority": 1},
    "Urgent": {"max_hours": 24, "priority": 2},
    "Moderate": {"max_hours": 72, "priority": 3},
    "Not urgent": {"max_hours": 168, "priority": 4},
}
STORAGE = ["Ambient", "Refrigerated", "Frozen"]

def sample_stock():
    return pd.DataFrame([
        {"Hospital":"City General Hospital","Medicine":"Paracetamol 500 mg","Batch ID":"CGH-PAR-01","Stock":500,"Minimum Stock":300,"Expiry Date":TODAY+timedelta(days=150),"Storage":"Ambient","Unit":"tablets","Unit Price (₹)":1.2,"Location":"Central Bengaluru"},
        {"Hospital":"Northside Medical Centre","Medicine":"Paracetamol 500 mg","Batch ID":"NMC-PAR-07","Stock":900,"Minimum Stock":250,"Expiry Date":TODAY+timedelta(days=75),"Storage":"Ambient","Unit":"tablets","Unit Price (₹)":1.0,"Location":"North Bengaluru"},
        {"Hospital":"Lakeside Hospital","Medicine":"Insulin 100 IU/ml","Batch ID":"LH-INS-02","Stock":120,"Minimum Stock":80,"Expiry Date":TODAY+timedelta(days=100),"Storage":"Refrigerated","Unit":"vials","Unit Price (₹)":180.0,"Location":"East Bengaluru"},
        {"Hospital":"Rural Care Hospital","Medicine":"Amoxicillin 250 mg","Batch ID":"RCH-AMX-04","Stock":600,"Minimum Stock":200,"Expiry Date":TODAY+timedelta(days=210),"Storage":"Ambient","Unit":"capsules","Unit Price (₹)":2.5,"Location":"Outskirts"},
        {"Hospital":"City General Hospital","Medicine":"Insulin 100 IU/ml","Batch ID":"CGH-INS-03","Stock":100,"Minimum Stock":80,"Expiry Date":TODAY+timedelta(days=25),"Storage":"Refrigerated","Unit":"vials","Unit Price (₹)":175.0,"Location":"Central Bengaluru"},
    ])

def sample_requests():
    return pd.DataFrame([
        {"Request ID":"REQ-1001","Requesting Hospital":"City General Hospital","Medicine":"Paracetamol 500 mg","Quantity Needed":100,"Urgency":"Urgent","Required By":TODAY+timedelta(days=1),"Storage Required":"Ambient","Status":"Open","Matched Hospital":"","Agreed Unit Price (₹)":0.0,"Transport Fee (₹)":0.0,"Payment Status":"Not started","Delivery Status":"Not arranged"},
        {"Request ID":"REQ-1002","Requesting Hospital":"Lakeside Hospital","Medicine":"Insulin 100 IU/ml","Quantity Needed":25,"Urgency":"Emergency","Required By":TODAY,"Storage Required":"Refrigerated","Status":"Open","Matched Hospital":"","Agreed Unit Price (₹)":0.0,"Transport Fee (₹)":0.0,"Payment Status":"Not started","Delivery Status":"Not arranged"},
    ])

if "stock" not in st.session_state:
    st.session_state.stock = sample_stock()
if "requests" not in st.session_state:
    st.session_state.requests = sample_requests()
if "payments" not in st.session_state:
    st.session_state.payments = []

def money(value):
    return f"₹{float(value):,.2f}"

def normalize_stock(df):
    cols = ["Hospital","Medicine","Batch ID","Stock","Minimum Stock","Expiry Date","Storage","Unit","Unit Price (₹)","Location"]
    df = df.copy()
    for c in cols:
        if c not in df.columns:
            df[c] = 0 if c in ["Stock","Minimum Stock","Unit Price (₹)"] else ""
    df["Stock"] = pd.to_numeric(df["Stock"], errors="coerce").fillna(0).clip(lower=0).astype(int)
    df["Minimum Stock"] = pd.to_numeric(df["Minimum Stock"], errors="coerce").fillna(0).clip(lower=0).astype(int)
    df["Unit Price (₹)"] = pd.to_numeric(df["Unit Price (₹)"], errors="coerce").fillna(0).clip(lower=0)
    df["Expiry Date"] = pd.to_datetime(df["Expiry Date"], errors="coerce").dt.date
    for c in ["Hospital","Medicine","Batch ID","Storage","Unit","Location"]:
        df[c] = df[c].fillna("").astype(str)
    return df[cols]

def normalize_requests(df):
    cols = ["Request ID","Requesting Hospital","Medicine","Quantity Needed","Urgency","Required By","Storage Required","Status","Matched Hospital","Agreed Unit Price (₹)","Transport Fee (₹)","Payment Status","Delivery Status"]
    df = df.copy()
    for c in cols:
        if c not in df.columns:
            df[c] = 0 if c in ["Quantity Needed","Agreed Unit Price (₹)","Transport Fee (₹)"] else ""
    for c in ["Quantity Needed"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).clip(lower=0).astype(int)
    for c in ["Agreed Unit Price (₹)","Transport Fee (₹)"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).clip(lower=0)
    df["Required By"] = pd.to_datetime(df["Required By"], errors="coerce").dt.date
    for c in ["Request ID","Requesting Hospital","Medicine","Urgency","Storage Required","Status","Matched Hospital","Payment Status","Delivery Status"]:
        df[c] = df[c].fillna("").astype(str)
    return df[cols]

def surplus_for(row):
    return max(0, int(row["Stock"]) - int(row["Minimum Stock"]))

def find_matches(request_row, stock):
    s = normalize_stock(stock)
    s["Surplus"] = s.apply(surplus_for, axis=1)
    s["Days to Expiry"] = s["Expiry Date"].apply(lambda d: (d - TODAY).days if pd.notna(d) else -999)
    req_hospital = str(request_row["Requesting Hospital"]).strip()
    medicine = str(request_row["Medicine"]).strip().casefold()
    required_storage = str(request_row["Storage Required"]).strip().casefold()
    s = s[
        (s["Hospital"] != req_hospital) &
        (s["Medicine"].str.strip().str.casefold() == medicine) &
        (s["Storage"].str.strip().str.casefold() == required_storage) &
        (s["Surplus"] > 0) &
        (s["Days to Expiry"] >= 0)
    ].copy()
    s["Suggested Qty"] = s["Surplus"].clip(upper=int(request_row["Quantity Needed"]))
    s["Estimated Medicine Cost (₹)"] = s["Suggested Qty"] * s["Unit Price (₹)"]
    return s.sort_values(["Days to Expiry", "Suggested Qty"], ascending=[True, False])

def make_id(prefix, n):
    return f"{prefix}-{n:04d}"

st.markdown("""
<div class="hero">
<h1>🏥 MedicineLink</h1>
<p>A shared hospital network for medicine shortages, safe surplus transfers and transparent settlement.</p>
</div>
""", unsafe_allow_html=True)

st.sidebar.title("MedicineLink")
st.sidebar.caption("Hospital medicine exchange prototype")
page = st.sidebar.radio("Navigate", ["Network dashboard", "Hospital stock", "Request medicine", "Match & transfer", "Payments & delivery", "Data & exports"])
st.sidebar.divider()
st.sidebar.caption("Demo data only. Use authorized, validated records in real operations.")
if st.sidebar.button("Reset demo data", use_container_width=True):
    st.session_state.stock = sample_stock()
    st.session_state.requests = sample_requests()
    st.session_state.payments = []
    st.rerun()

stock = normalize_stock(st.session_state.stock)
requests = normalize_requests(st.session_state.requests)
stock["Surplus"] = stock.apply(surplus_for, axis=1)
stock["Days to Expiry"] = stock["Expiry Date"].apply(lambda d: (d - TODAY).days if pd.notna(d) else None)
stock["Stock Status"] = stock.apply(lambda r: "Below minimum" if r["Stock"] < r["Minimum Stock"] else ("At minimum" if r["Stock"] == r["Minimum Stock"] else "Has surplus"), axis=1)

if page == "Network dashboard":
    st.subheader("Hospital network overview")
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Registered hospitals", stock["Hospital"].nunique())
    c2.metric("Medicine records", len(stock))
    c3.metric("Open requests", int((requests["Status"] == "Open").sum()))
    c4.metric("Available surplus units", f"{int(stock['Surplus'].sum()):,}")
    st.markdown("#### Network stock by hospital")
    if not stock.empty:
        st.bar_chart(stock.groupby("Hospital")["Stock"].sum())
    left,right = st.columns(2)
    with left:
        st.markdown("#### Requests needing support")
        open_req = requests[requests["Status"].isin(["Open","Matched","Awaiting payment","Payment confirmed","In transit"])]
        if open_req.empty:
            st.success("No active requests.")
        else:
            st.dataframe(open_req[["Request ID","Requesting Hospital","Medicine","Quantity Needed","Urgency","Required By","Status","Matched Hospital"]], use_container_width=True, hide_index=True)
    with right:
        st.markdown("#### Stock below minimum")
        low = stock[stock["Stock"] < stock["Minimum Stock"]]
        if low.empty:
            st.success("No records below minimum stock.")
        else:
            st.dataframe(low[["Hospital","Medicine","Stock","Minimum Stock","Stock Status"]], use_container_width=True, hide_index=True)
    st.info("Core rule: only stock above the donor hospital's minimum reserve is considered transferable. Expiry and storage compatibility are checked before a match is suggested.")

elif page == "Hospital stock":
    st.subheader("Hospital stock registry")
    st.write("Each record represents a medicine batch at one hospital. Surplus = current stock − minimum stock.")
    with st.form("add_stock", clear_on_submit=True):
        a,b,c = st.columns(3)
        hospital = a.selectbox("Hospital", HOSPITALS)
        medicine = b.text_input("Medicine name", placeholder="e.g. Paracetamol 500 mg")
        batch = c.text_input("Batch ID", placeholder="e.g. HOSP-PAR-10")
        d,e,f = st.columns(3)
        qty = d.number_input("Current stock", min_value=0, step=1)
        minimum = e.number_input("Minimum stock reserve", min_value=0, step=1)
        expiry = f.date_input("Expiry date", value=TODAY+timedelta(days=180))
        g,h,i = st.columns(3)
        storage = g.selectbox("Storage requirement", STORAGE)
        unit = h.text_input("Unit", value="units")
        price = i.number_input("Unit transfer price (₹)", min_value=0.0, step=1.0)
        location = st.text_input("Hospital area / location", placeholder="e.g. North Bengaluru")
        add = st.form_submit_button("Add stock record", type="primary")
        if add:
            if not medicine.strip() or not batch.strip() or not location.strip():
                st.error("Enter medicine name, batch ID and location.")
            elif batch.strip().casefold() in stock["Batch ID"].str.casefold().values:
                st.error("Batch ID already exists. Use a unique batch ID.")
            else:
                new = pd.DataFrame([{"Hospital":hospital,"Medicine":medicine.strip(),"Batch ID":batch.strip(),"Stock":int(qty),"Minimum Stock":int(minimum),"Expiry Date":expiry,"Storage":storage,"Unit":unit.strip() or "units","Unit Price (₹)":float(price),"Location":location.strip()}])
                st.session_state.stock = pd.concat([normalize_stock(st.session_state.stock),new], ignore_index=True)
                st.success("Stock record added.")
                st.rerun()
    st.markdown("#### Current hospital records (editable)")
    edited = st.data_editor(normalize_stock(st.session_state.stock), num_rows="dynamic", use_container_width=True, hide_index=True,
        column_config={"Hospital":st.column_config.SelectboxColumn(options=HOSPITALS),"Storage":st.column_config.SelectboxColumn(options=STORAGE),"Expiry Date":st.column_config.DateColumn(),"Stock":st.column_config.NumberColumn(min_value=0,step=1),"Minimum Stock":st.column_config.NumberColumn(min_value=0,step=1),"Unit Price (₹)":st.column_config.NumberColumn(min_value=0.0,step=1.0)})
    if st.button("Save stock table", type="primary"):
        st.session_state.stock = normalize_stock(edited)
        st.success("Stock updated for this session.")
        st.rerun()
    st.caption("A real deployment should use a database and verified hospital accounts. Demo edits may be lost when the app restarts.")

elif page == "Request medicine":
    st.subheader("Create a medicine request")
    st.write("A hospital requests stock when its current inventory cannot meet demand. The urgency sets the target delivery window.")
    with st.form("new_request", clear_on_submit=True):
        a,b = st.columns(2)
        req_hospital = a.selectbox("Requesting hospital", HOSPITALS)
        medicine = b.text_input("Medicine required", placeholder="Use the same medicine name as stock records")
        c,d,e = st.columns(3)
        quantity = c.number_input("Quantity required", min_value=1, value=50, step=1)
        urgency = d.selectbox("Urgency", list(URGENCY_RULES.keys()), help="Emergency ≤ 6h; Urgent ≤ 24h; Moderate ≤ 72h; Not urgent ≤ 7 days.")
        storage = e.selectbox("Required storage", STORAGE)
        required_by = st.date_input("Required by date", value=TODAY+timedelta(days=1))
        notes = st.text_area("Clinical / operational note (do not enter patient-identifying information)", placeholder="Optional reason for request")
        submit = st.form_submit_button("Submit request", type="primary")
        if submit:
            if not medicine.strip():
                st.error("Enter the medicine name.")
            else:
                rid = make_id("REQ", len(st.session_state.requests)+1001)
                new = pd.DataFrame([{"Request ID":rid,"Requesting Hospital":req_hospital,"Medicine":medicine.strip(),"Quantity Needed":int(quantity),"Urgency":urgency,"Required By":required_by,"Storage Required":storage,"Status":"Open","Matched Hospital":"","Agreed Unit Price (₹)":0.0,"Transport Fee (₹)":0.0,"Payment Status":"Not started","Delivery Status":"Not arranged"}])
                st.session_state.requests = pd.concat([normalize_requests(st.session_state.requests),new], ignore_index=True)
                st.success(f"Request {rid} submitted. Go to Match & transfer to find compatible surplus.")
                if notes.strip():
                    st.caption("Note is not saved in this prototype: add a secure, access-controlled notes feature before production use.")
                st.rerun()
    st.markdown("#### Existing requests")
    st.dataframe(normalize_requests(st.session_state.requests)[["Request ID","Requesting Hospital","Medicine","Quantity Needed","Urgency","Required By","Status","Matched Hospital"]], use_container_width=True, hide_index=True)

elif page == "Match & transfer":
    st.subheader("Find a hospital with safe surplus")
    reqs = normalize_requests(st.session_state.requests)
    eligible = reqs[reqs["Status"].isin(["Open","Matched"])]
    if eligible.empty:
        st.info("No open requests to match. Create a request first.")
    else:
        chosen_id = st.selectbox("Choose a request", eligible["Request ID"].tolist(), format_func=lambda rid: f"{rid} — {eligible.loc[eligible['Request ID']==rid, 'Medicine'].iloc[0]} ({eligible.loc[eligible['Request ID']==rid, 'Urgency'].iloc[0]})")
        row = reqs[reqs["Request ID"] == chosen_id].iloc[0]
        rule = URGENCY_RULES.get(row["Urgency"], URGENCY_RULES["Moderate"])
        st.write(f"**Requesting hospital:** {row['Requesting Hospital']}  ·  **Medicine:** {row['Medicine']}  ·  **Quantity:** {row['Quantity Needed']} {row['Urgency'].lower()} priority")
        st.caption(f"Target delivery window for this demo: within {rule['max_hours']} hours. This is a planning target, not a guaranteed delivery.")
        matches = find_matches(row, st.session_state.stock)
        if matches.empty:
            st.warning("No compatible surplus match found. Check medicine name, donor minimum stock, expiry date and storage type.")
        else:
            st.markdown("#### Compatible donor hospitals")
            st.dataframe(matches[["Hospital","Batch ID","Stock","Minimum Stock","Surplus","Suggested Qty","Expiry Date","Days to Expiry","Storage","Location","Unit Price (₹)","Estimated Medicine Cost (₹)"]], use_container_width=True, hide_index=True)
            donor_options = matches["Hospital"].tolist()
            donor = st.selectbox("Select donor hospital", donor_options)
            donor_rows = matches[matches["Hospital"] == donor]
            donor_row = donor_rows.iloc[0]
            max_qty = min(int(row["Quantity Needed"]), int(donor_rows["Surplus"].sum()))
            suggested_qty = st.number_input("Quantity to transfer", min_value=1, max_value=max(1,max_qty), value=max(1,min(max_qty,int(row["Quantity Needed"]))))
            unit_price = st.number_input("Agreed unit price (₹)", min_value=0.0, value=float(donor_row["Unit Price (₹)"]), step=1.0)
            transport_fee = st.number_input("Estimated transport fee (₹)", min_value=0.0, value=250.0, step=50.0)
            med_cost = suggested_qty * unit_price
            total = med_cost + transport_fee
            c1,c2,c3 = st.columns(3)
            c1.metric("Medicine cost", money(med_cost))
            c2.metric("Transport estimate", money(transport_fee))
            c3.metric("Estimated total", money(total))
            if st.button("Create proposed transfer", type="primary"):
                idx = st.session_state.requests.index[st.session_state.requests["Request ID"] == chosen_id]
                if len(idx):
                    st.session_state.requests.loc[idx[0], "Status"] = "Matched"
                    st.session_state.requests.loc[idx[0], "Matched Hospital"] = donor
                    st.session_state.requests.loc[idx[0], "Agreed Unit Price (₹)"] = float(unit_price)
                    st.session_state.requests.loc[idx[0], "Transport Fee (₹)"] = float(transport_fee)
                    st.session_state.requests.loc[idx[0], "Status"] = "Awaiting donor approval"
                    st.session_state.requests.loc[idx[0], "Delivery Status"] = f"Proposed — {int(suggested_qty)} units"
                    # store proposed quantity in a separate state mapping
                    if "transfer_qty" not in st.session_state:
                        st.session_state.transfer_qty = {}
                    st.session_state.transfer_qty[chosen_id] = int(suggested_qty)
                    st.success("Transfer proposal created. Continue to Payments & delivery to review and update its status.")
                    st.rerun()
    st.markdown("#### All requests and transfer status")
    st.dataframe(normalize_requests(st.session_state.requests)[["Request ID","Requesting Hospital","Medicine","Quantity Needed","Urgency","Status","Matched Hospital","Payment Status","Delivery Status"]], use_container_width=True, hide_index=True)

elif page == "Payments & delivery":
    st.subheader("Payment and delivery workflow")
    reqs = normalize_requests(st.session_state.requests)
    proposed = reqs[reqs["Status"].isin(["Awaiting donor approval","Awaiting payment","Payment confirmed","In transit","Delivered","Rejected"])]
    if proposed.empty:
        st.info("No transfer proposals yet. Use Match & transfer to create a proposal.")
    else:
        rid = st.selectbox("Select transfer", proposed["Request ID"].tolist())
        idxs = st.session_state.requests.index[st.session_state.requests["Request ID"] == rid]
        idx = idxs[0]
        r = normalize_requests(st.session_state.requests).loc[normalize_requests(st.session_state.requests)["Request ID"] == rid].iloc[0]
        qty = int(st.session_state.get("transfer_qty", {}).get(rid, min(int(r["Quantity Needed"]), 1)))
        medicine_cost = qty * float(r["Agreed Unit Price (₹)"])
        transport = float(r["Transport Fee (₹)"])
        total = medicine_cost + transport
        st.markdown("#### Settlement summary")
        c1,c2,c3 = st.columns(3)
        c1.metric("Medicine amount", money(medicine_cost))
        c2.metric("Transport fee", money(transport))
        c3.metric("Total estimate", money(total))
        st.write(f"**From:** {r['Matched Hospital'] or 'Not assigned'}  →  **To:** {r['Requesting Hospital']}")
        st.write(f"**Medicine:** {r['Medicine']}  ·  **Quantity proposed:** {qty}  ·  **Urgency:** {r['Urgency']}")
        st.warning("This is a payment-status demo only. It does not collect card/bank details or move real money. Real payments require an approved payment provider, secure backend, invoices and legal/accounting review.")
        new_status = st.selectbox("Update transfer stage", ["Awaiting donor approval","Awaiting payment","Payment confirmed","In transit","Delivered","Rejected"], index=["Awaiting donor approval","Awaiting payment","Payment confirmed","In transit","Delivered","Rejected"].index(r["Status"]) if r["Status"] in ["Awaiting donor approval","Awaiting payment","Payment confirmed","In transit","Delivered","Rejected"] else 0)
        if st.button("Save transfer status", type="primary"):
            st.session_state.requests.loc[idx, "Status"] = new_status
            if new_status == "Awaiting donor approval":
                st.session_state.requests.loc[idx, "Payment Status"] = "Not started"
                st.session_state.requests.loc[idx, "Delivery Status"] = "Awaiting donor approval"
            elif new_status == "Awaiting payment":
                st.session_state.requests.loc[idx, "Payment Status"] = "Pending"
                st.session_state.requests.loc[idx, "Delivery Status"] = "Awaiting payment"
            elif new_status == "Payment confirmed":
                st.session_state.requests.loc[idx, "Payment Status"] = "Marked paid (demo)"
                st.session_state.requests.loc[idx, "Delivery Status"] = "Ready for dispatch"
            elif new_status == "In transit":
                st.session_state.requests.loc[idx, "Payment Status"] = "Marked paid (demo)"
                st.session_state.requests.loc[idx, "Delivery Status"] = "In transit"
            elif new_status == "Delivered":
                st.session_state.requests.loc[idx, "Payment Status"] = "Marked paid (demo)"
                st.session_state.requests.loc[idx, "Delivery Status"] = "Delivered — confirmation required"
            else:
                st.session_state.requests.loc[idx, "Delivery Status"] = "Proposal rejected"
            st.success("Transfer status updated.")
            st.rerun()
        st.markdown("#### Transfer history")
        st.dataframe(normalize_requests(st.session_state.requests)[["Request ID","Requesting Hospital","Medicine","Urgency","Matched Hospital","Status","Payment Status","Delivery Status"]], use_container_width=True, hide_index=True)

elif page == "Data & exports":
    st.subheader("Data & exports")
    st.write("Download current demo records or upload a hospital stock CSV.")
    upload = st.file_uploader("Import stock CSV", type=["csv"])
    if upload is not None:
        try:
            st.session_state.stock = normalize_stock(pd.read_csv(upload))
            st.success("Stock CSV imported.")
            st.rerun()
        except Exception as exc:
            st.error(f"Could not import CSV: {exc}")
    c1,c2 = st.columns(2)
    with c1:
        st.markdown("#### Hospital stock")
        st.download_button("Download stock CSV", normalize_stock(st.session_state.stock).to_csv(index=False).encode("utf-8"), "hospital_stock.csv", "text/csv", use_container_width=True)
        st.dataframe(normalize_stock(st.session_state.stock), use_container_width=True, hide_index=True)
    with c2:
        st.markdown("#### Requests / transfers")
        st.download_button("Download requests CSV", normalize_requests(st.session_state.requests).to_csv(index=False).encode("utf-8"), "medicine_requests_transfers.csv", "text/csv", use_container_width=True)
        st.dataframe(normalize_requests(st.session_state.requests), use_container_width=True, hide_index=True)
    st.markdown("#### Suggested CSV columns")
    st.code("Hospital, Medicine, Batch ID, Stock, Minimum Stock, Expiry Date, Storage, Unit, Unit Price (₹), Location")
    st.caption("Do not upload patient records or other personally identifiable health information into this prototype.")

st.divider()
st.caption("MedicineLink hackathon prototype • Sample data only • Validate medicine transfer eligibility, cold-chain handling, authorization, pricing and local regulations before any real-world transfer.")

# Temporary QpiAI connection test
st.subheader("QpiAI API Connection")

if st.button("Test QpiAI Connection"):
    token = st.secrets.get("QPIAI_OPT_TOKEN", "")

    if not token:
        st.error("QpiAI token is missing from Streamlit Secrets.")
    else:
        try:
            response = http_requests.get(
                "https://opt-server.qpiai.tech/api/auth",
                headers={
                    "Authorization": f"Bearer {token}"
                },
                timeout=15
            )

            if response.status_code == 200:
                st.success("QpiAI API responded successfully!")
            elif response.status_code == 401:
                st.error("QpiAI rejected the token. Check its validity.")
            elif response.status_code == 403:
                st.warning("Authenticated, but access is forbidden.")
            else:
                st.warning(
                    f"QpiAI returned HTTP {response.status_code}. "
                    "Authentication or endpoint access may need checking."
                )

        except http_requests.exceptions.RequestException:
            st.error("Could not complete the QpiAI API request.")
