import streamlit as st

st.set_page_config(
    page_title="Medicine Expiry Optimizer",
    page_icon="💊",
    layout="wide"
)

st.title("💊 Medicine Expiry Optimizer")
st.write("Medicine inventory and transportation management")

medicine = st.text_input("Medicine name")
quantity = st.number_input("Quantity", min_value=0, step=1)
expiry = st.date_input("Expiry date")

if st.button("Add Medicine"):
    if medicine.strip():
        st.success(f"{medicine} added successfully!")
        st.write("Quantity:", quantity)
        st.write("Expiry date:", expiry)
    else:
        st.warning("Please enter a medicine name.")
