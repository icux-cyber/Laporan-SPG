from datetime import date, datetime, timedelta
from io import BytesIO
import json
import os
import re
import tempfile
import geopandas as gpd
import pandas as pd
import pydeck as pdk
import requests
from shapely.geometry import Point
import streamlit as st
from streamlit_js_eval import get_geolocation

try:
    from schedule_entry import (
        SCHEDULE_DETAIL_FILE,
        get_scheduled_personnel_for_team,
        get_scheduled_vehicles,
        render_schedule_entry,
    )
except ImportError:
    from schedule_entry import SCHEDULE_DETAIL_FILE, get_scheduled_vehicles, render_schedule_entry

    def get_scheduled_personnel_for_team(team_name, target_date=None, selected_kecamatan=""):
        return {
            "found": False,
            "supervisi": [],
            "spg_1": [],
            "spg_2": [],
            "spg_all": [],
            "vehicles": [],
            "records": [],
        }

from team_brand_sync import (
    match_brands_by_team_name,
    resolve_team_allowed_brands,
)

# ====================================================
# KONFIGURASI HALAMAN STREAMLIT
# ====================================================
st.set_page_config(
    page_title="Laporan Dirsell SPG",
    page_icon="📍",
    layout="centered",
    initial_sidebar_state="collapsed",
)

if str(st.query_params.get("page", "")).strip().lower() != "admin":
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"],
        [data-testid="stSidebarNav"],
        [data-testid="collapsedControl"] {
            display: none !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def get_team_theme(team_name: str) -> dict:
    """Mengembalikan konfigurasi palet warna dinamis berdasarkan nama team."""
    name = str(team_name or "").casefold()
    if "matcha" in name:
        return {
            "banner_bg": "linear-gradient(135deg, #090D0B 0%, #132A1E 100%)",
            "banner_border": "#22C55E",
            "badge_bg": "rgba(34, 197, 94, 0.18)",
            "badge_color": "#4ADE80",
            "btn_bg": "linear-gradient(135deg, #16A34A 0%, #052E16 100%)",
            "btn_shadow": "0 4px 12px rgba(22, 163, 74, 0.30)",
            "addr_bg": "#ECFDF5",
            "addr_border": "#86EFAC",
            "addr_accent": "#16A34A",
            "addr_text": "#064E3B",
            "accent_hex": "#22C55E",
        }
    if "super" in name:
        return {
            "banner_bg": "linear-gradient(135deg, #7F1D1D 0%, #450A0A 100%)",
            "banner_border": "#F59E0B",
            "badge_bg": "rgba(245, 158, 11, 0.20)",
            "badge_color": "#FCD34D",
            "btn_bg": "linear-gradient(135deg, #DC2626 0%, #B45309 100%)",
            "btn_shadow": "0 4px 12px rgba(220, 38, 38, 0.30)",
            "addr_bg": "#FFFBEB",
            "addr_border": "#FDE68A",
            "addr_accent": "#D97706",
            "addr_text": "#78350F",
            "accent_hex": "#F59E0B",
        }
    if "aksara" in name or "akasar" in name:
        return {
            "banner_bg": "linear-gradient(135deg, #0F1115 0%, #27200E 100%)",
            "banner_border": "#EAB308",
            "badge_bg": "rgba(234, 179, 8, 0.20)",
            "badge_color": "#FACC15",
            "btn_bg": "linear-gradient(135deg, #18181B 0%, #CA8A04 100%)",
            "btn_shadow": "0 4px 12px rgba(202, 138, 4, 0.28)",
            "addr_bg": "#FEFCE8",
            "addr_border": "#FEF08A",
            "addr_accent": "#CA8A04",
            "addr_text": "#713F12",
            "accent_hex": "#EAB308",
        }
    if "apel" in name:
        return {
            "banner_bg": "linear-gradient(135deg, #9A3412 0%, #7F1D1D 100%)",
            "banner_border": "#EF4444",
            "badge_bg": "rgba(239, 68, 68, 0.20)",
            "badge_color": "#FCA5A5",
            "btn_bg": "linear-gradient(135deg, #EA580C 0%, #DC2626 100%)",
            "btn_shadow": "0 4px 12px rgba(234, 88, 12, 0.30)",
            "addr_bg": "#FFF7ED",
            "addr_border": "#FDBA74",
            "addr_accent": "#EA580C",
            "addr_text": "#7C2D12",
            "accent_hex": "#EF4444",
        }
    return {
        "banner_bg": "linear-gradient(135deg, #0F172A 0%, #1E293B 100%)",
        "banner_border": "#DC2626",
        "badge_bg": "rgba(56, 189, 248, 0.15)",
        "badge_color": "#38BDF8",
        "btn_bg": "linear-gradient(135deg, #DC2626 0%, #B91C1C 100%)",
        "btn_shadow": "0 4px 12px rgba(220, 38, 38, 0.25)",
        "addr_bg": "#EFF6FF",
        "addr_border": "#BFDBFE",
        "addr_accent": "#2563EB",
        "addr_text": "#1E3A8A",
        "accent_hex": "#DC2626",
    }


# ====================================================
# CUSTOM CSS UNTUK UI MODERN & MOBILE-FRIENDLY
# ====================================================
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
    }

    /* Background Utama */
    .stApp {
        background-color: #F8FAFC;
        color: #1E293B;
    }

    /* Header Login */
    .login-header {
        background: linear-gradient(135deg, #DC2626 0%, #991B1B 100%);
        padding: 32px 24px;
        border-radius: 20px;
        color: white;
        text-align: center;
        box-shadow: 0 12px 28px -6px rgba(220, 38, 38, 0.35);
        margin-bottom: 24px;
        position: relative;
        overflow: hidden;
    }
    .login-header h1 {
        margin: 0;
        font-size: 1.65rem;
        font-weight: 800;
        letter-spacing: -0.02em;
    }
    .login-header p {
        margin: 6px 0 0 0;
        font-size: 0.9rem;
        color: #FEE2E2;
        font-weight: 500;
    }

    /* Styling Container / Card */
    .ui-card {
        background-color: #FFFFFF;
        padding: 22px;
        border-radius: 16px;
        border: 1px solid #E2E8F0;
        box-shadow: 0 4px 12px -2px rgba(15, 23, 42, 0.04);
        margin-bottom: 16px;
    }

    /* Form Styling */
    [data-testid="stForm"] {
        background-color: #FFFFFF;
        padding: 24px 20px;
        border-radius: 18px;
        border: 1px solid #E2E8F0;
        box-shadow: 0 8px 20px -4px rgba(15, 23, 42, 0.05);
    }

    /* Tombol Utama & Submit */
    [data-testid="stFormSubmitButton"] > button,
    div.stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #DC2626 0%, #B91C1C 100%) !important;
        color: #FFFFFF !important;
        font-weight: 700 !important;
        font-size: 0.95rem !important;
        padding: 0.65rem 1.2rem !important;
        border-radius: 12px !important;
        border: none !important;
        box-shadow: 0 4px 12px rgba(220, 38, 38, 0.25) !important;
        transition: all 0.2s ease !important;
    }
    [data-testid="stFormSubmitButton"] > button:hover,
    div.stButton > button[kind="primary"]:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 16px rgba(220, 38, 38, 0.35) !important;
    }

    /* Tombol Sekunder */
    div.stButton > button[kind="secondary"] {
        background-color: #FFFFFF !important;
        color: #334155 !important;
        font-weight: 600 !important;
        border: 1px solid #CBD5E1 !important;
        border-radius: 12px !important;
        padding: 0.6rem 1rem !important;
        transition: all 0.2s ease !important;
    }
    div.stButton > button[kind="secondary"]:hover {
        border-color: #94A3B8 !important;
        background-color: #F1F5F9 !important;
    }

    /* Input Fields */
    .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] > div {
        border-radius: 10px !important;
        border-color: #CBD5E1 !important;
    }

    /* User Banner setelah Login */
    .user-banner {
        background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%);
        color: #F8FAFC;
        padding: 18px 20px;
        border-radius: 16px;
        margin-bottom: 16px;
        box-shadow: 0 8px 20px -4px rgba(15, 23, 42, 0.2);
        border-left: 5px solid #DC2626;
    }
    .user-banner-title {
        font-size: 1.1rem;
        font-weight: 700;
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 6px;
    }
    .badge-mode {
        background-color: rgba(56, 189, 248, 0.15);
        color: #38BDF8;
        padding: 3px 10px;
        border-radius: 999px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .user-banner-sub {
        font-size: 0.85rem;
        color: #CBD5E1;
    }

    /* KPI Dashboard Card */
    .dashboard-card {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        padding: 18px;
        border-radius: 16px;
        box-shadow: 0 4px 10px -2px rgba(15, 23, 42, 0.04);
        margin-bottom: 12px;
        min-height: 138px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        transition: transform 0.2s ease;
    }
    .dashboard-card:hover {
        transform: translateY(-2px);
        border-color: #CBD5E1;
    }
    .card-value {
        font-size: 1.75rem;
        font-weight: 800;
        color: #0F172A;
        line-height: 1.15;
    }
    .card-value-green {
        font-size: 1.75rem;
        font-weight: 800;
        color: #16A34A;
        line-height: 1.15;
    }
    .card-subtext {
        font-size: 0.8rem;
        color: #64748B;
        margin-top: 4px;
    }
    .card-label {
        font-size: 0.88rem;
        color: #475569;
        font-weight: 600;
        margin-top: 8px;
    }

    /* Progress Bar */
    .progress-bar-container {
        width: 100%;
        background-color: #E2E8F0;
        border-radius: 999px;
        height: 8px;
        margin: 10px 0 4px 0;
        overflow: hidden;
    }
    .progress-bar-fill {
        height: 100%;
        background: linear-gradient(90deg, #16A34A 0%, #22C55E 100%);
        border-radius: 999px;
    }

    /* Box Alamat Warkop */
    .address-box {
        background-color: #EFF6FF;
        border: 1px solid #BFDBFE;
        border-left: 4px solid #2563EB;
        padding: 12px 16px;
        border-radius: 12px;
        font-size: 0.88rem;
        color: #1E3A8A;
        margin-top: 8px;
        margin-bottom: 16px;
    }

    /* Section Title Pill */
    .section-title {
        font-size: 1.05rem;
        font-weight: 700;
        color: #0F172A;
        margin: 18px 0 10px 0;
        display: flex;
        align-items: center;
        gap: 8px;
    }

    .footer-note {
        text-align: center;
        font-size: 0.78rem;
        color: #94A3B8;
        margin-top: 24px;
        padding-bottom: 16px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def apply_team_theme_css(team_name: str):
    """Menerapkan gaya CSS tema warna dinamis pada halaman User (SPG & Supervisi)."""
    t = get_team_theme(team_name)
    st.markdown(
        f"""
        <style>
        .user-banner {{
            background: {t["banner_bg"]} !important;
            border-left: 5px solid {t["banner_border"]} !important;
        }}
        .badge-mode {{
            background-color: {t["badge_bg"]} !important;
            color: {t["badge_color"]} !important;
        }}
        [data-testid="stFormSubmitButton"] > button,
        div.stButton > button[kind="primary"] {{
            background: {t["btn_bg"]} !important;
            box-shadow: {t["btn_shadow"]} !important;
        }}
        .address-box {{
            background-color: {t["addr_bg"]} !important;
            border: 1px solid {t["addr_border"]} !important;
            border-left: 4px solid {t["addr_accent"]} !important;
            color: {t["addr_text"]} !important;
        }}
        .section-title {{
            border-left: 4px solid {t["accent_hex"]};
            padding-left: 10px;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ====================================================
# DEFINISI FILE DATABASE LOKAL & KONFIGURASI GOOGLE SHEET
# ====================================================
WEB_APP_URL = "https://script.google.com/macros/s/AKfycbzk6tqiNonaArNjJt7X0IIhja_D7elgGLkNPE90xmDtvdHwNeq4VhZJQfUU2OE_jiA/exec"

DB_FILE = "rekap_laporan_spg.csv"
DB_SUPERVISI_KONTAK_FILE = "rekap_kontak_supervisi.csv"
MASTER_BRAND_FILE = "master_brand_rokok.json"
MASTER_TARGET_FILE = "master_target_brand.json"
MASTER_HARGA_FILE = "master_harga_konsumen.json"
STOK_SUPERVISI_FILE = "stok_rokok_supervisi.json"
MASTER_LOKASI_FILE = "Master WarkopLKK.xlsx"
MASTER_SPG_FILE = "master_nama_spg.json"
MASTER_TEAM_BRAND_FILE = "master_team_brand.json"
MASTER_PLAT_FILE = "master_plat_kendaraan.json"
MASTER_TEAM_NAME_FILE = "master_nama_team.json"
JADWAL_SPG_FILE = "Jadwal SPG.xlsx"

EXPECTED_COLUMNS = [
    "Waktu",
    "Promotor",
    "Plat_Mobil",
    "Nama_SPG",
    "Kota_Kab",
    "Kecamatan",
    "Warkop_LKK",
    "Alamat_Warkop",
    "Brand_Rokok",
    "Nama_Konsumen",
    "Gender",
    "Range_Umur",
    "No_HP",
    "Instagram",
    "Jumlah_Bungkus",
    "Rokok_Asal_BUMO",
    "Latitude",
    "Longitude",
]

EXPECTED_SUPERVISI_COLUMNS = [
    "Waktu",
    "Promotor",
    "Plat_Mobil",
    "Kota_Kab",
    "Kecamatan",
    "Warkop_LKK",
    "Alamat_Warkop",
    "Jumlah_Kontak_Manual",
]

LOCKED_LKK_POINT_FILE = "titik_lkk_aktif_team.json"
WARKOP_VISIT_STATUS_FILE = "status_warkop_kunjungan.json"

VISIT_STATUS_WAJIB = "Wajib Kunjung"
VISIT_STATUS_TIDAK_WAJIB = "Opsional"
VISIT_STATUS_OPTIONS = [VISIT_STATUS_WAJIB, VISIT_STATUS_TIDAK_WAJIB]

DEFAULT_HARGA_KONSUMEN = {
    "Black Matcha K12": 22000,
    "D.Super 12": 24000,
    "D.Super Kretek": 16000,
    "D.76 Apel Royal": 18000,
    "D.76 Apel": 16000,
    "Djarum 76 Aksara": 16000,
    "Black Matcha Siro": 23000,
    "Black Matcha Kuro": 23000,
}

DEFAULT_BRANDS = [
    "D.Super 12",
    "D.Super Kretek",
    "D.76 Apel",
    "D.76 Apel Royal",
    "Black Matcha K12",
    "Djarum 76 Aksara",
    "Black Matcha Siro",
    "Black Matcha Kuro",
]
DEFAULT_SPGS = ["Nanda"]
DEFAULT_PLATS = ["L 1234 ABC"]

DEFAULT_TARGET_RULES = {
    "Black Matcha K12": {"target_spg": 40, "target_team": 80, "group": "Black_Matcha"},
    "D.Super 12": {"target_spg": 40, "target_team": 80, "group": "D_Super"},
    "D.Super Kretek": {"target_spg": 40, "target_team": 80, "group": "D_Super"},
    "D.76 Apel Royal": {"target_spg": 40, "target_team": 80},
    "D.76 Apel": {"target_spg": 30, "target_team": 60},
    "Djarum 76 Aksara": {"target_spg": 30, "target_team": 60},
    "Black Matcha Siro": {"target_spg": 40, "target_team": 80, "group": "Black_Matcha"},
    "Black Matcha Kuro": {"target_spg": 40, "target_team": 80, "group": "Black_Matcha"},
}

TARGET_GROUP_LABELS = {
    "D_Super": "D. Super (Gabungan)",
    "Black_Matcha": "Black Matcha (Gabungan)",
    "Black_Siro_Kuro": "Black Matcha (Gabungan)",
}
TARGET_GROUP_OPTIONS = {
    "": "Tidak digabungkan",
    "D_Super": TARGET_GROUP_LABELS["D_Super"],
    "Black_Matcha": TARGET_GROUP_LABELS["Black_Matcha"],
}


def normalize_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def normalize_brand_key(brand):
    return "".join(str(brand).casefold().split())


def get_custom_week_info(dt):
    if pd.isna(dt):
        return "-", "-"
    d = pd.to_datetime(dt).date()
    wd = d.weekday()

    if wd == 5:
        fri_date = d + timedelta(days=6)
    elif wd == 6:
        fri_date = d + timedelta(days=5)
    else:
        fri_date = d + timedelta(days=(4 - wd))

    _, iso_w, _ = fri_date.isocalendar()
    periode_label = f"Minggu ke-{iso_w}"
    return periode_label, iso_w


def add_custom_week_columns(df, date_col="Waktu_Dt"):
    if df.empty or date_col not in df.columns:
        df["Periode_Minggu"] = "-"
        return df
    periods = []
    for val in df[date_col]:
        p_label, _ = get_custom_week_info(val)
        periods.append(p_label)
    df["Periode_Minggu"] = periods
    return df


def _file_mtime(path: str) -> float:
    return os.path.getmtime(path) if os.path.exists(path) else 0.0


@st.cache_data(show_spinner=False)
def _cached_read_csv(path: str, mtime: float) -> pd.DataFrame:
    return pd.read_csv(path)


@st.cache_data(show_spinner=False)
def _cached_read_excel(path: str, mtime: float) -> pd.DataFrame:
    df = pd.read_excel(path)
    df.columns = [str(c).strip() for c in df.columns]
    return df


@st.cache_data(show_spinner=False)
def _cached_read_json(path: str, mtime: float):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(show_spinner=False)
def _cached_read_json_no_mtime(path: str) -> dict | list | None:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ====================================================
# STOK & HARGA KONSUMEN
# ====================================================
def _stok_sup_key(tanggal_str: str, team_name: str, brand_name: str) -> str:
    return "|".join([
        str(tanggal_str or "").strip(),
        str(team_name or "").strip().casefold(),
        str(brand_name or "").strip().casefold(),
    ])


def load_stok_supervisi() -> dict:
    data = _cached_read_json_no_mtime(STOK_SUPERVISI_FILE)
    return data if isinstance(data, dict) else {}


def save_stok_supervisi(stok_map: dict) -> bool:
    cleaned = {}
    for k, v in (stok_map or {}).items():
        try:
            cleaned[str(k)] = max(0, int(float(v)))
        except (ValueError, TypeError):
            cleaned[str(k)] = 0
    with open(STOK_SUPERVISI_FILE, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)
    st.cache_data.clear()
    return True


def get_stok_awal_supervisi(tanggal_str: str, team_name: str, brand_name: str, stok_map: dict | None = None) -> int:
    smap = stok_map if isinstance(stok_map, dict) else load_stok_supervisi()
    key = _stok_sup_key(tanggal_str, team_name, brand_name)
    val = smap.get(key, 0)
    try:
        return max(0, int(float(val)))
    except (ValueError, TypeError):
        return 0


def load_harga_konsumen() -> dict:
    data = _cached_read_json_no_mtime(MASTER_HARGA_FILE)
    if isinstance(data, dict) and data:
        cleaned = {}
        for k, v in data.items():
            label = str(k or "").strip()
            if label:
                try:
                    cleaned[label] = max(0, int(float(v)))
                except (ValueError, TypeError):
                    cleaned[label] = 0
        if cleaned:
            return cleaned
    return dict(DEFAULT_HARGA_KONSUMEN)


def save_harga_konsumen(harga_map: dict) -> bool:
    cleaned = {}
    for k, v in (harga_map or {}).items():
        label = str(k or "").strip()
        if label:
            try:
                cleaned[label] = max(0, int(float(v)))
            except (ValueError, TypeError):
                cleaned[label] = 0
    with open(MASTER_HARGA_FILE, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)
    st.cache_data.clear()
    return True


def get_harga_konsumen_brand(brand: str, harga_map: dict | None = None) -> int:
    hmap = harga_map if isinstance(harga_map, dict) else load_harga_konsumen()
    b_key = normalize_brand_key(brand)
    if not b_key:
        return 0
    for k, v in hmap.items():
        if normalize_brand_key(k) == b_key:
            try:
                return max(0, int(float(v)))
            except (ValueError, TypeError):
                return 0
    return 0


# ====================================================
# STATUS WARKOP & LOCK TITIK LKK
# ====================================================
def _warkop_status_key(kota: str, kecamatan: str, warkop: str) -> str:
    return "|".join([
        str(kota or "").strip().casefold(),
        str(kecamatan or "").strip().casefold(),
        str(warkop or "").strip().casefold(),
    ])


def load_warkop_visit_status_map() -> dict:
    if os.path.exists(WARKOP_VISIT_STATUS_FILE):
        try:
            with open(WARKOP_VISIT_STATUS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {}


def save_warkop_visit_status_map(status_map: dict) -> bool:
    try:
        cleaned = {}
        for k, v in (status_map or {}).items():
            val = str(v or "").strip()
            if val in VISIT_STATUS_OPTIONS:
                cleaned[str(k)] = val
            elif "tidak" in val.casefold() or "opsional" in val.casefold():
                cleaned[str(k)] = VISIT_STATUS_TIDAK_WAJIB
            else:
                cleaned[str(k)] = VISIT_STATUS_WAJIB
        with open(WARKOP_VISIT_STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(cleaned, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        st.error(f"Gagal menyimpan status warkop wajib/tidak wajib: {e}")
        return False


def get_warkop_visit_status(kota: str, kecamatan: str, warkop: str, status_map: dict | None = None) -> str:
    smap = status_map if isinstance(status_map, dict) else load_warkop_visit_status_map()
    key = _warkop_status_key(kota, kecamatan, warkop)
    raw_val = smap.get(key)
    if raw_val in VISIT_STATUS_OPTIONS:
        return raw_val
    suffix = f"|{str(kecamatan or '').strip().casefold()}|{str(warkop or '').strip().casefold()}"
    for k, v in smap.items():
        if str(k).endswith(suffix) and v in VISIT_STATUS_OPTIONS:
            return v
    return VISIT_STATUS_TIDAK_WAJIB


def build_warkop_status_dataframe(df_lokasi: pd.DataFrame, status_map: dict | None = None) -> pd.DataFrame:
    smap = status_map if isinstance(status_map, dict) else load_warkop_visit_status_map()
    empty_cols = ["Kota", "Kecamatan", "Nama Warkop / LKK", "Alamat Warkop / LKK", "Status Kunjungan"]
    if df_lokasi is None or df_lokasi.empty:
        return pd.DataFrame(columns=empty_cols)

    c_kota = next((c for c in df_lokasi.columns if "kota" in str(c).lower()), None)
    c_kec = next((c for c in df_lokasi.columns if "kec" in str(c).lower() or "wilayah" in str(c).lower()), None)
    c_wrk = next((c for c in df_lokasi.columns if "warkop" in str(c).lower() or "lkk" in str(c).lower() or "nama" in str(c).lower()), None)
    c_alm = next((c for c in df_lokasi.columns if "alamat" in str(c).lower() or "address" in str(c).lower()), None)

    out = pd.DataFrame({
        "Kota": df_lokasi[c_kota].astype(str).str.strip().replace("", "Surabaya") if c_kota else "Surabaya",
        "Kecamatan": df_lokasi[c_kec].astype(str).str.strip() if c_kec else "",
        "Nama Warkop / LKK": df_lokasi[c_wrk].astype(str).str.strip() if c_wrk else "",
        "Alamat Warkop / LKK": (df_lokasi[c_alm].astype(str).str.strip().replace("", "-") if c_alm else "-"),
    })
    out = out[out["Nama Warkop / LKK"] != ""].reset_index(drop=True)

    out["Status Kunjungan"] = [
        get_warkop_visit_status(k, kc, w, smap)
        for k, kc, w in zip(out["Kota"], out["Kecamatan"], out["Nama Warkop / LKK"])
    ]
    return out[empty_cols]


def load_locked_lkk_points() -> dict:
    if os.path.exists(LOCKED_LKK_POINT_FILE):
        try:
            with open(LOCKED_LKK_POINT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def save_locked_lkk_point(team_name: str, point_info: dict) -> bool:
    today_str = (datetime.utcnow() + timedelta(hours=7)).strftime("%Y-%m-%d")
    all_locked = load_locked_lkk_points()
    key = str(team_name or "").strip().casefold()
    payload = dict(point_info)
    payload["status_kunjungan"] = str(payload.get("status_kunjungan") or VISIT_STATUS_WAJIB).strip()
    payload["tanggal"] = today_str
    payload["locked_at"] = (datetime.utcnow() + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S")
    all_locked[key] = payload
    try:
        with open(LOCKED_LKK_POINT_FILE, "w", encoding="utf-8") as f:
            json.dump(all_locked, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        st.error(f"Gagal menyimpan titik LKK aktif: {e}")
        return False


def get_active_locked_lkk_point_today(team_name: str, fallback_kota: str = "") -> dict | None:
    """Mengambil titik LKK yang sudah di-save / di-lock oleh Supervisi untuk team hari ini (WIB)."""
    today_str = (datetime.utcnow() + timedelta(hours=7)).strftime("%Y-%m-%d")
    all_locked = load_locked_lkk_points()
    key = str(team_name or "").strip().casefold()
    entry = all_locked.get(key)
    if not isinstance(entry, dict):
        return None
    if str(entry.get("tanggal", "")).strip() != today_str:
        return None
    warkop = str(entry.get("warkop", "") or "").strip()
    if not warkop:
        return None
    kota = str(entry.get("kota", fallback_kota) or fallback_kota).strip()
    if fallback_kota and kota and kota.casefold() != str(fallback_kota).strip().casefold():
        return None
    kec = str(entry.get("kecamatan", "") or "").strip()
    status_kunjungan = str(entry.get("status_kunjungan") or "").strip()
    if status_kunjungan not in VISIT_STATUS_OPTIONS:
        status_kunjungan = get_warkop_visit_status(kota, kec, warkop)
    return {
        "kota": kota,
        "kecamatan": kec,
        "warkop": warkop,
        "alamat": str(entry.get("alamat", "-") or "-").strip() or "-",
        "status_kunjungan": status_kunjungan,
        "locked_at": str(entry.get("locked_at", "") or "").strip(),
    }


# ====================================================
# BACKUP & RESTORE (GOOGLE SHEET & SUPABASE)
# ====================================================
def df_to_sheet_rows(df: pd.DataFrame):
    if df is None:
        return []
    columns = [str(column) for column in df.columns]
    if df.empty:
        return [columns] if columns else []

    rows = []
    for row in df.itertuples(index=False, name=None):
        serialized_row = []
        for value in row:
            if pd.isna(value):
                serialized_row.append("")
            elif isinstance(value, (datetime, pd.Timestamp)):
                serialized_row.append(value.strftime("%Y-%m-%d %H:%M:%S"))
            elif isinstance(value, date):
                serialized_row.append(value.isoformat())
            else:
                serialized_row.append(str(value))
        rows.append(serialized_row)

    return [columns] + rows


def google_json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    item = getattr(value, "item", None)
    if callable(item):
        return item()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def sheet_rows_to_df(rows, expected_columns=None):
    if not rows:
        return pd.DataFrame(columns=expected_columns)

    columns = [str(column) for column in rows[0]]
    df = pd.DataFrame(rows[1:], columns=columns)
    if expected_columns is not None:
        for column in expected_columns:
            if column not in df.columns:
                df[column] = ""
        return df[expected_columns]
    return df


def post_google_sheet(payload):
    payload_json = json.dumps(payload, ensure_ascii=False, default=google_json_default)
    response = requests.post(
        WEB_APP_URL,
        data=payload_json,
        headers={"Content-Type": "application/json"},
        timeout=(10, 120),
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(
            f"Google Apps Script mengembalikan HTTP {response.status_code} "
            f"(Content-Type: {response.headers.get('Content-Type', 'tidak diketahui')})."
        ) from exc

    try:
        result = response.json()
    except ValueError as exc:
        raise RuntimeError(
            "Google Apps Script tidak mengembalikan JSON "
            f"(HTTP {response.status_code}, "
            f"Content-Type: {response.headers.get('Content-Type', 'tidak diketahui')}). "
            "Periksa URL Web App, akses deployment, dan handler doPost."
        ) from exc

    if not isinstance(result, dict):
        raise RuntimeError("Format respons Google Apps Script tidak valid.")
    return result


def load_supabase_backup_data():
    df_rekap = pd.read_csv(DB_FILE) if os.path.exists(DB_FILE) else pd.DataFrame(columns=EXPECTED_COLUMNS)
    df_sup = pd.read_csv(DB_SUPERVISI_KONTAK_FILE) if os.path.exists(DB_SUPERVISI_KONTAK_FILE) else pd.DataFrame(columns=EXPECTED_SUPERVISI_COLUMNS)
    df_jdw = pd.read_excel(JADWAL_SPG_FILE) if os.path.exists(JADWAL_SPG_FILE) else pd.DataFrame()
    df_wrk = pd.read_excel(MASTER_LOKASI_FILE) if os.path.exists(MASTER_LOKASI_FILE) else pd.DataFrame()

    def read_json_file(file_path):
        if not os.path.exists(file_path):
            return None
        with open(file_path, "r", encoding="utf-8") as file:
            return json.load(file)

    return {
        "backup_version": 1,
        "datasets": {
            "rekap_laporan": df_to_sheet_rows(df_rekap),
            "rekap_supervisi": df_to_sheet_rows(df_sup),
            "jadwal_spg": df_to_sheet_rows(df_jdw),
            "master_warkop": df_to_sheet_rows(df_wrk),
        },
        "master_data": {
            "nama_spg": read_json_file(MASTER_SPG_FILE),
            "nama_team": read_json_file(MASTER_TEAM_NAME_FILE),
            "team_brand": read_json_file(MASTER_TEAM_BRAND_FILE),
            "brand_rokok": read_json_file(MASTER_BRAND_FILE),
            "target_brand": read_json_file(MASTER_TARGET_FILE),
            "harga_konsumen": read_json_file(MASTER_HARGA_FILE),
            "plat_kendaraan": read_json_file(MASTER_PLAT_FILE),
            "jadwal_detail": read_json_file(SCHEDULE_DETAIL_FILE),
        },
    }


def get_supabase_config():
    try:
        supabase_url = st.secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL"))
        supabase_key = st.secrets.get("SUPABASE_KEY", os.environ.get("SUPABASE_KEY"))
    except FileNotFoundError:
        supabase_url = os.environ.get("SUPABASE_URL")
        supabase_key = os.environ.get("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        raise RuntimeError(
            "Konfigurasi SUPABASE_URL dan SUPABASE_KEY belum tersedia di Streamlit secrets atau environment."
        )

    return supabase_url.rstrip("/"), supabase_key


def post_supabase_backup(snapshot):
    supabase_url, supabase_key = get_supabase_config()
    response = requests.post(
        f"{supabase_url}/rest/v1/app_backups",
        json={"data": snapshot},
        headers={
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        timeout=(10, 120),
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(
            f"Supabase mengembalikan HTTP {response.status_code}: {response.text[:500]}"
        ) from exc


def get_latest_supabase_backup():
    supabase_url, supabase_key = get_supabase_config()
    response = requests.get(
        f"{supabase_url}/rest/v1/app_backups",
        params={
            "select": "id,created_at,data",
            "order": "created_at.desc,id.desc",
            "limit": "1",
        },
        headers={
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
        },
        timeout=(10, 120),
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(
            f"Supabase mengembalikan HTTP {response.status_code}: {response.text[:500]}"
        ) from exc

    try:
        backups = response.json()
    except ValueError as exc:
        raise RuntimeError("Supabase tidak mengembalikan JSON yang valid.") from exc

    if not isinstance(backups, list):
        raise RuntimeError("Format respons backup Supabase tidak valid.")
    if not backups:
        raise RuntimeError("Belum ada backup yang tersimpan di Supabase.")
    if not isinstance(backups[0], dict) or not isinstance(backups[0].get("data"), dict):
        raise RuntimeError("Isi backup terbaru di Supabase tidak valid.")
    return backups[0]


def restore_supabase_backup(snapshot):
    if not isinstance(snapshot, dict) or snapshot.get("backup_version") != 1:
        raise RuntimeError("Versi atau format backup Supabase tidak didukung.")

    datasets = snapshot.get("datasets")
    master_data = snapshot.get("master_data")
    if not isinstance(datasets, dict) or not isinstance(master_data, dict):
        raise RuntimeError("Struktur data backup Supabase tidak lengkap.")

    dataset_specs = {
        "rekap_laporan": (DB_FILE, EXPECTED_COLUMNS, "csv"),
        "rekap_supervisi": (DB_SUPERVISI_KONTAK_FILE, EXPECTED_SUPERVISI_COLUMNS, "csv"),
        "jadwal_spg": (JADWAL_SPG_FILE, None, "excel"),
        "master_warkop": (MASTER_LOKASI_FILE, None, "excel"),
    }
    file_contents = {}
    for dataset_name, (file_path, expected_columns, file_type) in dataset_specs.items():
        rows = datasets.get(dataset_name)
        if not isinstance(rows, list):
            raise RuntimeError(f"Data `{dataset_name}` tidak ditemukan pada backup Supabase.")
        dataframe = sheet_rows_to_df(rows, expected_columns)
        if file_type == "csv":
            file_contents[file_path] = dataframe.to_csv(index=False).encode("utf-8")
        else:
            excel_buffer = BytesIO()
            dataframe.to_excel(excel_buffer, index=False)
            file_contents[file_path] = excel_buffer.getvalue()

    master_file_paths = {
        "nama_spg": MASTER_SPG_FILE,
        "nama_team": MASTER_TEAM_NAME_FILE,
        "team_brand": MASTER_TEAM_BRAND_FILE,
        "brand_rokok": MASTER_BRAND_FILE,
        "target_brand": MASTER_TARGET_FILE,
        "harga_konsumen": MASTER_HARGA_FILE,
        "plat_kendaraan": MASTER_PLAT_FILE,
        "jadwal_detail": SCHEDULE_DETAIL_FILE,
    }
    files_to_remove = []
    for master_name, file_path in master_file_paths.items():
        if master_name not in master_data:
            raise RuntimeError(f"Data master `{master_name}` tidak ditemukan pada backup Supabase.")
        master_value = master_data[master_name]
        if master_value is None:
            files_to_remove.append(file_path)
        else:
            file_contents[file_path] = json.dumps(
                master_value, ensure_ascii=False, indent=2
            ).encode("utf-8")

    staged_files = {}
    try:
        for file_path, content in file_contents.items():
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=os.path.dirname(os.path.abspath(file_path)),
                prefix=f".{os.path.basename(file_path)}.",
                suffix=".tmp",
                delete=False,
            ) as staged_file:
                staged_file.write(content)
                staged_files[file_path] = staged_file.name

        for file_path, staged_path in staged_files.items():
            os.replace(staged_path, file_path)
        for file_path in files_to_remove:
            if os.path.exists(file_path):
                os.remove(file_path)
    finally:
        for staged_path in staged_files.values():
            if os.path.exists(staged_path):
                os.remove(staged_path)


def render_google_sheet_backup_controls():
    with st.expander("☁️ Backup & Load Data", expanded=False):
        st.caption("Backup data aplikasi ke Google Spreadsheet atau Supabase.")

        col_backup_gs, col_backup_supabase = st.columns(2)
        with col_backup_gs:
            btn_backup_gs = st.button(
                "⬆️ Backup ke Sheet",
                use_container_width=True,
                key="backup_google_sheet",
            )
        with col_backup_supabase:
            btn_backup_supabase = st.button(
                "⬆️ Backup ke Supabase",
                use_container_width=True,
                key="backup_supabase",
            )
        col_load_gs, col_load_supabase = st.columns(2)
        with col_load_gs:
            btn_load_gs = st.button(
                "⬇️ Load dari Sheet",
                use_container_width=True,
                key="load_google_sheet",
            )
        with col_load_supabase:
            btn_load_supabase = st.button(
                "⬇️ Load dari Supabase",
                use_container_width=True,
                key="load_supabase",
            )

        if btn_backup_gs:
            try:
                with st.spinner("Mem-backup data ke Google Sheet..."):
                    snapshot = load_supabase_backup_data()
                    ds = snapshot["datasets"]
                    payload = {
                        "action": "backup",
                        "rekap_laporan": ds["rekap_laporan"],
                        "rekap_supervisi": ds["rekap_supervisi"],
                        "jadwal_spg": ds["jadwal_spg"],
                        "master_warkop": ds["master_warkop"],
                    }
                    res_json = post_google_sheet(payload)
                    if res_json.get("status") == "success":
                        st.success("✅ " + res_json.get("message", "Backup berhasil!"))
                    else:
                        st.error("❌ " + res_json.get("message", "Gagal backup."))
            except Exception as e:
                st.error(f"Error backup: {e}")
        if btn_backup_supabase:
            try:
                with st.spinner("Mem-backup data ke Supabase..."):
                    snapshot = load_supabase_backup_data()
                    post_supabase_backup(snapshot)
                    st.success("✅ Backup berhasil disimpan ke Supabase.")
            except Exception as e:
                st.error(f"Error backup Supabase: {e}")

        if btn_load_supabase:
            try:
                with st.spinner("Memuat backup terbaru dari Supabase..."):
                    backup = get_latest_supabase_backup()
                    restore_supabase_backup(backup["data"])
                    st.cache_data.clear()
                    st.success(
                        f"✅ Backup Supabase {backup.get('created_at', '')} "
                        "berhasil dimuat. Data lokal telah diganti."
                    )
                    st.rerun()
            except Exception as e:
                st.error(f"Error load Supabase: {e}")

        if btn_load_gs:
            try:
                with st.spinner("Memuat data dari Google Sheet..."):
                    res_json = post_google_sheet({"action": "load"})
                    if res_json.get("status") == "success":
                        data_gs = res_json.get("data", {})

                        if "rekap_laporan" in data_gs and len(data_gs["rekap_laporan"]) > 0:
                            sheet_rows_to_df(data_gs["rekap_laporan"], EXPECTED_COLUMNS).to_csv(DB_FILE, index=False)
                        if "rekap_supervisi" in data_gs and len(data_gs["rekap_supervisi"]) > 0:
                            sheet_rows_to_df(data_gs["rekap_supervisi"], EXPECTED_SUPERVISI_COLUMNS).to_csv(DB_SUPERVISI_KONTAK_FILE, index=False)
                        if "jadwal_spg" in data_gs and len(data_gs["jadwal_spg"]) > 0:
                            sheet_rows_to_df(data_gs["jadwal_spg"]).to_excel(JADWAL_SPG_FILE, index=False)
                        if "master_warkop" in data_gs and len(data_gs["master_warkop"]) > 0:
                            sheet_rows_to_df(data_gs["master_warkop"]).to_excel(MASTER_LOKASI_FILE, index=False)

                        st.cache_data.clear()
                        st.success("✅ Data berhasil dimuat dari Google Sheet!")
                        st.rerun()
                    else:
                        st.error("❌ " + res_json.get("message", "Gagal load."))
            except Exception as e:
                st.error(f"Error load: {e}")


# ====================================================
# DATABASE TRANSAKSI & SUPERVISI
# ====================================================
@st.cache_data(show_spinner=False)
def _cached_load_db_transformed(path: str, mtime: float) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "Usia" in df.columns and "Range_Umur" not in df.columns:
        df = df.rename(columns={"Usia": "Range_Umur"})
    for col in EXPECTED_COLUMNS:
        if col not in df.columns:
            df[col] = "-"
    return df[EXPECTED_COLUMNS]


def load_database():
    if os.path.exists(DB_FILE):
        try:
            return _cached_load_db_transformed(DB_FILE, _file_mtime(DB_FILE)).copy()
        except Exception:
            return pd.DataFrame(columns=EXPECTED_COLUMNS)
    return pd.DataFrame(columns=EXPECTED_COLUMNS)


def save_database(df):
    df.to_csv(DB_FILE, index=False)


@st.cache_data(show_spinner=False)
def _cached_load_sup_transformed(path: str, mtime: float) -> pd.DataFrame:
    df = pd.read_csv(path)
    for col in EXPECTED_SUPERVISI_COLUMNS:
        if col not in df.columns:
            df[col] = "-"
    return df[EXPECTED_SUPERVISI_COLUMNS]


def load_supervisi_database():
    if os.path.exists(DB_SUPERVISI_KONTAK_FILE):
        try:
            return _cached_load_sup_transformed(
                DB_SUPERVISI_KONTAK_FILE,
                _file_mtime(DB_SUPERVISI_KONTAK_FILE),
            ).copy()
        except Exception:
            return pd.DataFrame(columns=EXPECTED_SUPERVISI_COLUMNS)
    return pd.DataFrame(columns=EXPECTED_SUPERVISI_COLUMNS)


def save_supervisi_database(df):
    df.to_csv(DB_SUPERVISI_KONTAK_FILE, index=False)


def get_latest_supervisi_point_today(
    team_name: str,
    fallback_kota: str = "",
    fallback_kec: str = "",
    df_sup: pd.DataFrame | None = None,
) -> dict | None:
    today_str = (datetime.utcnow() + timedelta(hours=7)).strftime("%Y-%m-%d")
    if df_sup is None:
        df_sup = load_supervisi_database()
    if df_sup is None or df_sup.empty:
        return None

    mask = (
        df_sup["Promotor"].astype(str).str.strip().str.casefold()
        == str(team_name or "").strip().casefold()
    ) & (
        df_sup["Waktu"].astype(str).str.startswith(today_str)
    )
    if fallback_kota:
        mask = mask & (
            df_sup["Kota_Kab"].astype(str).str.strip().str.casefold()
            == str(fallback_kota).strip().casefold()
        )

    df_today = df_sup[mask].copy()
    if df_today.empty:
        return None

    parsed = pd.to_datetime(df_today["Waktu"], errors="coerce")
    if parsed.notna().any():
        df_today = df_today.assign(_dt=parsed).sort_values("_dt", ascending=False)
    else:
        df_today = df_today.iloc[::-1]

    for _, row in df_today.iterrows():
        warkop = str(row.get("Warkop_LKK", "") or "").strip()
        if warkop:
            return {
                "kota": str(row.get("Kota_Kab", fallback_kota) or fallback_kota).strip(),
                "kecamatan": str(row.get("Kecamatan", fallback_kec) or fallback_kec).strip(),
                "warkop": warkop,
                "alamat": str(row.get("Alamat_Warkop", "-") or "-").strip() or "-",
                "kontak": int(pd.to_numeric(row.get("Jumlah_Kontak_Manual", 0), errors="coerce") or 0),
                "waktu": str(row.get("Waktu", "") or "").strip(),
            }
    return None


# ====================================================
# MASTER WILAYAH / GEOJSON
# ====================================================
GEOJSON_INDEX_FILE = os.path.join("geojson_by_kecamatan", "_index.json")

KECAMATAN_BY_KOTA = {
    "Surabaya": [
        "Asem Rowo", "Benowo", "Bubutan", "Dukuh Pakis", "Genteng",
        "Karang Pilang", "Krembangan", "Lakarsantri", "Pabean Cantian",
        "Pakal", "Sambikerep", "Sawahan", "Sukomanunggal", "Tandes",
        "Tegalsari", "Wiyung",
    ],
    "Gresik": [
        "Balongpanggang", "Benjeng", "Bungah", "Cerme", "Driyorejo",
        "Duduksampeyan", "Dukun", "Gresik", "Kebomas", "Kedamean",
        "Manyar", "Menganti", "Panceng", "Sangkapura", "Sidayu",
        "Tambak", "Ujungpangkah", "Wringinanom",
    ],
}


@st.cache_data(ttl=3600, show_spinner=False)
def _get_kecamatan_filepath_map() -> dict:
    result = {}
    if os.path.exists(GEOJSON_INDEX_FILE):
        try:
            idx = _cached_read_json(GEOJSON_INDEX_FILE, _file_mtime(GEOJSON_INDEX_FILE))
            if isinstance(idx, dict):
                for k, v in idx.items():
                    if isinstance(v, dict) and v.get("file"):
                        result[str(k).strip().casefold()] = v["file"]
        except Exception:
            pass
    return result


@st.cache_data(ttl=3600, show_spinner=False)
def load_geojson_index(mtime: float = 0.0) -> dict:
    if os.path.exists(GEOJSON_INDEX_FILE):
        try:
            raw_idx = _cached_read_json(GEOJSON_INDEX_FILE, _file_mtime(GEOJSON_INDEX_FILE))
            if isinstance(raw_idx, dict):
                return {
                    str(k).strip().casefold(): {"nm_kecamatan": str(k).strip(), **v}
                    for k, v in raw_idx.items()
                    if isinstance(v, dict)
                }
        except Exception:
            pass
    return {}


def _resolve_kecamatan_filepath(nm_kecamatan: str) -> str | None:
    if not nm_kecamatan:
        return None
    target = str(nm_kecamatan).strip()
    fmap = _get_kecamatan_filepath_map()
    cand = fmap.get(target.casefold())
    if cand:
        if os.path.exists(cand):
            return cand
        base_cand = os.path.join("geojson_by_kecamatan", os.path.basename(cand))
        if os.path.exists(base_cand):
            return base_cand
    slug = re.sub(r"[^a-z0-9]+", "_", target.lower()).strip("_")
    fallback_path = os.path.join("geojson_by_kecamatan", f"{slug}.geojson")
    if os.path.exists(fallback_path):
        return fallback_path
    return None


@st.cache_data(ttl=3600, max_entries=40, show_spinner=False)
def load_kecamatan_geojson(nm_kecamatan: str, mtime: float = 0.0) -> dict | None:
    filepath = _resolve_kecamatan_filepath(nm_kecamatan)
    if not filepath:
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Gagal memuat GeoJSON kecamatan '{nm_kecamatan}': {e}")
        return None


@st.cache_data(ttl=3600, max_entries=40, show_spinner=False)
def load_kecamatan_gdf(nm_kecamatan: str, mtime: float = 0.0):
    data = load_kecamatan_geojson(nm_kecamatan, mtime)
    if not data:
        return None
    try:
        gdf = gpd.GeoDataFrame.from_features(data)
        if gdf.crs is None:
            gdf.set_crs("EPSG:4326", inplace=True)
        return gdf
    except Exception as e:
        st.error(f"Gagal memproses geometri kecamatan '{nm_kecamatan}': {e}")
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def build_polygon_features(kecamatan_tuple: tuple) -> list:
    gresik_set = {k.casefold() for k in KECAMATAN_BY_KOTA["Gresik"]}
    features = []
    for kec_name in kecamatan_tuple:
        gj = load_kecamatan_geojson(kec_name)
        if not gj or not isinstance(gj.get("features"), list):
            continue
        is_gresik = kec_name.strip().casefold() in gresik_set
        fill_col = [16, 185, 129, 35] if is_gresik else [30, 144, 255, 35]
        line_col = [5, 150, 105, 210] if is_gresik else [37, 99, 235, 210]
        kota_label = "Gresik" if is_gresik else "Surabaya"
        for feat in gj["features"]:
            props = dict(feat.get("properties") or {})
            props.setdefault("Kota_Wilayah", kota_label)
            props["fill_color"] = fill_col
            props["line_color"] = line_col
            features.append({
                "type": "Feature",
                "properties": props,
                "geometry": feat.get("geometry"),
            })
    return features


def get_geo_districts(kota: str) -> list[str]:
    k_norm = str(kota or "").strip().casefold()
    if k_norm == "surabaya":
        return sorted(KECAMATAN_BY_KOTA["Surabaya"])
    if k_norm == "gresik":
        return sorted(KECAMATAN_BY_KOTA["Gresik"])
    idx = load_geojson_index(_file_mtime(GEOJSON_INDEX_FILE))
    return sorted(v["nm_kecamatan"] for v in idx.values())


# ====================================================
# MASTER DATA LOADERS & SAVERS
# ====================================================
def load_master_team_names():
    default_teams = {f"Team SPG {i}": f"Team SPG {i}" for i in range(1, 21)}
    data = _cached_read_json_no_mtime(MASTER_TEAM_NAME_FILE)
    if not isinstance(data, dict):
        save_master_team_names(default_teams)
        return default_teams
    for i in range(1, 21):
        key = f"Team SPG {i}"
        if key not in data:
            data[key] = key
        else:
            data[key] = str(data[key]).strip()
    return data


def save_master_team_names(team_names_dict):
    active_names = [str(name).strip() for name in team_names_dict.values() if str(name).strip()]
    if not active_names:
        st.error("Minimal satu nama team harus diisi. Unggah jadwal SPG untuk mengatur nama team otomatis.")
        return False
    if len({name.casefold() for name in active_names}) != len(active_names):
        st.error("Nama team tidak boleh duplikat.")
        return False
    try:
        with open(MASTER_TEAM_NAME_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {
                    f"Team SPG {i}": str(team_names_dict.get(f"Team SPG {i}", "")).strip()
                    for i in range(1, 21)
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Gagal menyimpan master nama team: {e}")
        return False


def load_master_brands():
    data = _cached_read_json_no_mtime(MASTER_BRAND_FILE)
    return data if isinstance(data, list) else DEFAULT_BRANDS


def save_master_brands(brands):
    try:
        with open(MASTER_BRAND_FILE, "w", encoding="utf-8") as f:
            json.dump(brands, f, ensure_ascii=False, indent=2)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Gagal menyimpan file master_brand_rokok.json: {e}")
        return False


def load_master_team_brands():
    current_brands = load_master_brands()
    team_map = load_master_team_names()
    active_team_names = [team_map[f"Team SPG {i}"] for i in range(1, 21) if team_map[f"Team SPG {i}"]]
    default_teams = {
        team_name: match_brands_by_team_name(team_name, current_brands)
        for team_name in active_team_names
    }
    data = _cached_read_json_no_mtime(MASTER_TEAM_BRAND_FILE)
    if not isinstance(data, dict):
        save_master_team_brands(default_teams)
        return default_teams
    for i, t_name in enumerate(active_team_names, start=1):
        t_key = f"Team SPG {i}"
        if t_name not in data and t_key not in data:
            data[t_name] = match_brands_by_team_name(t_name, current_brands)
    return data


def save_master_team_brands(team_brands):
    try:
        cleaned_data = {
            str(team): [str(b).strip() for b in brands]
            for team, brands in team_brands.items()
        }
        with open(MASTER_TEAM_BRAND_FILE, "w", encoding="utf-8") as f:
            json.dump(cleaned_data, f, ensure_ascii=False, indent=2)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"❌ Gagal menyimpan ke `{MASTER_TEAM_BRAND_FILE}`: {e}")
        return False


def load_master_plat_kendaraan():
    data = _cached_read_json_no_mtime(MASTER_PLAT_FILE)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return list(data.values())
    return DEFAULT_PLATS


def save_master_plat_kendaraan(plat_list):
    with open(MASTER_PLAT_FILE, "w", encoding="utf-8") as f:
        json.dump(plat_list, f, ensure_ascii=False, indent=2)
    st.cache_data.clear()


def load_master_spgs():
    data = _cached_read_json_no_mtime(MASTER_SPG_FILE)
    return data if isinstance(data, list) else DEFAULT_SPGS


def save_master_spgs(spgs):
    with open(MASTER_SPG_FILE, "w", encoding="utf-8") as f:
        json.dump(spgs, f, ensure_ascii=False, indent=2)
    st.cache_data.clear()


def load_master_lokasi_excel():
    if os.path.exists(MASTER_LOKASI_FILE):
        try:
            return _cached_read_excel(MASTER_LOKASI_FILE, _file_mtime(MASTER_LOKASI_FILE)).copy()
        except Exception as e:
            st.error(f"Gagal membaca file Excel {MASTER_LOKASI_FILE}: {e}")
            return pd.DataFrame(columns=["Kota", "Kecamatan", "Nama Warkop / LKK", "Alamat Warkop / LKK"])
    return pd.DataFrame(
        columns=["Kota", "Kecamatan", "Nama Warkop / LKK", "Alamat Warkop / LKK"],
        data=[
            ["Surabaya", "Kecamatan Default", "Warkop Cak No", "-"],
            ["Surabaya", "Kecamatan Default", "Warkop Pitoe", "-"],
        ],
    )


def save_master_lokasi_excel(df_excel):
    try:
        df_excel.to_excel(MASTER_LOKASI_FILE, index=False)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Gagal menyimpan file Excel: {e}")
        return False


def load_jadwal_spg():
    if os.path.exists(JADWAL_SPG_FILE):
        try:
            return _cached_read_excel(JADWAL_SPG_FILE, _file_mtime(JADWAL_SPG_FILE)).copy()
        except Exception as e:
            st.error(f"Gagal membaca file Jadwal SPG {JADWAL_SPG_FILE}: {e}")
            return pd.DataFrame()
    return pd.DataFrame()


def get_scheduled_slots_for_date(target_date: date | None = None) -> list[dict]:
    df_j = load_jadwal_spg()
    if df_j is None or df_j.empty:
        return []

    kota_col = next((c for c in df_j.columns if "kota" in str(c).lower()), None)
    kec_col = next((c for c in df_j.columns if "kecamatan" in str(c).lower()), None)
    if not kota_col or not kec_col:
        return []

    ref_date = target_date or (datetime.utcnow() + timedelta(hours=7)).date()
    date_cols = []
    for c in df_j.columns:
        if c in {kota_col, kec_col}:
            continue
        try:
            parsed_dt = pd.to_datetime(c).date()
            date_cols.append((c, parsed_dt))
        except Exception:
            continue

    if target_date is not None:
        date_cols = [(c, dt) for c, dt in date_cols if dt == ref_date]

    slots = []
    seen = set()
    for _, row in df_j.iterrows():
        kota_val = normalize_text(row.get(kota_col, "")) or "Surabaya"
        kec_val = normalize_text(row.get(kec_col, ""))
        if not kec_val:
            continue
        for c_name, dt_val in date_cols:
            team_val = normalize_text(row.get(c_name, ""))
            if not team_val or team_val.lower() in {"nan", "none", "-"}:
                continue
            key = (dt_val.isoformat(), team_val.casefold(), kota_val.casefold(), kec_val.casefold())
            if key in seen:
                continue
            seen.add(key)
            slots.append({
                "tanggal": dt_val,
                "tanggal_str": dt_val.strftime("%d %b %Y"),
                "team": team_val,
                "kota": kota_val,
                "kecamatan": kec_val,
            })

    slots.sort(key=lambda item: (item["tanggal"], item["team"].casefold(), item["kota"].casefold(), item["kecamatan"].casefold()))
    return slots


def _is_same_team_reference(team_cell, team_name):
    team_cell = normalize_text(team_cell).lower()
    team_name = normalize_text(team_name).lower()
    if not team_cell or team_cell in {"nan", "none"}:
        return False
    return team_cell == team_name


def get_schedule_info_for_team(team_name):
    df_j = load_jadwal_spg()
    if df_j.empty:
        return False, "Tidak Ada Jadwal Team Tersebut Untuk Hari Ini", "Surabaya", [], pd.DataFrame()

    kota_col = next((c for c in df_j.columns if "kota" in str(c).lower()), None)
    kec_col = next((c for c in df_j.columns if "kecamatan" in str(c).lower()), None)
    if not kota_col or not kec_col:
        return False, "Tidak Ada Jadwal Team Tersebut Untuk Hari Ini", "Surabaya", [], pd.DataFrame()

    today_date = (datetime.utcnow() + timedelta(hours=7)).date()
    today_col = None
    for c in df_j.columns:
        try:
            if pd.to_datetime(c).date() == today_date:
                today_col = c
                break
        except Exception:
            continue

    if not today_col:
        return False, "Tidak Ada Jadwal Team Tersebut Untuk Hari Ini", "Surabaya", [], pd.DataFrame()

    matched_rows = []
    for _, row in df_j.iterrows():
        val_cell = normalize_text(row.get(today_col, ""))
        if not val_cell or val_cell.lower() in {"nan", "-"}:
            continue
        if _is_same_team_reference(val_cell, team_name):
            kota_val = normalize_text(row.get(kota_col, ""))
            kec_val = normalize_text(row.get(kec_col, ""))
            if kota_val or kec_val:
                matched_rows.append({"Kota": kota_val, "Kecamatan": kec_val})

    if not matched_rows:
        return False, "Tidak Ada Jadwal Team Tersebut Untuk Hari Ini", "Surabaya", [], pd.DataFrame()

    kec_list = sorted({r["Kecamatan"] for r in matched_rows if r["Kecamatan"]})
    kota_list = [r["Kota"] for r in matched_rows if r["Kota"]]
    found_kota = kota_list[0] if kota_list else "Surabaya"

    return True, "", found_kota, kec_list, pd.DataFrame(matched_rows)


# ====================================================
# TARGET BRAND
# ====================================================
def load_target_rules():
    data = _cached_read_json_no_mtime(MASTER_TARGET_FILE)
    return data if isinstance(data, dict) else dict(DEFAULT_TARGET_RULES)


def refresh_target_rules():
    global TARGET_RULES
    TARGET_RULES = load_target_rules()
    return TARGET_RULES


def save_target_rules(rules):
    global TARGET_RULES
    cleaned = rules if isinstance(rules, dict) else {}
    with open(MASTER_TARGET_FILE, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)
    st.cache_data.clear()
    TARGET_RULES = load_target_rules()


TARGET_RULES = load_target_rules()


def get_brand_target_rule(brand):
    brand_key = normalize_brand_key(brand)
    return next(
        (rule for rule_brand, rule in TARGET_RULES.items() if normalize_brand_key(rule_brand) == brand_key),
        {},
    )


def clean_brand_target_name(brand):
    group = get_brand_target_rule(brand).get("group")
    return TARGET_GROUP_LABELS.get(group, brand)


def get_group_target(group_name, target_key, default_val):
    for _, rule in TARGET_RULES.items():
        rule_group = rule.get("group")
        if rule_group == "Black_Siro_Kuro":
            rule_group = "Black_Matcha"
        if rule_group == group_name and target_key in rule:
            return rule[target_key]
    return default_val


def get_target_for_brand(brand, target_key, default_val):
    brand_str = str(brand or "").strip()
    if not brand_str:
        return default_val

    for group_key, label in TARGET_GROUP_LABELS.items():
        if brand_str.casefold() == label.casefold():
            canonical_group = "Black_Matcha" if group_key == "Black_Siro_Kuro" else group_key
            return get_group_target(canonical_group, target_key, default_val)

    rule = get_brand_target_rule(brand_str)
    group = rule.get("group")
    if group:
        canonical_group = "Black_Matcha" if group == "Black_Siro_Kuro" else group
        return get_group_target(canonical_group, target_key, default_val)
    return rule.get(target_key, default_val)


def style_status_target(val):
    if val == "Not Achieved":
        return "color: #DC2626; font-weight: 700;"
    if val == "Achieved":
        return "color: #16A34A; font-weight: 700;"
    return ""


# ====================================================
# KOMPONEN REKAP PENJUALAN 2 SPG & KONTROL STOK ROKOK
# ====================================================
def render_rekap_2spg_dan_stok(team_name: str, target_date_str: str, allow_edit_stok: bool = True):
    st.markdown(f"### 📦 Rekap Penjualan 2 SPG & Kontrol Stok Rokok ({team_name})")
    st.caption(
        "Breakdown penjualan per nama SPG hari ini, kontrol stok rokok yang dibawa, "
        "dan perhitungan otomatis sisa stok setelah dikurangi penjualan SPG."
    )

    df_all_db = load_database()
    harga_konsumen_map = load_harga_konsumen()
    stok_sup_map = load_stok_supervisi()

    df_team_spg_today = pd.DataFrame()
    if not df_all_db.empty and "Promotor" in df_all_db.columns:
        df_team_spg_today = df_all_db[
            (df_all_db["Promotor"].astype(str).str.strip().str.casefold() == str(team_name).strip().casefold())
            & (df_all_db["Waktu"].astype(str).str.startswith(str(target_date_str).strip()))
        ].copy()

    if not df_team_spg_today.empty:
        df_team_spg_today["Jumlah_Bungkus"] = pd.to_numeric(
            df_team_spg_today["Jumlah_Bungkus"], errors="coerce"
        ).fillna(0)
        df_team_spg_today["Harga_Konsumen"] = df_team_spg_today["Brand_Rokok"].apply(
            lambda b: get_harga_konsumen_brand(b, harga_konsumen_map)
        )
        df_team_spg_today["Total_Uang_Rp"] = (
            df_team_spg_today["Jumlah_Bungkus"] * df_team_spg_today["Harga_Konsumen"]
        ).astype(int)

    all_brands_sup = load_master_brands()
    team_brands_sup_map = load_master_team_brands()
    team_names_sup_map = load_master_team_names()
    allowed_brands_sup = resolve_team_allowed_brands(
        team_name=team_name,
        all_brands=all_brands_sup,
        team_brands_map=team_brands_sup_map,
        team_names_map=team_names_sup_map,
        prefer_keyword_match=True,
    )
    if not allowed_brands_sup:
        allowed_brands_sup = all_brands_sup

    sold_brands_today = (
        df_team_spg_today["Brand_Rokok"].dropna().astype(str).str.strip().unique().tolist()
        if not df_team_spg_today.empty
        else []
    )
    brand_list_sup_stok = list(
        dict.fromkeys([b for b in allowed_brands_sup if b] + [b for b in sold_brands_today if b])
    )

    try:
        parsed_target_date = datetime.strptime(str(target_date_str).strip(), "%Y-%m-%d").date()
    except ValueError:
        parsed_target_date = (datetime.utcnow() + timedelta(hours=7)).date()

    sched_spg_today = get_scheduled_personnel_for_team(
        team_name,
        parsed_target_date,
        selected_kecamatan="",
    ).get("spg_all", [])
    tx_spg_today = (
        df_team_spg_today["Nama_SPG"].dropna().astype(str).str.strip().unique().tolist()
        if not df_team_spg_today.empty
        else []
    )
    spg_2_list = list(dict.fromkeys([s for s in sched_spg_today if s] + [s for s in tx_spg_today if s]))
    if not spg_2_list:
        spg_2_list = ["SPG 1", "SPG 2"]

    total_bks_2spg_today = int(df_team_spg_today["Jumlah_Bungkus"].sum()) if not df_team_spg_today.empty else 0
    total_uang_2spg_today = int(df_team_spg_today["Total_Uang_Rp"].sum()) if not df_team_spg_today.empty else 0

    st.info(
        f"💵 **Jumlah Uang Terkumpul ({target_date_str}) — Penjualan 2 SPG:** "
        f"**Rp {total_uang_2spg_today:,}** ({total_bks_2spg_today:,} bungkus)"
    )

    if allow_edit_stok:
        with st.form(f"form_input_stok_rekap_{team_name}_{target_date_str}"):
            st.markdown("#### 📥 Input / Update Stok Rokok Dibawa (Per Merk)")
            st.caption(f"Tanggal: **{target_date_str}** • Team: **{team_name}**")
            stok_input_dict = {}
            if not brand_list_sup_stok:
                st.info("Belum ada daftar merk rokok untuk tim ini.")
            else:
                for idx_b, b_name in enumerate(brand_list_sup_stok):
                    existing_stok = get_stok_awal_supervisi(target_date_str, team_name, b_name, stok_sup_map)
                    col_sb1, col_sb2 = st.columns([0.6, 0.4])
                    with col_sb1:
                        st.markdown(f"**🚬 {b_name}**")
                        st.caption(f"Harga konsumen: Rp {get_harga_konsumen_brand(b_name, harga_konsumen_map):,} / bks")
                    with col_sb2:
                        stok_input_dict[b_name] = st.number_input(
                            f"Stok dibawa {b_name}",
                            min_value=0,
                            step=1,
                            value=int(existing_stok),
                            label_visibility="collapsed",
                            key=f"inp_stok_rekap_{team_name}_{target_date_str}_{idx_b}_{b_name}",
                        )
            btn_save_stok_rekap = st.form_submit_button("💾 Simpan Stok Dibawa", type="primary", use_container_width=True)
            if btn_save_stok_rekap:
                for b_name, qty_val in stok_input_dict.items():
                    k_stok = _stok_sup_key(target_date_str, team_name, b_name)
                    stok_sup_map[k_stok] = int(qty_val)
                if save_stok_supervisi(stok_sup_map):
                    st.success("✅ Jumlah stok rokok yang dibawa berhasil disimpan!")
                    st.rerun()

    st.markdown("#### 👩‍💼 Breakdown Penjualan Per Nama SPG Hari Ini")
    spg_cols = st.columns(min(2, len(spg_2_list)) if spg_2_list else 1)
    for idx_s, spg_nm in enumerate(spg_2_list[:2]):
        df_s = (
            df_team_spg_today[
                df_team_spg_today["Nama_SPG"].astype(str).str.strip().str.casefold() == spg_nm.strip().casefold()
            ]
            if not df_team_spg_today.empty
            else pd.DataFrame()
        )
        bks_s = int(df_s["Jumlah_Bungkus"].sum()) if not df_s.empty else 0
        uang_s = int(df_s["Total_Uang_Rp"].sum()) if not df_s.empty else 0
        trx_s = int(len(df_s)) if not df_s.empty else 0
        with spg_cols[idx_s % len(spg_cols)]:
            st.markdown(
                f"""
                <div class="dashboard-card">
                    <div>
                        <div style="font-size:0.85rem;font-weight:700;color:#334155;">👩‍💼 {spg_nm}</div>
                        <div class="card-value" style="margin-top:6px;">{bks_s:,} bks</div>
                        <div class="card-subtext">Rp {uang_s:,} • {trx_s} transaksi</div>
                    </div>
                    <div class="card-label">Penjualan SPG #{idx_s + 1}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    if not df_team_spg_today.empty:
        df_breakdown_spg_merk = (
            df_team_spg_today.groupby(["Nama_SPG", "Brand_Rokok"])
            .agg(
                Transaksi=("Nama_Konsumen", "count"),
                Terjual_Bungkus=("Jumlah_Bungkus", "sum"),
                Total_Uang_Rp=("Total_Uang_Rp", "sum"),
            )
            .reset_index()
        )
        df_breakdown_spg_merk["Terjual_Bungkus"] = df_breakdown_spg_merk["Terjual_Bungkus"].astype(int)
        df_breakdown_spg_merk["Total_Uang_Rp"] = df_breakdown_spg_merk["Total_Uang_Rp"].astype(int)
        st.dataframe(df_breakdown_spg_merk, use_container_width=True, hide_index=True)
    else:
        st.info("Belum ada penjualan SPG tercatat pada tanggal ini.")

    st.markdown("#### 📊 Rekap Stok Dibawa, Terjual 2 SPG & Sisa Stok Per Merk")
    rows_stok_rekap = []
    for b_name in brand_list_sup_stok:
        stok_dibawa = get_stok_awal_supervisi(target_date_str, team_name, b_name, stok_sup_map)
        df_b = (
            df_team_spg_today[
                df_team_spg_today["Brand_Rokok"].astype(str).str.strip().str.casefold() == b_name.strip().casefold()
            ]
            if not df_team_spg_today.empty
            else pd.DataFrame()
        )
        terjual_spg_b = int(df_b["Jumlah_Bungkus"].sum()) if not df_b.empty else 0
        sisa_stok_b = stok_dibawa - terjual_spg_b
        uang_b = int(df_b["Total_Uang_Rp"].sum()) if not df_b.empty else 0

        r_detail = {"Merk_Rokok": b_name, "Stok_Dibawa": stok_dibawa}
        for spg_nm in spg_2_list[:2]:
            col_key = f"Terjual_{spg_nm}"
            if not df_b.empty:
                val_spg_b = int(
                    df_b[df_b["Nama_SPG"].astype(str).str.strip().str.casefold() == spg_nm.strip().casefold()][
                        "Jumlah_Bungkus"
                    ].sum()
                )
            else:
                val_spg_b = 0
            r_detail[col_key] = val_spg_b

        r_detail["Total_Terjual_SPG"] = terjual_spg_b
        r_detail["Sisa_Stok"] = sisa_stok_b
        r_detail["Uang_Merk_Rp"] = uang_b
        rows_stok_rekap.append(r_detail)

    if rows_stok_rekap:
        df_stok_rekap = pd.DataFrame(rows_stok_rekap)
        st.dataframe(df_stok_rekap, use_container_width=True, hide_index=True)

        total_stok_dibawa_all = int(df_stok_rekap["Stok_Dibawa"].sum())
        total_terjual_all = int(df_stok_rekap["Total_Terjual_SPG"].sum())
        total_sisa_stok_all = int(df_stok_rekap["Sisa_Stok"].sum())
        st.info(
            f"📦 **Ringkasan Stok ({target_date_str}):** Stok Dibawa: **{total_stok_dibawa_all:,} bks** • "
            f"Terjual 2 SPG: **{total_terjual_all:,} bks** • "
            f"**Sisa Stok: {total_sisa_stok_all:,} bks**"
        )
    else:
        st.info("Belum ada data stok atau merk untuk direkap.")


# ====================================================
# SESSION STATE
# ====================================================
def reset_session_on_user_change():
    st.session_state["logged_in"] = False
    st.session_state["user_spg"] = st.session_state.get("selected_team_login", "")
    st.session_state["nama_supervisi_aktif"] = ""
    st.session_state["spg_terjadwal_list"] = []
    st.session_state["sektor_terjadwal_login"] = ""
    st.session_state["draft_konsumen"] = ""
    st.session_state["draft_nohp"] = ""
    st.session_state["draft_ig"] = ""
    st.session_state["draft_bungkus"] = 1
    st.session_state["draft_bumo"] = ""
    st.session_state["draft_brand"] = ""
    st.session_state["draft_gender"] = "L"
    st.session_state["draft_range_umur"] = "18-24"
    st.session_state["spg_form_nonce"] = st.session_state.get("spg_form_nonce", 0) + 1
    st.session_state["sup_kontak_nonce"] = st.session_state.get("sup_kontak_nonce", 0) + 1


for _k, _default in [
    ("logged_in", False),
    ("user_spg", ""),
    ("plat_mobil", ""),
    ("kota_kab", ""),
    ("nama_supervisi_aktif", ""),
    ("spg_terjadwal_list", []),
    ("sektor_terjadwal_login", ""),
    ("login_mode", "SPG"),
    ("admin_logged_in", False),
    ("admin_view", "Dashboard"),
    ("draft_konsumen", ""),
    ("draft_nohp", ""),
    ("draft_ig", ""),
    ("draft_bungkus", 1),
    ("draft_bumo", ""),
    ("draft_brand", ""),
    ("draft_gender", "L"),
    ("draft_range_umur", "18-24"),
    ("spg_form_nonce", 0),
    ("sup_kontak_nonce", 0),
]:
    if _k not in st.session_state:
        st.session_state[_k] = _default

# ====================================================
# AKSES TERPISAH HALAMAN ADMIN VIA QUERY PARAM (?page=admin)
# ====================================================
_qp_page = str(st.query_params.get("page", "")).strip().lower()
_admin_portal_requested = (_qp_page == "admin")

if not _admin_portal_requested and st.session_state.get("admin_logged_in"):
    st.session_state["admin_logged_in"] = False

if _admin_portal_requested and not st.session_state["logged_in"]:
    with st.sidebar:
        st.markdown("### 🔐 Panel Admin & Supervisor")
        st.caption("Pusat kontrol data lapangan dan konfigurasi master.")

        if not st.session_state["admin_logged_in"]:
            with st.form("form_admin_login"):
                pass_input = st.text_input("Kata Sandi Admin", type="password", placeholder="••••••••")
                btn_pass = st.form_submit_button("Masuk Dashboard Admin", use_container_width=True)
                if btn_pass:
                    if pass_input == "admin123":
                        st.session_state["admin_logged_in"] = True
                        st.session_state["admin_view"] = "Dashboard"
                        st.success("✅ Berhasil masuk sebagai Admin!")
                        st.rerun()
                    else:
                        st.error("❌ Password salah!")
        else:
            st.success("🟢 Mode Admin Aktif")
            st.markdown("##### 📊 Monitoring & Laporan")
            for label, view_key in [
                ("🏠 Dashboard Utama", "Dashboard"),
                ("📅 Entry & Jadwal SPG", "Master_Jadwal_Excel"),
                ("📈 Analitik Lapangan", "Analitik"),
                ("🗺️ Peta Rute & Poligon", "Peta_Rute"),
            ]:
                if st.button(
                    label,
                    use_container_width=True,
                    type="primary" if st.session_state["admin_view"] == view_key else "secondary",
                ):
                    st.session_state["admin_view"] = view_key
                    st.rerun()

            st.markdown("##### ⚙️ Master Data")
            for label, view_key in [
                ("🏷️ Master Nama Team", "Master_Nama_Team"),
                ("👥 Team & Alokasi Brand", "Master_Team"),
                ("👩‍💼 Master Nama SPG", "Master_SPG"),
                ("🚬 Merek Rokok & Target", "Master_Brand"),
                ("💰 Harga Rokok Konsumen", "Master_Harga"),
                ("🚗 Plat Kendaraan", "Master_Plat"),
                ("📍 Lokasi Warkop (Excel)", "Master_Lokasi"),
            ]:
                if st.button(label, use_container_width=True):
                    st.session_state["admin_view"] = view_key
                    st.rerun()

            st.markdown("---")
            if st.button("🔒 Keluar Mode Admin", use_container_width=True):
                st.session_state["admin_logged_in"] = False
                st.query_params.clear()
                st.rerun()

if _admin_portal_requested and not st.session_state["logged_in"] and st.session_state["admin_logged_in"]:
    if st.session_state["admin_view"] == "Master_Nama_Team":
        st.markdown("## 🏷️ Master Data: Nama Team (1 - 20)")
        team_names_map = load_master_team_names()
        with st.form("form_edit_nama_team"):
            updated_names = {
                f"Team SPG {i}": st.text_input(
                    f"Nama untuk `Team SPG {i}`",
                    value=team_names_map.get(f"Team SPG {i}", f"Team SPG {i}"),
                    key=f"input_team_name_{i}",
                ).strip()
                for i in range(1, 21)
            }
            if st.form_submit_button("💾 Simpan Perubahan Nama Team", type="primary"):
                if save_master_team_names(updated_names):
                    st.success("✅ Perubahan nama team berhasil disimpan!")
                    st.rerun()
        if st.button("⬅️ Kembali ke Dashboard"):
            st.session_state["admin_view"] = "Dashboard"
            st.rerun()
        st.stop()

    elif st.session_state["admin_view"] == "Master_Plat":
        st.markdown("## 🚗 Master Data: Plat Nomor Kendaraan Operasional")
        plat_list = load_master_plat_kendaraan()
        with st.form("form_tambah_plat"):
            new_plat_input = st.text_input("Plat Nomor Kendaraan", placeholder="Contoh: L 1234 ABC")
            if st.form_submit_button("➕ Tambah Plat Kendaraan"):
                p_clean = new_plat_input.strip().upper()
                if p_clean and p_clean not in plat_list:
                    plat_list.append(p_clean)
                    save_master_plat_kendaraan(plat_list)
                    st.rerun()
        for idx, p in enumerate(plat_list):
            c1, c2 = st.columns([0.8, 0.2])
            with c1:
                st.write(f"**{idx+1}.** `{p}`")
            with c2:
                if st.button("🗑️ Hapus", key=f"del_plat_{idx}"):
                    plat_list.pop(idx)
                    save_master_plat_kendaraan(plat_list)
                    st.rerun()
        if st.button("⬅️ Kembali ke Dashboard"):
            st.session_state["admin_view"] = "Dashboard"
            st.rerun()
        st.stop()

    elif st.session_state["admin_view"] == "Master_Team":
        st.markdown("## 👥 Master Data: Team 1 - 20 & Alokasi Brand Rokok")
        all_available_brands = load_master_brands()
        team_brands_dict = load_master_team_brands()
        team_name_mapping = load_master_team_names()
        active_team_slots = [
            (f"Team SPG {i}", team_name_mapping[f"Team SPG {i}"])
            for i in range(1, 21)
            if team_name_mapping[f"Team SPG {i}"]
        ]
        team_options = [team_name for _, team_name in active_team_slots]
        selected_team_config = st.selectbox("Pilih Team SPG untuk Konfigurasi Brand", options=team_options)
        current_assigned = [b for b in team_brands_dict.get(selected_team_config, []) if b in all_available_brands]
        with st.form(key=f"form_config_{selected_team_config}"):
            selected_brands_input = st.multiselect("Pilih Brand Rokok yang Diizinkan", options=all_available_brands, default=current_assigned)
            if st.form_submit_button("💾 Simpan Alokasi Brand Team"):
                team_brands_dict[selected_team_config] = selected_brands_input
                if save_master_team_brands(team_brands_dict):
                    st.success("✅ Alokasi brand berhasil disimpan!")
                    st.rerun()
        if st.button("⬅️ Kembali ke Dashboard", key="btn_back_master_team"):
            st.session_state["admin_view"] = "Dashboard"
            st.rerun()
        st.stop()

    elif st.session_state["admin_view"] == "Master_SPG":
        st.markdown("## 👩‍💼 Master Data: Nama SPG")
        current_spgs = load_master_spgs()
        with st.form("form_tambah_spg"):
            new_spg_name = st.text_input("Nama SPG Baru", placeholder="Contoh: Siska")
            if st.form_submit_button("➕ Tambah Nama SPG"):
                spg_clean = new_spg_name.strip()
                if spg_clean and spg_clean not in current_spgs:
                    current_spgs.append(spg_clean)
                    save_master_spgs(current_spgs)
                    st.rerun()
        for idx, s in enumerate(current_spgs):
            c1, c2 = st.columns([0.8, 0.2])
            with c1:
                st.write(f"**{idx+1}.** {s}")
            with c2:
                if st.button("🗑️ Hapus", key=f"del_spg_{idx}"):
                    current_spgs.pop(idx)
                    save_master_spgs(current_spgs)
                    st.rerun()
        if st.button("⬅️ Kembali ke Dashboard"):
            st.session_state["admin_view"] = "Dashboard"
            st.rerun()
        st.stop()

    elif st.session_state["admin_view"] == "Master_Brand":
        st.markdown("## 🚬 Master Data: Merek Rokok & Target")
        current_brands = load_master_brands()
        target_rules_data = load_target_rules()
        with st.form("form_tambah_brand"):
            new_brand_name = st.text_input("Nama Merek Rokok Baru")
            t_spg = st.number_input("Target per SPG (Bungkus)", min_value=1, value=30, step=1)
            t_team = st.number_input("Target per Team (Bungkus)", min_value=1, value=60, step=1)
            new_group = st.selectbox("Grup target gabungan", options=list(TARGET_GROUP_OPTIONS), format_func=lambda g: TARGET_GROUP_OPTIONS[g])
            if st.form_submit_button("➕ Tambah Merek Rokok"):
                b_clean = new_brand_name.strip()
                if b_clean and b_clean not in current_brands:
                    current_brands.append(b_clean)
                    save_master_brands(current_brands)
                    target_rules_data[b_clean] = {"target_spg": int(t_spg), "target_team": int(t_team)}
                    if new_group:
                        target_rules_data[b_clean]["group"] = new_group
                    save_target_rules(target_rules_data)
                    refresh_target_rules()
                    st.rerun()
        if st.button("⬅️ Kembali ke Dashboard"):
            st.session_state["admin_view"] = "Dashboard"
            st.rerun()
        st.stop()

    elif st.session_state["admin_view"] == "Master_Harga":
        st.markdown("## 💰 Master Data: Harga Rokok Konsumen")
        current_brands = load_master_brands()
        harga_map = load_harga_konsumen()
        all_merk_list = list(dict.fromkeys([str(b).strip() for b in current_brands if str(b).strip()] + [str(k).strip() for k in harga_map if str(k).strip()]))
        with st.form("form_edit_harga_konsumen"):
            edited_harga_dict = {}
            for idx, merk_item in enumerate(all_merk_list):
                edited_harga_dict[merk_item] = st.number_input(
                    f"{merk_item} (Rp / bks)",
                    min_value=0,
                    value=int(get_harga_konsumen_brand(merk_item, harga_map)),
                    step=500,
                    key=f"inp_harga_konsumen_{idx}_{merk_item}",
                )
            if st.form_submit_button("💾 Simpan Perubahan Harga Konsumen", type="primary", use_container_width=True):
                if save_harga_konsumen(edited_harga_dict):
                    st.success("✅ Harga rokok konsumen berhasil disimpan!")
                    st.rerun()
        if st.button("⬅️ Kembali ke Dashboard"):
            st.session_state["admin_view"] = "Dashboard"
            st.rerun()
        st.stop()

    elif st.session_state["admin_view"] == "Master_Lokasi":
        st.markdown("## 📍 Master Lokasi Warkop / LKK")
        df_lokasi_excel = load_master_lokasi_excel()
        st.dataframe(df_lokasi_excel, use_container_width=True, hide_index=True)
        if st.button("⬅️ Kembali ke Dashboard", key="btn_back_master_lokasi"):
            st.session_state["admin_view"] = "Dashboard"
            st.rerun()
        st.stop()

    elif st.session_state["admin_view"] == "Master_Jadwal_Excel":
        st.markdown("## 📅 Entry & Monitoring Jadwal SPG")
        render_schedule_entry()
        st.stop()

    elif st.session_state["admin_view"] == "Analitik":
        st.markdown("## 📊 Analitik Lapangan")
        df_all_users = load_database()
        if not df_all_users.empty:
            df_all_users["Jumlah_Bungkus"] = pd.to_numeric(df_all_users["Jumlah_Bungkus"], errors="coerce").fillna(0)
            st.bar_chart(df_all_users.groupby("Brand_Rokok")["Jumlah_Bungkus"].sum())
        if st.button("⬅️ Kembali ke Dashboard"):
            st.session_state["admin_view"] = "Dashboard"
            st.rerun()
        st.stop()

    elif st.session_state["admin_view"] == "Peta_Rute":
        st.markdown("## 🗺️ Peta Rute")
        if st.button("⬅️ Kembali ke Dashboard"):
            st.session_state["admin_view"] = "Dashboard"
            st.rerun()
        st.stop()

    st.markdown("## 📊 Dashboard Admin & Manajemen Lapangan")
    render_google_sheet_backup_controls()
    st.stop()

# ====================================================
# PORTAL LOGIN KHUSUS ADMIN (?page=admin)
# ====================================================
if _admin_portal_requested and not st.session_state["logged_in"] and not st.session_state["admin_logged_in"]:
    st.markdown(
        """
        <div class="login-header">
            <div style="font-size: 2.2rem; margin-bottom: 4px;">🔐</div>
            <h1>PORTAL ADMIN &amp; SUPERVISOR</h1>
            <p>Akses Khusus Pengelola Data Master &amp; Monitoring</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.container(border=True):
        with st.form("form_admin_portal_login"):
            admin_pass_main = st.text_input("Kata Sandi Admin", type="password", placeholder="Masukkan kata sandi admin")
            if st.form_submit_button("🔓 Masuk Halaman Admin", type="primary", use_container_width=True):
                if admin_pass_main == "admin123":
                    st.session_state["admin_logged_in"] = True
                    st.session_state["admin_view"] = "Dashboard"
                    st.rerun()
                else:
                    st.error("❌ Kata sandi admin salah!")
    st.stop()

# ====================================================
# HALAMAN AWAL / LOGIN (3 MENU: SPG, SUPERVISI, REKAPITULASI PENJUALAN)
# ====================================================
if not st.session_state["logged_in"]:
    st.markdown(
        """
        <div class="login-header">
            <div style="font-size: 2.2rem; margin-bottom: 4px;">📍</div>
            <h1>PORTAL LAPORAN &amp; MONITORING</h1>
            <p>Sistem Pelaporan Lapangan SPG, Supervisi &amp; Rekapitulasi</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="section-title">1️⃣ Pilih Menu Utama</div>', unsafe_allow_html=True)
    col_btn_mode1, col_btn_mode2, col_btn_mode3 = st.columns(3)
    with col_btn_mode1:
        if st.button(
            "📝 Masuk sebagai SPG",
            use_container_width=True,
            type="primary" if st.session_state["login_mode"] == "SPG" else "secondary",
        ):
            st.session_state["login_mode"] = "SPG"
            st.rerun()

    with col_btn_mode2:
        if st.button(
            "👀 Masuk sebagai Supervisi",
            use_container_width=True,
            type="primary" if st.session_state["login_mode"] == "Supervisi" else "secondary",
        ):
            st.session_state["login_mode"] = "Supervisi"
            st.rerun()

    with col_btn_mode3:
        if st.button(
            "📊 Rekapitulasi Penjualan",
            use_container_width=True,
            type="primary" if st.session_state["login_mode"] == "Rekapitulasi" else "secondary",
        ):
            st.session_state["login_mode"] = "Rekapitulasi"
            st.rerun()

    team_name_mapping = load_master_team_names()
    list_team = [
        team_name_mapping[f"Team SPG {i}"]
        for i in range(1, 21)
        if team_name_mapping[f"Team SPG {i}"]
    ]

    # --- MENU KE-3: REKAPITULASI PENJUALAN (2 SPG & KONTROL STOK ROKOK) ---
    if st.session_state["login_mode"] == "Rekapitulasi":
        st.markdown('<div class="section-title">2️⃣ Pilih Team &amp; Tanggal Rekapitulasi</div>', unsafe_allow_html=True)
        with st.container(border=True):
            today_wib_rek = (datetime.utcnow() + timedelta(hours=7)).date()
            c_rek1, c_rek2 = st.columns([0.65, 0.35])
            with c_rek1:
                team_rekap_pilih = st.selectbox(
                    "👤 Nama Team Operasional",
                    options=list_team,
                    key="rekap_page_team_select",
                )
            with c_rek2:
                tgl_rekap_pilih = st.date_input(
                    "📅 Tanggal Rekap",
                    value=today_wib_rek,
                    key="rekap_page_date_select",
                )

        apply_team_theme_css(team_rekap_pilih)
        st.markdown("---")
        render_rekap_2spg_dan_stok(
            team_name=team_rekap_pilih,
            target_date_str=tgl_rekap_pilih.strftime("%Y-%m-%d"),
            allow_edit_stok=True,
        )

        st.markdown(
            """
            <div class="footer-note">
                © 2026 Tumarso Monitoring System
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.stop()

    # --- MENU 1 & 2: LOGIN SPG / SUPERVISI ---
    st.markdown('<div class="section-title">2️⃣ Pilih Tim &amp; Verifikasi Jadwal</div>', unsafe_allow_html=True)
    with st.container(border=True):
        pilihan_user = st.selectbox(
            "👤 Nama Team Operasional",
            list_team,
            key="selected_team_login",
            on_change=reset_session_on_user_change,
        )

        schedule_ok, _, auto_detected_kota, auto_kecamatan_list, matched_schedule_rows = get_schedule_info_for_team(pilihan_user)
        today_wib = (datetime.utcnow() + timedelta(hours=7)).date()

        selected_sektor_login = ""
        if schedule_ok and len(auto_kecamatan_list) > 1:
            selected_sektor_login = st.selectbox(
                "📍 Pilih Sektor / Kecamatan Terjadwal Hari Ini",
                options=auto_kecamatan_list,
                key="login_select_sektor_team",
            )
        elif schedule_ok and len(auto_kecamatan_list) == 1:
            selected_sektor_login = auto_kecamatan_list[0]

        personnel_info = (
            get_scheduled_personnel_for_team(pilihan_user, today_wib, selected_kecamatan=selected_sektor_login)
            if schedule_ok
            else {"found": False, "supervisi": [], "spg_1": [], "spg_2": [], "spg_all": [], "vehicles": [], "records": []}
        )

        if schedule_ok and personnel_info.get("records"):
            auto_detected_kota = personnel_info["records"][0].get("kota") or auto_detected_kota

        scheduled_vehicles = personnel_info.get("vehicles", []) if personnel_info.get("found") else []
        if schedule_ok and not scheduled_vehicles:
            scheduled_vehicles = get_scheduled_vehicles(matched_schedule_rows, today_wib)

        spv_names = personnel_info.get("supervisi", [])
        spg_all_names = personnel_info.get("spg_all", [])

        if not schedule_ok:
            st.error("⚠️ **Tidak Ada Jadwal Team Tersebut Untuk Hari Ini**")
        else:
            spv_label = ", ".join(spv_names) if spv_names else "Belum diatur di jadwal"
            sektor_tampil = selected_sektor_login or (", ".join(auto_kecamatan_list) if auto_kecamatan_list else "-")
            st.success(
                f"✅ **Jadwal Aktif Ditemukan**\n\n"
                f"- **Wilayah / Sektor:** {auto_detected_kota} — **{sektor_tampil}**\n"
                f"- **Supervisi:** **{spv_label}**\n"
                f"- **SPG Terjadwal:** **{', '.join(spg_all_names) if spg_all_names else '-'}**"
            )
            if st.session_state["login_mode"] == "Supervisi":
                if len(scheduled_vehicles) == 1:
                    st.info(f"🚗 Plat Kendaraan Terjadwal: **{scheduled_vehicles[0]}**")
                elif not scheduled_vehicles:
                    st.warning("Plat kendaraan belum diatur pada jadwal team hari ini.")
                else:
                    st.error(f"Terdapat lebih dari satu plat kendaraan ({', '.join(scheduled_vehicles)}). Samakan plat pada jadwal.")

        st.markdown("")
        if st.button(f"🚀 Lanjut Masuk ({st.session_state['login_mode']})", type="primary", use_container_width=True):
            if not schedule_ok:
                st.error("❌ Akses ditolak: Tidak Ada Jadwal Team Tersebut Untuk Hari Ini.")
            elif st.session_state["login_mode"] == "Supervisi" and len(scheduled_vehicles) != 1:
                st.error("❌ Akses Supervisi ditolak: plat kendaraan pada jadwal belum tersedia atau tidak konsisten.")
            else:
                st.session_state["logged_in"] = True
                st.session_state["user_spg"] = pilihan_user
                st.session_state["plat_mobil"] = scheduled_vehicles[0] if len(scheduled_vehicles) == 1 else "-"
                st.session_state["kota_kab"] = auto_detected_kota
                st.session_state["nama_supervisi_aktif"] = spv_names[0] if spv_names else ""
                st.session_state["spg_terjadwal_list"] = spg_all_names
                st.session_state["sektor_terjadwal_login"] = selected_sektor_login
                st.rerun()

    st.markdown(
        """
        <div class="footer-note">
            © 2026 Tumarso Monitoring System
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()

# ====================================================
# APLIKASI UTAMA SETELAH LOGIN (SPG & SUPERVISI)
# ====================================================
apply_team_theme_css(st.session_state["user_spg"])

col_banner, col_logout = st.columns([0.8, 0.2])
with col_banner:
    mode_badge = "👀 Supervisi" if st.session_state["login_mode"] == "Supervisi" else "📝 SPG"
    spv_aktif = st.session_state.get("nama_supervisi_aktif", "").strip()
    spg_list_aktif = st.session_state.get("spg_terjadwal_list", [])
    personel_badge = (
        f" &nbsp;•&nbsp; 🧑‍💼 SPV: <b>{spv_aktif or '-'}</b>"
        if st.session_state["login_mode"] == "Supervisi"
        else f" &nbsp;•&nbsp; 👩‍💼 SPG: <b>{', '.join(spg_list_aktif) if spg_list_aktif else '-'}</b>"
    )
    st.markdown(
        f"""
        <div class="user-banner">
            <div class="user-banner-title">
                <span>👤 {st.session_state['user_spg']}</span>
                <span class="badge-mode">{mode_badge}</span>
            </div>
            <div class="user-banner-sub">
                🚗 Plat: <b>{st.session_state['plat_mobil']}</b> &nbsp;•&nbsp; 🏙️ Wilayah: <b>{st.session_state['kota_kab']}</b>{personel_badge}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with col_logout:
    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
    if st.button("🚪 Keluar", use_container_width=True):
        st.session_state["logged_in"] = False
        st.rerun()

daftar_kecamatan = get_geo_districts(st.session_state["kota_kab"]) or ["Kecamatan Default"]

loc = get_geolocation()
if loc is None or not isinstance(loc, dict) or "coords" not in loc:
    user_lat = -7.2575
    user_lon = 112.7521
    akurasi_meter = 0.0
else:
    user_lat = float(loc["coords"]["latitude"])
    user_lon = float(loc["coords"]["longitude"])
    akurasi_meter = round(float(loc["coords"].get("accuracy", 0)), 1)

st.success(f"📍 **GPS Aktif:** `{user_lat:.6f}`, `{user_lon:.6f}` (±{akurasi_meter}m) — **{st.session_state['kota_kab']}**")

schedule_ok, _, _, daftar_kecamatan_terjadwal, _ = get_schedule_info_for_team(st.session_state["user_spg"])
if not schedule_ok:
    daftar_kecamatan_terjadwal = daftar_kecamatan
else:
    daftar_kecamatan_terjadwal = sorted(set(daftar_kecamatan_terjadwal))

# ====================================================
# TITIK KUNJUNGAN LAPANGAN (LOCK TITIK LKK OLEH SUPERVISI)
# ====================================================
st.markdown('<div class="section-title">📍 Titik Kunjungan Lapangan</div>', unsafe_allow_html=True)
with st.container(border=True):
    df_sup_today_all = load_supervisi_database()
    locked_point_today = get_active_locked_lkk_point_today(
        team_name=st.session_state["user_spg"],
        fallback_kota=st.session_state.get("kota_kab", ""),
    )
    latest_sup_contact = get_latest_supervisi_point_today(
        team_name=st.session_state["user_spg"],
        fallback_kota=st.session_state.get("kota_kab", ""),
        df_sup=df_sup_today_all,
    )

    df_master_excel = load_master_lokasi_excel()
    col_kec_excel = next((c for c in df_master_excel.columns if "kec" in c.lower() or "wilayah" in c.lower()), None) if not df_master_excel.empty else None
    col_warkop_excel = next((c for c in df_master_excel.columns if "warkop" in c.lower() or "lkk" in c.lower() or "nama" in c.lower()), None) if not df_master_excel.empty else None
    col_alamat_excel = next((c for c in df_master_excel.columns if "alamat" in c.lower() or "address" in c.lower()), None) if not df_master_excel.empty else None

    if st.session_state["login_mode"] == "Supervisi":
        col_sync_1, col_sync_2 = st.columns([0.78, 0.22])
        status_map_sup = load_warkop_visit_status_map()
        with col_sync_1:
            if locked_point_today:
                st_lock = locked_point_today.get("status_kunjungan", VISIT_STATUS_WAJIB)
                st.success(
                    f"🔒 **Titik LKK Terkunci Hari Ini:** **{locked_point_today['warkop']}** "
                    f"({locked_point_today['kecamatan']}) • **{st_lock}** • SPG sudah diizinkan menginput di titik ini."
                )
            else:
                st.warning("⚠️ **Titik LKK Belum Di-Save / Di-Lock.** Pilih Kecamatan & Warkop/LKK lalu klik **🔒 Save Titik LKK**.")
        with col_sync_2:
            st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)
            if st.button("🔄 Refresh", key="btn_refresh_sup_points", use_container_width=True):
                st.rerun()

        default_kec_idx = 0
        if locked_point_today and locked_point_today.get("kecamatan") in daftar_kecamatan_terjadwal:
            default_kec_idx = daftar_kecamatan_terjadwal.index(locked_point_today["kecamatan"])

        kecamatan_pilihan = st.selectbox(
            f"Kecamatan Tujuan ({st.session_state['kota_kab']})",
            options=daftar_kecamatan_terjadwal,
            index=default_kec_idx,
        )

        filtered_warkop_list = []
        if not df_master_excel.empty and col_kec_excel and col_warkop_excel:
            mask = df_master_excel[col_kec_excel].astype(str).str.strip().str.lower() == str(kecamatan_pilihan).strip().lower()
            filtered_df_warkop = df_master_excel[mask]
            if filtered_df_warkop.empty:
                filtered_df_warkop = df_master_excel.copy()
            seen_w = set()
            for w_item in filtered_df_warkop[col_warkop_excel].dropna().astype(str).str.strip().tolist():
                if w_item and w_item.casefold() not in seen_w:
                    seen_w.add(w_item.casefold())
                    filtered_warkop_list.append(w_item)

        if not filtered_warkop_list:
            filtered_warkop_list = ["Warkop Alternatif 1", "Warkop Alternatif 2"]

        default_w_idx = 0
        if locked_point_today and locked_point_today.get("warkop") in filtered_warkop_list:
            default_w_idx = filtered_warkop_list.index(locked_point_today["warkop"])

        nama_warkop_manual = st.selectbox(
            f"Warkop / LKK di {kecamatan_pilihan}",
            options=filtered_warkop_list,
            index=default_w_idx,
        )
        status_warkop_terpilih = get_warkop_visit_status(st.session_state["kota_kab"], kecamatan_pilihan, nama_warkop_manual, status_map_sup)
        alamat_warkop_terpilih = "-"
        if not df_master_excel.empty and col_warkop_excel and col_alamat_excel:
            match_row = df_master_excel[df_master_excel[col_warkop_excel].astype(str).str.strip() == str(nama_warkop_manual).strip()]
            if not match_row.empty:
                alamat_warkop_terpilih = str(match_row.iloc[0][col_alamat_excel])

        if st.button("🔒 Save Titik LKK (Buka Akses Input SPG)", type="primary", use_container_width=True, key="btn_save_lock_lkk"):
            if save_locked_lkk_point(
                team_name=st.session_state["user_spg"],
                point_info={
                    "kota": st.session_state["kota_kab"],
                    "kecamatan": str(kecamatan_pilihan).strip(),
                    "warkop": str(nama_warkop_manual).strip(),
                    "alamat": alamat_warkop_terpilih,
                    "status_kunjungan": status_warkop_terpilih,
                },
            ):
                st.success(f"✅ Titik LKK **{str(nama_warkop_manual).strip()}** berhasil di-save & di-lock!")
                st.rerun()
    else:
        col_spg_s1, col_spg_s2 = st.columns([0.78, 0.22])
        with col_spg_s1:
            if locked_point_today:
                st_lock_spg = locked_point_today.get("status_kunjungan", VISIT_STATUS_WAJIB)
                kontak_info = (
                    f" • Kontak Tim Tersimpan: **{latest_sup_contact['kontak']}**"
                    if latest_sup_contact and latest_sup_contact.get("warkop", "").casefold() == locked_point_today["warkop"].casefold()
                    else ""
                )
                st.success(
                    f"🔒 **Titik LKK Terkunci (Dari Supervisi):** **{locked_point_today['warkop']}** "
                    f"({locked_point_today['kecamatan']} • **{st_lock_spg}**){kontak_info}"
                )
            else:
                st.error("⛔ **Menunggu Supervisi Save Titik LKK.** Form input SPG belum dibuka.")
        with col_spg_s2:
            st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)
            if st.button("🔄 Refresh", key="btn_refresh_spg_sync", use_container_width=True):
                st.rerun()

        if locked_point_today:
            kecamatan_pilihan = locked_point_today["kecamatan"] or "-"
            nama_warkop_manual = locked_point_today["warkop"]
            alamat_warkop_terpilih = locked_point_today["alamat"]
            status_warkop_terpilih = locked_point_today.get("status_kunjungan", VISIT_STATUS_WAJIB)
        else:
            kecamatan_pilihan = "-"
            nama_warkop_manual = ""
            alamat_warkop_terpilih = "-"
            status_warkop_terpilih = "-"

    st.markdown(f"""
    <div class="address-box">
        📍 <b>Kecamatan:</b> {kecamatan_pilihan} &nbsp;|&nbsp; <b>Warkop / LKK:</b> {nama_warkop_manual or '(Belum di-save Supervisi)'} &nbsp;|&nbsp; <b>Status:</b> {status_warkop_terpilih}<br/>
        🏠 <b>Alamat:</b> {alamat_warkop_terpilih}
    </div>
    """, unsafe_allow_html=True)

# ====================================================
# MODE SUPERVISI (SAVE KONTAK & REKAP PER TITIK LKK)
# ====================================================
if st.session_state["login_mode"] == "Supervisi":
    st.markdown("---")
    st.markdown(f"### 👀 Dashboard Monitoring & Entry Supervisi: {st.session_state['user_spg']} (Plat Mobil: `{st.session_state['plat_mobil']}`)")

    sup_nonce = st.session_state.get("sup_kontak_nonce", 0)
    with st.form(f"form_entry_kontak_supervisi_{sup_nonce}"):
        st.markdown("#### 📝 Save Jumlah Kontak Konsumen Tim (Setelah SPG Selesai Jualan)")
        if not str(nama_warkop_manual).strip():
            st.warning("Pilih dan save Titik LKK terlebih dahulu sebelum menyimpan jumlah kontak konsumen.")
        jumlah_kontak_input = st.number_input(
            f"Jumlah Kontak Konsumen Tim di {nama_warkop_manual or 'Titik LKK'}",
            min_value=0,
            step=1,
            value=0,
            key=f"input_jumlah_kontak_sup_{sup_nonce}",
        )
        if st.form_submit_button("💾 Save Jumlah Kontak Konsumen", type="primary"):
            if not str(nama_warkop_manual).strip():
                st.error("❌ Gagal menyimpan kontak: Titik LKK belum dipilih/disimpan.")
            else:
                df_sup_db = load_supervisi_database()
                waktu_wib = datetime.utcnow() + timedelta(hours=7)
                new_sup_row = {
                    "Waktu": waktu_wib.strftime("%Y-%m-%d %H:%M:%S"),
                    "Promotor": st.session_state["user_spg"],
                    "Plat_Mobil": st.session_state["plat_mobil"],
                    "Kota_Kab": st.session_state["kota_kab"],
                    "Kecamatan": kecamatan_pilihan,
                    "Warkop_LKK": str(nama_warkop_manual).strip(),
                    "Alamat_Warkop": alamat_warkop_terpilih,
                    "Jumlah_Kontak_Manual": int(jumlah_kontak_input),
                }
                df_sup_db = pd.concat([df_sup_db, pd.DataFrame([new_sup_row])], ignore_index=True)
                save_supervisi_database(df_sup_db)
                st.session_state["sup_kontak_nonce"] = sup_nonce + 1
                st.session_state["sup_last_saved_msg"] = f"✅ Berhasil menyimpan **{jumlah_kontak_input} kontak tim** untuk **{nama_warkop_manual}**!"
                st.rerun()

    if st.session_state.get("sup_last_saved_msg"):
        st.success(st.session_state.pop("sup_last_saved_msg"))

    df_all_db = load_database()
    df_sup_db = load_supervisi_database()
    df_current_team_spg = df_all_db[df_all_db["Promotor"] == st.session_state["user_spg"]].copy() if not df_all_db.empty else pd.DataFrame()
    df_current_team_sup = df_sup_db[df_sup_db["Promotor"] == st.session_state["user_spg"]].copy() if not df_sup_db.empty else pd.DataFrame()
    today_str_sup = (datetime.utcnow() + timedelta(hours=7)).strftime("%Y-%m-%d")
    harga_konsumen_map = load_harga_konsumen()

    df_team_spg_today = pd.DataFrame()
    if not df_current_team_spg.empty:
        df_current_team_spg["Jumlah_Bungkus"] = pd.to_numeric(df_current_team_spg["Jumlah_Bungkus"], errors="coerce").fillna(0)
        df_current_team_spg["Harga_Konsumen"] = df_current_team_spg["Brand_Rokok"].apply(lambda b: get_harga_konsumen_brand(b, harga_konsumen_map))
        df_current_team_spg["Total_Uang_Rp"] = (df_current_team_spg["Jumlah_Bungkus"] * df_current_team_spg["Harga_Konsumen"]).astype(int)
        df_team_spg_today = df_current_team_spg[df_current_team_spg["Waktu"].astype(str).str.startswith(today_str_sup)].copy()

    df_lkk_active_spg = (
        df_team_spg_today[df_team_spg_today["Warkop_LKK"].astype(str).str.strip() == str(nama_warkop_manual).strip()]
        if not df_team_spg_today.empty and str(nama_warkop_manual).strip()
        else pd.DataFrame()
    )

    kontak_supervisi_team_lkk = 0
    if not df_current_team_sup.empty and str(nama_warkop_manual).strip():
        df_lkk_active_sup = df_current_team_sup[
            (df_current_team_sup["Warkop_LKK"].astype(str).str.strip() == str(nama_warkop_manual).strip())
            & (df_current_team_sup["Waktu"].astype(str).str.startswith(today_str_sup))
        ]
        if not df_lkk_active_sup.empty:
            kontak_supervisi_team_lkk = int(pd.to_numeric(df_lkk_active_sup["Jumlah_Kontak_Manual"], errors="coerce").fillna(0).sum())

    total_uang_2spg_today = int(df_team_spg_today["Total_Uang_Rp"].sum()) if not df_team_spg_today.empty else 0
    spg_2spg_today_list = df_team_spg_today["Nama_SPG"].dropna().astype(str).str.strip().unique().tolist() if not df_team_spg_today.empty else []

    col_mon1, col_mon2, col_mon3, col_mon4 = st.columns(4)
    with col_mon1:
        st.markdown(f'<div class="dashboard-card"><div class="card-value">{kontak_supervisi_team_lkk}</div><div class="card-label">Kontak Supervisi Team</div></div>', unsafe_allow_html=True)
    with col_mon2:
        st.markdown(f'<div class="dashboard-card"><div class="card-value">{len(df_lkk_active_spg)}</div><div class="card-label">Konsumen Beli (LKK Ini)</div></div>', unsafe_allow_html=True)
    with col_mon3:
        st.markdown(f'<div class="dashboard-card"><div class="card-value" style="color: #16A34A;">Rp {total_uang_2spg_today:,}</div><div class="card-label">Uang Terkumpul 2 SPG Hari Ini</div></div>', unsafe_allow_html=True)
    with col_mon4:
        spg_list_str = ", ".join(spg_2spg_today_list) if spg_2spg_today_list else "Belum ada SPG"
        st.markdown(f'<div class="dashboard-card"><div class="card-value" style="font-size: 1.05rem; padding-top: 6px;">{spg_list_str}</div><div class="card-label">SPG Bertugas Hari Ini</div></div>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("#### 📑 Log Detail Konsumen Beli (SPG) di Warkop Ini")
    if not df_lkk_active_spg.empty:
        st.dataframe(df_lkk_active_spg.drop(columns=["Waktu", "Promotor", "Plat_Mobil"], errors="ignore"), use_container_width=True)
    else:
        st.info(f"Belum ada data konsumen beli masuk untuk titik Warkop / LKK '{nama_warkop_manual or '-'}'.")

    st.stop()

# ====================================================
# MODE SPG
# ====================================================
today_wib_spg = (datetime.utcnow() + timedelta(hours=7)).date()
today_str_spg = today_wib_spg.strftime("%Y-%m-%d")
sektor_aktif_spg = locked_point_today["kecamatan"] if locked_point_today else st.session_state.get("sektor_terjadwal_login", "")
personnel_spg_today = get_scheduled_personnel_for_team(st.session_state["user_spg"], today_wib_spg, selected_kecamatan=sektor_aktif_spg)
daftar_spg_terjadwal = personnel_spg_today.get("spg_all", []) or st.session_state.get("spg_terjadwal_list", [])

if daftar_spg_terjadwal:
    nama_spg_manual = st.selectbox("👩‍💼 Pilih Nama SPG yang Bertugas (Sesuai Jadwal Hari Ini)", options=daftar_spg_terjadwal, key="spg_active_name_selector")
else:
    daftar_master_spg = load_master_spgs()
    nama_spg_manual = st.selectbox("👩‍💼 Pilih Nama SPG yang Bertugas", options=daftar_master_spg, key="spg_active_name_selector") if daftar_master_spg else st.text_input("👩‍💼 Nama SPG (Entry Manual)", key="spg_active_name_selector")

df_db_spg_top = load_database()
spg_active_clean = str(nama_spg_manual or "").strip()
team_active_clean = str(st.session_state["user_spg"] or "").strip()

total_laku_spg_today = 0
total_laku_team_today = 0
brands_spg_today = []

if not df_db_spg_top.empty and "Promotor" in df_db_spg_top.columns:
    df_db_spg_top["Jumlah_Bungkus"] = pd.to_numeric(df_db_spg_top["Jumlah_Bungkus"], errors="coerce").fillna(0)
    df_team_today_top = df_db_spg_top[
        (df_db_spg_top["Promotor"].astype(str).str.strip().str.casefold() == team_active_clean.casefold())
        & (df_db_spg_top["Waktu"].astype(str).str.startswith(today_str_spg))
    ]
    total_laku_team_today = int(df_team_today_top["Jumlah_Bungkus"].sum())
    if spg_active_clean:
        df_spg_today_top = df_team_today_top[df_team_today_top["Nama_SPG"].astype(str).str.strip().str.casefold() == spg_active_clean.casefold()]
        total_laku_spg_today = int(df_spg_today_top["Jumlah_Bungkus"].sum())
        brands_spg_today = df_spg_today_top["Brand_Rokok"].dropna().astype(str).unique().tolist()

brands_for_target = personnel_spg_today.get("brands", []) or brands_spg_today
target_spg_today = max(int(get_target_for_brand(b, "target_spg", 30)) for b in brands_for_target) if brands_for_target else 30
is_achieved_today = total_laku_spg_today >= target_spg_today
kurang_target_today = max(0, target_spg_today - total_laku_spg_today)
status_badge_spg = (
    '<span style="background:#DCFCE7;color:#15803D;padding:5px 14px;border-radius:999px;font-weight:700;font-size:0.88rem;">✅ ACHIEVED</span>'
    if is_achieved_today
    else f'<span style="background:#FEE2E2;color:#B91C1C;padding:5px 14px;border-radius:999px;font-weight:700;font-size:0.88rem;">⏳ BELUM ACHIEVED (Kurang {kurang_target_today} bks)</span>'
)

st.markdown(
    f"""
    <div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:12px;padding:14px 18px;margin:10px 0 14px 0;box-shadow:0 1px 3px rgba(0,0,0,0.05);">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;">
            <div>
                <div style="font-size:0.82rem;color:#64748B;font-weight:600;">🚬 TOTAL ROKOK LAKU TERJUAL HARI INI ({spg_active_clean or 'SPG'})</div>
                <div style="font-size:1.7rem;font-weight:800;color:#0F172A;line-height:1.2;">
                    {total_laku_spg_today:,} <span style="font-size:0.95rem;font-weight:600;color:#475569;">/ {target_spg_today:,} bungkus</span>
                </div>
                <div style="font-size:0.8rem;color:#64748B;margin-top:2px;">Total terjual tim hari ini (2 SPG): <b>{total_laku_team_today:,} bungkus</b></div>
            </div>
            <div>{status_badge_spg}</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

has_locked_lkk = locked_point_today is not None and str(nama_warkop_manual).strip() != ""
if not has_locked_lkk:
    st.error("🔒 **Form Input SPG Terkunci:** Supervisi belum memilih dan menyimpan (**Save Titik LKK**) titik lokasi LKK hari ini.")
elif str(nama_spg_manual).strip() != "":
    if st.session_state.get("spg_last_saved_msg"):
        st.balloons()
        st.success(st.session_state.pop("spg_last_saved_msg"))

    spg_nonce = st.session_state.get("spg_form_nonce", 0)
    with st.form(f"form_laporan_spg_{spg_nonce}"):
        st.markdown("### 📝 Form Input Laporan Konsumen")
        all_master_brands = load_master_brands()
        team_brands_map = load_master_team_brands()
        team_names_map = load_master_team_names()
        allowed_brands_for_team = resolve_team_allowed_brands(
            team_name=st.session_state["user_spg"],
            all_brands=all_master_brands,
            team_brands_map=team_brands_map,
            team_names_map=team_names_map,
            prefer_keyword_match=True,
        ) or all_master_brands

        col_f1, col_f2 = st.columns([1.3, 0.7])
        with col_f1:
            brand_entry = st.selectbox("🚬 Brand Rokok", options=allowed_brands_for_team, key=f"spg_brand_{spg_nonce}")
        with col_f2:
            jumlah_bungkus = st.number_input("📦 Jumlah Bungkus", min_value=1, step=1, value=1, key=f"spg_bungkus_{spg_nonce}")

        nama_konsumen = st.text_input("👤 Nama Konsumen", placeholder="Masukkan nama konsumen", key=f"spg_konsumen_{spg_nonce}")

        col_g1, col_g2 = st.columns(2)
        with col_g1:
            gender_entry = st.radio("⚧️ Gender", ["L", "P"], horizontal=True, key=f"spg_gender_{spg_nonce}")
        with col_g2:
            range_umur_entry = st.selectbox("🎂 Range Umur", options=["18-24", "25-30", "31-35", "36-44", "45+"], key=f"spg_umur_{spg_nonce}")

        col_c1, col_c2 = st.columns(2)
        with col_c1:
            nohp_entry = st.text_input("📱 No HP", placeholder="081234567890", key=f"spg_nohp_{spg_nonce}")
        with col_c2:
            instagram_input = st.text_input("📸 Instagram", placeholder="username_ig", key=f"spg_ig_{spg_nonce}")

        rokok_asal_bumo = st.text_input("🔄 Rokok Asal (BUMO)", placeholder="Merk rokok sebelumnya", key=f"spg_bumo_{spg_nonce}")

        if st.form_submit_button("🚀 Kirim Laporan", type="primary", use_container_width=True):
            if not nama_konsumen.strip():
                st.warning("Mohon isi nama konsumen.")
            else:
                ig_formatted = f"@{instagram_input.strip().lstrip('@')}" if instagram_input.strip() else "-"
                waktu_wib = datetime.utcnow() + timedelta(hours=7)
                data_baru = {
                    "Waktu": waktu_wib.strftime("%Y-%m-%d %H:%M:%S"),
                    "Promotor": st.session_state["user_spg"],
                    "Plat_Mobil": st.session_state["plat_mobil"],
                    "Nama_SPG": str(nama_spg_manual).strip(),
                    "Kota_Kab": st.session_state["kota_kab"],
                    "Kecamatan": kecamatan_pilihan,
                    "Warkop_LKK": str(nama_warkop_manual).strip(),
                    "Alamat_Warkop": alamat_warkop_terpilih,
                    "Brand_Rokok": brand_entry,
                    "Nama_Konsumen": nama_konsumen.strip(),
                    "Gender": gender_entry,
                    "Range_Umur": range_umur_entry,
                    "No_HP": nohp_entry.strip(),
                    "Instagram": ig_formatted,
                    "Jumlah_Bungkus": jumlah_bungkus,
                    "Rokok_Asal_BUMO": rokok_asal_bumo.strip(),
                    "Latitude": user_lat,
                    "Longitude": user_lon,
                }
                df_all = pd.concat([load_database(), pd.DataFrame([data_baru])], ignore_index=True)
                save_database(df_all)
                st.session_state["spg_form_nonce"] = spg_nonce + 1
                st.session_state["spg_last_saved_msg"] = f"🎉 Laporan konsumen **{nama_konsumen}** oleh **{str(nama_spg_manual).strip()}** berhasil disimpan!"
                st.rerun()

st.markdown("---")
st.markdown(f"### 📈 Evaluasi Harian & Log Rekap: {st.session_state['user_spg']} ({st.session_state['kota_kab']})")
df_master_all = load_database()
df_user_rekap = df_master_all[df_master_all["Promotor"] == st.session_state["user_spg"]].copy() if not df_master_all.empty else pd.DataFrame()

if not df_user_rekap.empty:
    df_user_rekap["Waktu_Dt"] = pd.to_datetime(df_user_rekap["Waktu"], errors="coerce")
    df_user_rekap["Tanggal"] = df_user_rekap["Waktu_Dt"].dt.strftime("%d-%m-%Y")
    df_user_rekap = add_custom_week_columns(df_user_rekap, "Waktu_Dt")
    df_user_rekap["Jumlah_Bungkus"] = pd.to_numeric(df_user_rekap["Jumlah_Bungkus"], errors="coerce").fillna(0)
    st.dataframe(df_user_rekap.drop(columns=["Waktu_Dt"], errors="ignore"), use_container_width=True)
else:
    st.info(f"Belum ada data laporan tersimpan untuk {st.session_state['user_spg']}.")
