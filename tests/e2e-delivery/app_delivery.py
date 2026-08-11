import streamlit as st

from core.delivery.ui_streamlit import render_delivery_v1

st.set_page_config(page_title="Delivery Proprio V1", layout="wide")
render_delivery_v1()
