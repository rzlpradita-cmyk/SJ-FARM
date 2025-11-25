import os
import sqlite3
from datetime import datetime
import streamlit as st
from PIL import Image
import base64
import pandas as pd
import hashlib 
from io import BytesIO 

# ======================================================================
# 1. KONFIGURASI APLIKASI DAN AKUN MASTER
# ======================================================================

MASTER_DB = "accounts.db"
TABLE_NAME = "jurnal"
INVENTORY_TABLE_NAME = "inventory"

# Konfigurasi Warna
BG_PAGE = "#FDF6E3"
DARK_HEADER = "#3A4F35"
NAV_COLOR = "#4F7942"
ACCENT_GOLD = "#6B8E23"
TEXT_COLOR = "#3E2F24"
BUTTON_COLOR = "#4F7942"

# Daftar Akun Master
AKUN_ASET = [
    "Kas", "Piutang usaha", "Persediaan kambing jantan", "Persediaan kambing betina",
    "Aset biologis - kambing kecil", "Persediaan pakan", "Persediaan obat & vitamin",
    "Bangunan kandang", "Kendaraan"
]
AKUN_KEWAJIBAN = [ "Utang usaha", "Utang lain-lain" ]
AKUN_EKUITAS = [ "Modal", "Prive" ]
AKUN_PENDAPATAN = [ "Penjualan", "Pendapatan lain-lain" ]
AKUN_BEBAN = [
    "HPP", "Beban gaji", "Beban reparasi kandang", "Beban listrik & air",
    "Beban pakan ternak", "Beban obat & vitamin", "Beban penyusutan"
]
AKUN_KONTRA = [ "Akumulasi penyusutan" ]

DEBIT_CHOICES = AKUN_ASET + AKUN_KEWAJIBAN + AKUN_EKUITAS + AKUN_PENDAPATAN + AKUN_BEBAN + AKUN_KONTRA
GENERAL_LEDGER_ACCOUNTS = DEBIT_CHOICES
INVENTORY_ACCOUNT_CHOICES = ["Persediaan kambing jantan", "Persediaan kambing betina"]
MAIN_SHEETS = ["Penjualan", "Pembelian", "Lain-lain", "Inventory_Data", "Saldo_Awal"]

# ======================================================================
# 2. FUNGSI UTILITY EKSPOR XLSX
# ======================================================================

def to_excel(df, sheet_name="Sheet1"):
    """Konversi DataFrame ke file Excel (BytesIO)"""
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
    processed_data = output.getvalue()
    return processed_data

def add_download_button(df, filename, label="⬇️ Unduh Data (.xlsx)", key_suffix=""):
    """Menambahkan tombol unduh untuk DataFrame"""
    if df.empty:
        st.warning("Data kosong, tidak bisa diunduh.")
        return

    df_clean = df.copy()

    # Logika Pembersihan Format Mata Uang dan Teks
    for col in df_clean.columns:
        if df_clean[col].dtype == 'object':
            if 'Rp.' in str(df_clean[col].iloc[0] if not df_clean.empty else ''):
                try:
                    # Hapus Rp. dan pemisah ribuan/desimal untuk konversi numerik
                    df_clean[col] = df_clean[col].astype(str).str.replace('Rp. ', '', regex=False).str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
                    df_clean[col] = df_clean[col].str.replace('(', '-', regex=False).str.replace(')', '', regex=False)
                    df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce').fillna(0.0).round(2)
                except Exception:
                    pass
            
            if col in ['Keterangan', 'Deskripsi']:
                 df_clean[col] = df_clean[col].astype(str).str.replace('**', '', regex=False).str.replace('    ', '', regex=False).str.strip()

    if 'Waktu' in df_clean.columns:
        try:
             # Konversi kolom Waktu ke format tanggal string YYYY-MM-DD
             df_clean['Waktu'] = pd.to_datetime(df_clean['Waktu'], errors='coerce').dt.date.astype(str)
        except:
             pass

    excel_data = to_excel(df_clean)
    st.download_button(
        label=label,
        data=excel_data,
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"download_{key_suffix}"
    )

# ======================================================================
# 3. FUNGSI UTILITY DATABASE & AKUN
# ======================================================================

def hash_password(password):
    """Menghash password menggunakan SHA224"""
    return hashlib.sha224(password.encode()).hexdigest()

def get_master_db_connection():
    """Koneksi ke database master akun (accounts.db)"""
    conn = sqlite3.connect(MASTER_DB)
    conn.row_factory = sqlite3.Row 
    return conn

def setup_master_database():
    """Membuat tabel master akun jika belum ada"""
    conn = get_master_db_connection()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            db_path TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def get_db_connection(db_path):
    """Koneksi ke database transaksi spesifik user (dynamis path)"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row 
    return conn

def setup_user_database(db_path):
    """Menginisialisasi tabel jurnal dan inventory di database user baru"""
    conn = get_db_connection(db_path)
    c = conn.cursor()

    # Tabel Jurnal
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            Waktu TEXT,
            Deskripsi TEXT,
            Metode TEXT,
            Source_Sheet TEXT, 
            D1_Akun TEXT,
            D1_Nominal REAL DEFAULT 0.0, 
            D2_Akun TEXT DEFAULT NULL,
            D2_Nominal REAL DEFAULT 0.0, 
            K1_Akun TEXT,
            K1_Nominal REAL DEFAULT 0.0, 
            K2_Akun TEXT DEFAULT NULL,
            K2_Nominal REAL DEFAULT 0.0, 
            Customer_Supplier TEXT,
            Kategori_Ternak TEXT,
            Harga_Satuan REAL DEFAULT 0.0,
            Jumlah_Unit REAL DEFAULT 0.0,
            Total_Nilai REAL DEFAULT 0.0
        )
    """)

    # Tabel Inventory
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS {INVENTORY_TABLE_NAME} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            Waktu TEXT,
            Tipe TEXT,
            Kategori TEXT,
            Harga REAL DEFAULT 0.0,
            Jumlah INTEGER DEFAULT 0,
            Total REAL DEFAULT 0.0
        )
    """)
    conn.commit()
    conn.close()

def register_user(username, password):
    """Mendaftarkan user baru dan membuat database transaksi mereka"""
    if not username or not password:
        return False, "Username dan password tidak boleh kosong."

    conn_master = get_master_db_connection()
    c_master = conn_master.cursor()
    
    c_master.execute("SELECT username FROM users WHERE username = ?", (username,))
    if c_master.fetchone():
        conn_master.close()
        return False, "Username sudah terdaftar. Silakan pilih yang lain."

    db_path = f"{username}_transaksi.db"
    hashed_pass = hash_password(password)

    try:
        c_master.execute("INSERT INTO users (username, password_hash, db_path) VALUES (?, ?, ?)", 
                             (username, hashed_pass, db_path))
        conn_master.commit()
        conn_master.close()

        setup_user_database(db_path)

        return True, "Registrasi berhasil! Silakan login."
    except Exception as e:
        return False, f"Gagal menyimpan data: {e}"

# ======================================================================
# 4. FUNGSI CRUD (DYNAMIC PATH)
# ======================================================================

def append_row_to_sheet(sheet_name, row_data):
    """Menambahkan baris data ke tabel jurnal atau inventory."""
    db_path = st.session_state.get('db_path')
    if not db_path: raise ConnectionError("DB path tidak ditemukan.")
    
    conn = get_db_connection(db_path)
    c = conn.cursor()
    
    if sheet_name == "Inventory_Data":
        table_name = INVENTORY_TABLE_NAME
        columns = ["Waktu", "Tipe", "Kategori", "Harga", "Jumlah", "Total"]
        data = tuple(row_data)

        if len(data) != len(columns):
             conn.close()
             raise ValueError("Jumlah kolom untuk Inventory_Data tidak sesuai.")

        placeholders = ', '.join(['?' for _ in columns])
        c.execute(f"INSERT INTO {table_name} ({','.join(columns)}) VALUES ({placeholders})", data)
        
    else:
        table_name = TABLE_NAME
        columns = [
            "Waktu", "Deskripsi", "Metode", "Source_Sheet",
            "D1_Akun", "D1_Nominal", "D2_Akun", "D2_Nominal",
            "K1_Akun", "K1_Nominal", "K2_Akun", "K2_Nominal",
            "Customer_Supplier", "Kategori_Ternak", "Harga_Satuan",
            "Jumlah_Unit", "Total_Nilai"
        ]
        
        data_to_insert = [
             row_data[0], row_data[1], row_data[2], 
             sheet_name,
             row_data[3], row_data[4], row_data[5], row_data[6],
             row_data[7], row_data[8], row_data[9], row_data[10],
             row_data[11], row_data[12], row_data[13], row_data[14],
             row_data[15]
        ]
        
        if len(data_to_insert) != len(columns):
            conn.close()
            raise ValueError("Jumlah kolom untuk Jurnal/Transaksi tidak sesuai.")

        placeholders = ', '.join(['?' for _ in columns])
        c.execute(f"INSERT INTO {table_name} ({','.join(columns)}) VALUES ({placeholders})", tuple(data_to_insert))

    conn.commit()
    conn.close()
    return True

def delete_rows_from_sheet(sheet_name, ids_to_delete):
    """Menghapus baris data dari tabel jurnal atau inventory berdasarkan ID."""
    db_path = st.session_state.get('db_path')
    if not db_path: return 0
    
    if not ids_to_delete: return 0
    
    ids_to_delete_int = [int(i) for i in ids_to_delete]
    
    conn = get_db_connection(db_path)
    c = conn.cursor()
    deleted_count = 0
    
    try:
        if sheet_name == "Inventory_Data":
            table_name = INVENTORY_TABLE_NAME
        else:
            table_name = TABLE_NAME
            
        placeholders = ', '.join(['?' for _ in ids_to_delete_int])
        c.execute(f"DELETE FROM {table_name} WHERE id IN ({placeholders})", ids_to_delete_int)
        deleted_count = c.rowcount
        
        conn.commit()
        
    except Exception as e:
        st.error(f"Gagal menghapus data dari {table_name}: {e}")
        deleted_count = 0
    finally:
        conn.close()

    return deleted_count

# ======================================================================
# 5. FUNGSI PEMUATAN DATA (HANYA AMBIL TANGGAL)
# ======================================================================

def safe_float_conversion(value):
    """Mengkonversi nilai ke float dengan penanganan error."""
    if value is None: return 0.0
    try: 
        if isinstance(value, str):
            # Mengganti pemisah ribuan (titik) dan desimal (koma) jika ada, lalu konversi
            return float(value.replace('.', '').replace(',', '.').strip()) 
        return float(value)
    except (ValueError, TypeError): return 0.0

def safe_int_conversion(value):
    """Mengkonversi nilai ke integer dengan penanganan error."""
    if value is None: return 0
    try: 
        if isinstance(value, str):
            # Konversi string numerik ke float dulu, lalu ke int
            return int(float(value.replace('.', '').replace(',', '.').strip()))
        return int(float(value))
    except (ValueError, TypeError): return 0

def load_transactions_data(sheet_names):
    """Memuat semua data transaksi dari Source_Sheet tertentu."""
    db_path = st.session_state.get('db_path')
    if not db_path: return []

    all_transactions = []
    
    try:
        conn = get_db_connection(db_path)
    except Exception:
        return []
    
    placeholders = ', '.join(['?' for _ in sheet_names])
    query_base = f"""
        SELECT * FROM {TABLE_NAME} 
        WHERE Source_Sheet IN ({placeholders})
        ORDER BY Waktu
    """
    
    try:
        df = pd.read_sql_query(query_base, conn, params=sheet_names)
        
        for index, row in df.iterrows():
            
            waktu_str = str(row['Waktu']).split(' ')[0] 
            
            transaction = {
                "id": row['id'], 
                "Waktu": waktu_str, 
                "Deskripsi": row['Deskripsi'], 
                "Metode": row['Metode'] if row['Source_Sheet'] != "Saldo_Awal" else "SALDO AWAL",
                
                "D1_Akun": row['D1_Akun'], 
                "D1_Nominal": safe_float_conversion(row['D1_Nominal']),
                "D2_Akun": row['D2_Akun'], 
                "D2_Nominal": safe_float_conversion(row['D2_Nominal']),
                "K1_Akun": row['K1_Akun'], 
                "K1_Nominal": safe_float_conversion(row['K1_Nominal']),
                "K2_Akun": row['K2_Akun'], 
                "K2_Nominal": safe_float_conversion(row['K2_Nominal']),
                
                "Customer": row['Customer_Supplier'], 
                "Source_Sheet": row['Source_Sheet'],
                "Total_Nilai": safe_float_conversion(row['Total_Nilai']),
                "Row_Index": row['id'] 
            }
            all_transactions.append(transaction)
            
    except Exception as e:
        if "no such table" not in str(e):
             st.warning(f"Gagal memuat data transaksi: {e}")
    finally:
        conn.close()

    return all_transactions

def get_last_average_cost(kategori_name):
    """Menghitung saldo ekor dan biaya rata-rata (Moving Average) terakhir untuk kategori tertentu."""
    db_path = st.session_state.get('db_path')
    if not db_path: return 0, 0.0

    saldo_ekor = 0
    saldo_total = 0.0
    
    conn = get_db_connection(db_path)
    try:
        query = f"""
            SELECT Tipe, Jumlah, Total 
            FROM {INVENTORY_TABLE_NAME} 
            WHERE Kategori = ? 
            ORDER BY Waktu ASC
        """
        df = pd.read_sql_query(query, conn, params=[kategori_name])
        
        for index, row in df.iterrows():
            tipe = row['Tipe']
            jumlah = safe_int_conversion(row['Jumlah'])
            total = safe_float_conversion(row['Total'])
            
            if tipe == "Pembelian" or tipe == "SALDO AWAL":
                saldo_ekor += jumlah
                saldo_total += total
            elif tipe == "Penjualan":
                # Pengurangan saat penjualan, menggunakan HPP yang sudah dicatat
                saldo_ekor -= jumlah
                saldo_total -= total 
                
        if saldo_ekor > 0:
            avg_cost = saldo_total / saldo_ekor
            return saldo_ekor, avg_cost
        else:
            return 0, 0.0
            
    except Exception:
        return 0, 0.0
    finally:
        conn.close()

# ======================================================================
# 6. FUNGSI AKUNTANSI & LAPORAN
# ======================================================================

def get_customer_supplier_list():
    """Mengambil daftar Customer/Supplier unik dari semua transaksi."""
    transactions = load_transactions_data(MAIN_SHEETS)  
    all_parties = set()
    for t in transactions:
        if t.get("Customer"):
            all_parties.add(t["Customer"])
    return sorted(list(all_parties))

def calculate_account_balance(akun_name):
    """Menghitung saldo akhir akun (termasuk Saldo Awal)."""
    transactions = load_transactions_data(MAIN_SHEETS)
    
    total_debit = 0.0
    total_kredit = 0.0
    
    for trx in transactions:
        if trx["D1_Akun"] == akun_name: total_debit += trx["D1_Nominal"]
        if trx["D2_Akun"] == akun_name: total_debit += trx["D2_Nominal"]
        
        if trx["K1_Akun"] == akun_name: total_kredit += trx["K1_Nominal"]
        if trx["K2_Akun"] == akun_name: total_kredit += trx["K2_Nominal"]
    
    # Menentukan Saldo Normal Akun
    if akun_name in AKUN_ASET or akun_name in AKUN_BEBAN or akun_name == "Prive":
        saldo = total_debit - total_kredit # Saldo Normal Debit
    elif akun_name in AKUN_KEWAJIBAN or akun_name in AKUN_PENDAPATAN or akun_name == "Modal" or akun_name in AKUN_KONTRA:
        saldo = total_kredit - total_debit # Saldo Normal Kredit
    else:
        saldo = total_debit - total_kredit # Default Debit
    
    return saldo

def calculate_account_balance_non_sa(akun_name):
    """Menghitung saldo akun hanya dari transaksi NON-Saldo_Awal."""
    transactions = load_transactions_data(["Penjualan", "Pembelian", "Lain-lain"]) 
    
    total_debit = 0.0
    total_kredit = 0.0
    
    for trx in transactions:
        if trx["D1_Akun"] == akun_name: total_debit += trx["D1_Nominal"]
        if trx["D2_Akun"] == akun_name: total_debit += trx["D2_Nominal"]
        
        if trx["K1_Akun"] == akun_name: total_kredit += trx["K1_Nominal"]
        if trx["K2_Akun"] == akun_name: total_kredit += trx["K2_Nominal"]
    
    # Menentukan Saldo Normal Akun
    if akun_name in AKUN_ASET or akun_name in AKUN_BEBAN or akun_name == "Prive":
        saldo = total_debit - total_kredit # Saldo Normal Debit
    elif akun_name in AKUN_KEWAJIBAN or akun_name in AKUN_PENDAPATAN or akun_name == "Modal" or akun_name in AKUN_KONTRA:
        saldo = total_kredit - total_debit # Saldo Normal Kredit
    else:
        saldo = total_debit - total_kredit
    
    return saldo

def get_formatted_journal_data(sheet_names):
    """Memformat data transaksi mentah menjadi format jurnal umum untuk tampilan."""
    raw_data = load_transactions_data(sheet_names)
    formatted_journal = []

    for transaction in raw_data:
        if transaction["Source_Sheet"] == "Saldo_Awal":
            continue
            
        waktu = transaction["Waktu"]
        deskripsi = transaction["Deskripsi"]
        sort_key = str(waktu)
        row_index = transaction["Row_Index"] 

        # Entri Debit 1
        if transaction["D1_Nominal"] > 0 and transaction["D1_Akun"]:
            keterangan = f"{transaction['D1_Akun']} ({deskripsi})"
            formatted_journal.append({
                "Waktu": waktu,
                "Keterangan": keterangan,
                "Debit": transaction["D1_Nominal"],
                "Kredit": 0.0,
                "Sort_Key": sort_key,
                "Row_Index": row_index
            })

        # Entri Debit 2
        if transaction["D2_Nominal"] > 0 and transaction["D2_Akun"]:
            formatted_journal.append({
                "Waktu": "",
                "Keterangan": transaction["D2_Akun"],
                "Debit": transaction["D2_Nominal"],
                "Kredit": 0.0,
                "Sort_Key": sort_key,
                "Row_Index": row_index
            })

        # Entri Kredit 1
        if transaction["K1_Nominal"] > 0 and transaction["K1_Akun"]:
            keterangan = f"    {transaction['K1_Akun']}"
            formatted_journal.append({
                "Waktu": "",
                "Keterangan": keterangan,  
                "Debit": 0.0,
                "Kredit": transaction["K1_Nominal"],
                "Sort_Key": sort_key,
                "Row_Index": row_index
            })
        
        # Entri Kredit 2
        if transaction["K2_Nominal"] > 0 and transaction["K2_Akun"]:
            formatted_journal.append({
                "Waktu": "",
                "Keterangan": f"    {transaction['K2_Akun']}",  
                "Debit": 0.0,
                "Kredit": transaction["K2_Nominal"],
                "Sort_Key": sort_key,
                "Row_Index": row_index
            })
            
    formatted_journal.sort(key=lambda x: str(x["Sort_Key"]))
    return formatted_journal

def get_ledger_data_for_display(akun_name, all_transactions):
    """Mendapatkan data mutasi akun dalam format Buku Besar."""
    ledger_entries = []
    
    saldo_awal = 0.0
    # Tentukan Saldo Normal Multiplier (1 untuk Debit, -1 untuk Kredit)
    if akun_name in AKUN_ASET or akun_name in AKUN_BEBAN or akun_name == "Prive":
        saldo_normal_multiplier = 1
    else:
        saldo_normal_multiplier = -1
        
    # --- HITUNG SALDO AWAL (termasuk dari SA Mitra dan SA Akun) ---
    saldo_awal_entries = [t for t in all_transactions if t["Source_Sheet"] == "Saldo_Awal"]
    
    initial_balance_ids = []
    total_debit_sa = 0.0
    total_kredit_sa = 0.0
    
    for t in saldo_awal_entries:
        # Hanya hitung jika nominal > 0.01 (untuk menghindari float error)
        debit_sa = t["D1_Nominal"] if t["D1_Akun"] == akun_name else 0.0
        debit_sa += t["D2_Nominal"] if t["D2_Akun"] == akun_name else 0.0
        
        kredit_sa = t["K1_Nominal"] if t["K1_Akun"] == akun_name else 0.0
        kredit_sa += t["K2_Nominal"] if t["K2_Akun"] == akun_name else 0.0
        
        if debit_sa > 0.01 or kredit_sa > 0.01:
            if saldo_normal_multiplier == 1:
                saldo_awal += (debit_sa - kredit_sa)
            else:
                saldo_awal += (kredit_sa - debit_sa)
            
            # Kumpulkan ID dan mutasi detailnya
            if debit_sa > 0.01: 
                total_debit_sa += debit_sa
                initial_balance_ids.append({"id": t["id"], "is_debit": True, "nominal": debit_sa})
            if kredit_sa > 0.01:
                total_kredit_sa += kredit_sa
                initial_balance_ids.append({"id": t["id"], "is_debit": False, "nominal": kredit_sa})

    # Tampilkan Saldo Awal sebagai SATU BARIS jika totalnya signifikan
    if abs(saldo_awal) > 0.01:
        sa_ids_string = ",".join([str(d["id"]) for d in initial_balance_ids])
        
        ledger_entries.append({
            "Waktu": "Awal Periode",  
            "Deskripsi": "Saldo Awal",
            "Debit": total_debit_sa,  
            "Kredit": total_kredit_sa,
            "Saldo Akhir": saldo_awal,
            "Source_Sheet": "Saldo_Awal",
            "Row_Index": -1, # Tanda bahwa ini baris Saldo Awal TOTAL
            "Tipe_Entry": "Saldo Awal Total",
            "SA_Detail_IDs": sa_ids_string 
        })
        
    saldo_berjalan = saldo_awal
    
    # --- PROSES TRANSAKSI NORMAL ---
    for t in all_transactions:
        if t["Source_Sheet"] == "Saldo_Awal": continue

        debit = 0.0
        kredit = 0.0
        
        if t["D1_Akun"] == akun_name: debit += t["D1_Nominal"]
        if t["D2_Akun"] == akun_name: debit += t["D2_Nominal"]
        if t["K1_Akun"] == akun_name: kredit += t["K1_Nominal"]
        if t["K2_Akun"] == akun_name: kredit += t["K2_Nominal"]
            
        if debit > 0 or kredit > 0:
            if saldo_normal_multiplier == 1:
                saldo_berjalan += (debit - kredit)
            else:
                saldo_berjalan += (kredit - debit)  
                
            ledger_entries.append({
                "Waktu": t["Waktu"],  
                "Deskripsi": t["Deskripsi"],
                "Debit": debit,  
                "Kredit": kredit,  
                "Saldo Akhir": saldo_berjalan,
                "Source_Sheet": t["Source_Sheet"],
                "Row_Index": t["Row_Index"],
                "Tipe_Entry": "Transaksi Normal",
                "SA_Detail_IDs": None
            })
    
    # --- PENGURUTAN ---
    def get_sort_key(entry):
        waktu = entry["Waktu"]
        if waktu == "Awal Periode":
            return (0, 0) # Prioritas 0 (paling atas)
        else:
            return (1, waktu) # Prioritas 1, diurutkan berdasarkan waktu (YYYY-MM-DD)

    ledger_entries.sort(key=get_sort_key) 
    
    return ledger_entries


def get_dashboard_kpis():
    """Menghitung KPI utama untuk ditampilkan di Dashboard."""
    
    saldo_kas = calculate_account_balance("Kas")
    total_penjualan = calculate_account_balance("Penjualan")
    laba_rugi = calculate_laba_rugi()[2]

    total_stok_ekor = 0
    total_stok_nilai = 0.0
    
    # Total Stok Ekor (Inventory)
    for akun in INVENTORY_ACCOUNT_CHOICES:
        kategori = akun.replace('Persediaan kambing ', '').title()
        ekor, avg_cost = get_last_average_cost(kategori)
        total_stok_ekor += ekor
        total_stok_nilai += (ekor * avg_cost)

    return saldo_kas, total_penjualan, laba_rugi, total_stok_ekor, total_stok_nilai

def calculate_laba_rugi():
    """Menghitung total pendapatan, total beban, dan laba/rugi bersih."""
    total_pendapatan = sum([calculate_account_balance(akun) for akun in AKUN_PENDAPATAN])
    total_beban = sum([calculate_account_balance(akun) for akun in AKUN_BEBAN])
    laba_rugi = total_pendapatan - total_beban
    return total_pendapatan, total_beban, laba_rugi

def generate_neraca_saldo_page():
    """Menghasilkan laporan Neraca Saldo."""
    st.title("🧾 Neraca Saldo (Trial Balance)")

    if st.button("⬅️ Kembali ke Dashboard"):
        st.session_state['page'] = 'dashboard'
        st.rerun()

    st.markdown("---")
    st.subheader("Neraca Saldo - Subuh Jaya Farm")
    st.markdown(f"**Per Tanggal:** {datetime.now().strftime('%d %B %Y')}")

    neraca_saldo_data = []
    total_debit_ns = 0.0
    total_kredit_ns = 0.0

    all_accounts = sorted(GENERAL_LEDGER_ACCOUNTS)

    for akun in all_accounts:
        saldo = calculate_account_balance(akun)
        debit = 0.0
        kredit = 0.0

        if abs(saldo) > 0.01:
            # Tentukan posisi saldo
            if akun in AKUN_ASET or akun in AKUN_BEBAN or akun == "Prive": # Saldo Normal Debit
                if saldo >= 0:
                    debit = saldo
                else:
                    kredit = abs(saldo)
            
            elif akun in AKUN_KEWAJIBAN or akun in AKUN_PENDAPATAN or akun == "Modal" or akun in AKUN_KONTRA: # Saldo Normal Kredit
                if saldo >= 0:
                    kredit = saldo
                else:
                    debit = abs(saldo)
            
            else: # Default (jika ada akun yang tidak terdaftar, anggap Saldo Normal Debit)
                if saldo >= 0:
                    debit = saldo
                else:
                    kredit = abs(saldo)

            if debit > 0 or kredit > 0:
                neraca_saldo_data.append({
                    "Keterangan": akun,
                    "Debit": debit,
                    "Kredit": kredit
                })
                total_debit_ns += debit
                total_kredit_ns += kredit
    
    df_ns = pd.DataFrame(neraca_saldo_data)

    if df_ns.empty:
        st.info("Tidak ada saldo yang tercatat untuk Neraca Saldo.")
        return

    df_for_download = df_ns.copy() 
    
    # Formatting untuk tampilan
    df_ns['Debit'] = df_ns['Debit'].apply(lambda x: f"Rp. {x:,.0f}")
    df_ns['Kredit'] = df_ns['Kredit'].apply(lambda x: f"Rp. {x:,.0f}")

    st.dataframe(df_ns, hide_index=True, use_container_width=True)

    st.markdown("---")
    
    # Tampilkan Total
    col_total1, col_total2, col_total3 = st.columns(3)
    with col_total1:
        st.markdown("**TOTAL**")
    with col_total2:
        st.markdown(f'**Rp. {total_debit_ns:,.0f}**')
    with col_total3:
        st.markdown(f'**Rp. {total_kredit_ns:,.0f}**')

    # Cek Keseimbangan
    if abs(total_debit_ns - total_kredit_ns) < 1.0:
        st.success("Neraca Saldo **SEIMBANG**. (Total Debit = Total Kredit)")
    else:
        st.error(f"PERINGATAN: Neraca Saldo **TIDAK SEIMBANG**! Selisih: Rp. {abs(total_debit_ns - total_kredit_ns):,.0f}")

    add_download_button(df_for_download, "Neraca_Saldo.xlsx", key_suffix="neraca_saldo")

def get_base64_of_file(path):
    """Membaca file dan mengembalikan base64 string-nya."""
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except FileNotFoundError:
        return None

def generate_laba_rugi_page():
    """Menghasilkan Laporan Laba Rugi Komprehensif."""
    st.title("📈 Laporan Laba Rugi Komprehensif")
    
    if st.button("⬅️ Kembali ke Dashboard"):
        st.session_state['page'] = 'dashboard'
        st.rerun()

    st.markdown("---")
    st.subheader("Laporan Laba Rugi - Subuh Jaya Farm")
    st.markdown(f"**Periode Sampai Tanggal:** {datetime.now().strftime('%d %B %Y')}")
    
    st.markdown(f'<div style="text-align: center; margin: 10px 0; border: 1px dashed #ccc; padding: 10px; background-color: #f9f9f9;">Infografis Laba Rugi (Revenue - Expenses)</div>', unsafe_allow_html=True)
    
    total_pendapatan, total_beban_gross, laba_rugi_gross = calculate_laba_rugi()
    
    lr_data = []
    
    # PENDAPATAN
    lr_data.append({"Keterangan": "PENDAPATAN", "Nominal": None})
    total_pendapatan_pos = 0.0
    for akun in AKUN_PENDAPATAN:
        saldo = calculate_account_balance(akun)
        if saldo > 0:
            lr_data.append({"Keterangan": f"    {akun}", "Nominal": saldo})
            total_pendapatan_pos += saldo
    
    # HPP
    hpp_val = calculate_account_balance("HPP")
    if hpp_val > 0:
        lr_data.append({"Keterangan": "Beban Pokok Penjualan (HPP)", "Nominal": -hpp_val})
        laba_bruto = total_pendapatan_pos - hpp_val
    else:
        laba_bruto = total_pendapatan_pos
        
    lr_data.append({"Keterangan": "LABA BRUTO", "Nominal": laba_bruto, "Total": "Subtotal"})
    lr_data.append({"Keterangan": "", "Nominal": None})

    # BEBAN OPERASIONAL
    lr_data.append({"Keterangan": "BEBAN OPERASIONAL", "Nominal": None})
    total_beban_ops = 0.0
    beban_ops_list = [a for a in AKUN_BEBAN if a != "HPP"]
    for akun in beban_ops_list:
        saldo = calculate_account_balance(akun)
        if saldo > 0:
            lr_data.append({"Keterangan": f"    {akun}", "Nominal": -saldo})
            total_beban_ops += saldo
    
    if total_beban_ops > 0:
        lr_data.append({"Keterangan": "TOTAL BEBAN OPERASIONAL", "Nominal": -total_beban_ops, "Total": "Subtotal"})
    
    # LABA BERSIH
    laba_bersih_final = laba_bruto - total_beban_ops
    lr_data.append({"Keterangan": "", "Nominal": None})
    lr_data.append({"Keterangan": "LABA (RUGI) BERSIH", "Nominal": laba_bersih_final, "Total": "Final"})
    
    df_lr = pd.DataFrame(lr_data)
    
    df_for_download = df_lr.copy()
    
    def format_lr(val, total_type):
        """Formatter untuk nilai Laba Rugi (Negatif = dalam kurung, Final = Bold)."""
        if val is None: return ""
        val = float(val)
        if total_type == "Final":
            return f'**Rp. {val:,.0f}**'
        if val < 0:
            return f'(Rp. {abs(val):,.0f})'
        return f'Rp. {val:,.0f}'

    df_lr['Nominal'] = df_lr.apply(lambda row: format_lr(row['Nominal'], row.get('Total', 'Normal')), axis=1)
    df_lr = df_lr.drop(columns=['Total'], errors='ignore')
    
    st.dataframe(df_lr, hide_index=True, use_container_width=True)

    add_download_button(df_for_download, "Laporan_Laba_Rugi.xlsx", key_suffix="laba_rugi")

    return laba_bersih_final

def generate_balance_sheet(title):
    """Menghasilkan Laporan Posisi Keuangan (Neraca)."""
    st.title(title)
    
    if st.button("⬅️ Kembali ke Dashboard"):
        st.session_state['page'] = 'dashboard'
        st.rerun()

    st.markdown("---")
    st.subheader(f"{title} - Subuh Jaya Farm")
    st.markdown(f"**Per Tanggal:** {datetime.now().strftime('%d %B %Y')}")
    st.caption("Aset harus seimbang dengan Kewajiban ditambah Ekuitas.")
    
    st.markdown("""
        <div style="text-align: center; margin: 10px 0; border: 1px dashed #ccc; padding: 10px; background-color: #f9f9f9;">
            Infografis Neraca/Laporan Posisi Keuangan (Aset = Liabilitas + Ekuitas)
        </div>
        """, unsafe_allow_html=True)
    
    laba_rugi = calculate_laba_rugi()[2]
    
    data = []
    total_aset = 0.0
    total_kewajiban = 0.0
    total_ekuitas_bersih = 0.0
    
    # --- ASET ---
    data.append({"Keterangan": "ASET", "Nominal": None, "Kategori": "A"})
    
    # ASET LANCAR
    data.append({"Keterangan": "Aset Lancar:", "Nominal": None, "Kategori": "A"})
    current_assets = [a for a in AKUN_ASET if a not in ["Bangunan kandang", "Kendaraan"]]
    total_lancar = 0.0
    for akun in current_assets:
        saldo = calculate_account_balance(akun)
        if saldo > 0:
            data.append({"Keterangan": f"    {akun}", "Nominal": saldo, "Kategori": "A"})
            total_lancar += saldo
    data.append({"Keterangan": "Total Aset Lancar", "Nominal": total_lancar, "Total_Type": "Subtotal", "Kategori": "A"})
    
    # ASET TIDAK LANCAR (TETAP)
    data.append({"Keterangan": "Aset Tidak Lancar:", "Nominal": None, "Kategori": "A"})
    total_tetap_bruto = 0.0
    
    for akun in ["Bangunan kandang", "Kendaraan"]:
        saldo = calculate_account_balance(akun)
        if saldo > 0:
            data.append({"Keterangan": f"    {akun} (Bruto)", "Nominal": saldo, "Kategori": "A"})
            total_tetap_bruto += saldo
            
    akumulasi_penyusutan = calculate_account_balance("Akumulasi penyusutan")
    if akumulasi_penyusutan > 0:
        data.append({"Keterangan": f"    (Akumulasi Penyusutan)", "Nominal": -akumulasi_penyusutan, "Kategori": "A"})
        total_tetap_bersih = total_tetap_bruto - akumulasi_penyusutan
    else:
        total_tetap_bersih = total_tetap_bruto
        
    data.append({"Keterangan": "Total Aset Tidak Lancar (Neto)", "Nominal": total_tetap_bersih, "Total_Type": "Subtotal", "Kategori": "A"})
    
    # TOTAL ASET
    total_aset = total_lancar + total_tetap_bersih
    data.append({"Keterangan": "TOTAL ASET", "Nominal": total_aset, "Total_Type": "Final", "Kategori": "A"})
    data.append({"Keterangan": "", "Nominal": None, "Kategori": None})
    
    # --- LIABILITAS DAN EKUITAS ---
    data.append({"Keterangan": "LIABILITAS DAN EKUITAS", "Nominal": None, "Kategori": "L+E"})
    
    # LIABILITAS (KEWAJIBAN)
    data.append({"Keterangan": "Liabilitas:", "Nominal": None, "Kategori": "L+E"})
    for akun in AKUN_KEWAJIBAN:
        saldo = calculate_account_balance(akun)
        if saldo > 0:
            data.append({"Keterangan": f"    {akun}", "Nominal": saldo, "Kategori": "L+E"})
            total_kewajiban += saldo
    data.append({"Keterangan": "Total Liabilitas", "Nominal": total_kewajiban, "Total_Type": "Subtotal", "Kategori": "L+E"})
    
    # EKUITAS
    data.append({"Keterangan": "Ekuitas:", "Nominal": None, "Kategori": "L+E"})
    
    modal_non_sa = calculate_account_balance_non_sa("Modal")
    saldo_awal_ekuitas_penyeimbang = calculate_account_balance("Modal") - modal_non_sa 

    if abs(saldo_awal_ekuitas_penyeimbang) > 0:
        data.append({"Keterangan": f"    Modal Awal", "Nominal": saldo_awal_ekuitas_penyeimbang, "Kategori": "L+E"})
        total_ekuitas_bersih += saldo_awal_ekuitas_penyeimbang
    
    if modal_non_sa > 0:
        data.append({"Keterangan": f"    Modal Disetor (Mutasi Lain)", "Nominal": modal_non_sa, "Kategori": "L+E"})
        total_ekuitas_bersih += modal_non_sa
        
    prive = calculate_account_balance("Prive")
    if prive > 0:
        data.append({"Keterangan": f"    (Prive)", "Nominal": -prive, "Kategori": "L+E"})
        total_ekuitas_bersih -= prive
        
    if laba_rugi != 0:
        data.append({"Keterangan": f"    Laba (Rugi) Periode Berjalan", "Nominal": laba_rugi, "Kategori": "L+E"})
        total_ekuitas_bersih += laba_rugi
        
    data.append({"Keterangan": "Total Ekuitas", "Nominal": total_ekuitas_bersih, "Total_Type": "Subtotal", "Kategori": "L+E"})
    
    # TOTAL LIABILITAS DAN EKUITAS
    total_liabilitas_ekuitas = total_kewajiban + total_ekuitas_bersih
    data.append({"Keterangan": "TOTAL LIABILITAS DAN EKUITAS", "Nominal": total_liabilitas_ekuitas, "Total_Type": "Final", "Kategori": "L+E"})
    
    df = pd.DataFrame(data)
    
    # Persiapan untuk download
    df_for_download = df.copy()
    df_for_download.insert(1, "ASET", df_for_download.apply(lambda row: row['Nominal'] if row['Kategori'] == 'A' else None, axis=1))
    df_for_download.insert(2, "LIABILITAS_EKUITAS", df_for_download.apply(lambda row: row['Nominal'] if row['Kategori'] == 'L+E' else None, axis=1))
    df_for_download = df_for_download.drop(columns=['Nominal', 'Total_Type', 'Kategori'])

    # Formatting untuk tampilan
    def format_bs(val, type):
        if val is None: return ""
        val = float(val)
        if type == "Final":
            return f'**Rp. {val:,.0f}**'
        if val < 0:
            return f'(Rp. {abs(val):,.0f})'
        return f'Rp. {val:,.0f}'

    df['Nominal'] = df.apply(lambda row: format_bs(row['Nominal'], row.get('Total_Type', 'Normal')), axis=1)
    
    df_aset = df[df['Kategori'] == 'A'].drop(columns=['Kategori', 'Total_Type'], errors='ignore')
    df_le = df[df['Kategori'] == 'L+E'].drop(columns=['Kategori', 'Total_Type'], errors='ignore')
    
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### ASET")
        st.dataframe(df_aset, hide_index=True, use_container_width=True)
    
    with col2:
        st.markdown("### LIABILITAS & EKUITAS")
        st.dataframe(df_le, hide_index=True, use_container_width=True)
    
    st.markdown("---")
    # Cek Keseimbangan Neraca
    if abs(total_aset - total_liabilitas_ekuitas) < 1.0:
        st.success(f"Laporan Seimbang: Total Aset (Rp. {total_aset:,.0f}) = Total L+E (Rp. {total_liabilitas_ekuitas:,.0f}).")
    else:
        st.error(f"PERINGATAN: Laporan Tidak Seimbang! Selisih: Rp. {abs(total_aset - total_liabilitas_ekuitas):,.0f}")
        
    st.markdown("---")
    add_download_button(df_for_download, "Laporan_Posisi_Keuangan.xlsx", key_suffix="posisi_keuangan")

def report_page(title, sheet_names):
    """Menghasilkan Jurnal Transaksi (Jurnal Umum, Pembelian, Penjualan)."""
    st.title(title)
    if st.button("⬅️ Kembali ke Dashboard"):
        st.session_state['page'] = 'dashboard'
        st.rerun()
        
    target_sheet = sheet_names[0]  
    data = get_formatted_journal_data(sheet_names)
    
    if data:
        st.subheader("Data Transaksi (Format Jurnal)")
        
        df = pd.DataFrame(data)
        
        df_for_delete = df[['Row_Index']].copy()
        df_for_display = df.drop(columns=['Row_Index', 'Sort_Key'])
        
        df_for_download = df_for_display.copy()
        
        # Formatting
        df_for_display['Debit'] = df_for_display['Debit'].apply(lambda x: f"Rp. {x:,.0f}")
        df_for_display['Kredit'] = df_for_display['Kredit'].apply(lambda x: f"Rp. {x:,.0f}")

        df_for_display.insert(0, 'Pilih', False)
        
        edited_df = st.data_editor(
            df_for_display,  
            column_order=["Pilih", "Waktu", "Keterangan", "Debit", "Kredit"],
            column_config={
                "Pilih": st.column_config.CheckboxColumn(default=False),
                "Waktu": st.column_config.TextColumn("Tanggal"), 
                "Keterangan": st.column_config.TextColumn("Keterangan"),
                "Debit": st.column_config.TextColumn("Debit", help="Nominal Debit"),
                "Kredit": st.column_config.TextColumn("Kredit", help="Nominal Kredit"),
            },
            hide_index=True,
            use_container_width=True,
            key=f'jurnal_data_editor_{target_sheet}'
        )
        
        add_download_button(df_for_download, f"Jurnal_{target_sheet}.xlsx", key_suffix=f"jurnal_{target_sheet}")
        st.markdown("---")

        selected_indices = edited_df[edited_df['Pilih']].index.tolist()
        
        rows_to_delete = []
        rows_to_delete_map = {}
        
        if selected_indices:
            # Dapatkan ID Jurnal (Row_Index) unik dari baris yang dipilih
            selected_ids = df_for_delete.iloc[selected_indices]['Row_Index'].unique().tolist()
            rows_to_delete = selected_ids
            rows_to_delete_map[target_sheet] = rows_to_delete

        total_trx_to_delete = len(rows_to_delete)
        
        if st.button(f"🗑️ Hapus {total_trx_to_delete} Transaksi Terpilih", key=f'delete_button_{target_sheet}', disabled=total_trx_to_delete == 0):
            
            deleted_count = execute_delete_transactions(rows_to_delete_map)
            
            if deleted_count > 0:
                st.success(f"{deleted_count} transaksi berhasil dihapus dari sheet {target_sheet}.")
                st.session_state.pop(f'jurnal_data_editor_{target_sheet}', None)
                st.rerun()
            else:
                st.warning("Tidak ada data yang dihapus.")

    else:
        st.info("Tidak ada data transaksi yang tercatat.")

def generate_general_ledger_report(akun_type):
    """Menghasilkan laporan Buku Besar (Umum, Piutang, atau Utang)."""
    if st.button("⬅️ Kembali ke Dashboard"):
        st.session_state['page'] = 'dashboard'
        st.rerun()
        
    st.markdown("---")
    
    transactions = load_transactions_data(MAIN_SHEETS)  
    
    # --- BB_PIUTANG (Kartu Piutang Usaha) ---
    if akun_type == 'BB_PIUTANG':
        report_title = "🤝 Kartu Piutang Usaha (Per Customer)"
        st.title(report_title)
        
        piutang_akun = "Piutang usaha"
        piutang_transactions = [
            t for t in transactions if 
            (t["Source_Sheet"] != "Saldo_Awal" and t.get("Customer") and (piutang_akun in [t["D1_Akun"], t["D2_Akun"], t["K1_Akun"], t["K2_Akun"]])) or
            (t["Source_Sheet"] == "Saldo_Awal" and t.get("Customer") and t["D1_Akun"] == piutang_akun)
        ]
        
        all_customers = {t["Customer"] for t in piutang_transactions if t.get("Customer")}

        if not all_customers:
            st.info("Tidak ada data Piutang Kredit atau Saldo Awal Piutang yang tercatat.")
            return

        selected_customer = st.selectbox("Pilih Customer", options=sorted(list(all_customers)))

        if selected_customer:
            st.subheader(f"Mutasi Piutang untuk: {selected_customer}")
            
            saldo_awal_piutang = 0.0
            saldo_awal_data = [t for t in transactions if t["Source_Sheet"] == "Saldo_Awal" and t["D1_Akun"] == piutang_akun and t.get("Customer") == selected_customer]
            if saldo_awal_data:
                saldo_awal_piutang = sum(t["D1_Nominal"] for t in saldo_awal_data)
                
            ledger_entries = []
            
            # 2. Tambahkan Saldo Awal
            if abs(saldo_awal_piutang) > 0.01:
                sa_ids_string = ",".join([str(t["id"]) for t in saldo_awal_data])
                ledger_entries.append({
                    "Waktu": "Awal Periode",  "Deskripsi": "Saldo Awal",
                    "Debit": saldo_awal_piutang,  "Kredit": 0.0,
                    "Saldo Akhir": saldo_awal_piutang,
                    "Source_Sheet": "Saldo_Awal", "Row_Index": -1, 
                    "Tipe_Entry": "Saldo Awal Total", "SA_Detail_IDs": sa_ids_string
                })
            
            saldo_berjalan = saldo_awal_piutang
            
            # 3. Tambahkan Transaksi Normal
            for t in transactions:
                if t["Source_Sheet"] == "Saldo_Awal": continue
                
                debit = 0.0
                kredit = 0.0
                
                if t["Customer"] == selected_customer:
                    if t["Source_Sheet"] == "Penjualan" and t["D1_Akun"] == piutang_akun:
                        debit = t["D1_Nominal"]
                        
                    elif t["Source_Sheet"] == "Lain-lain":
                        if t["K1_Akun"] == piutang_akun: kredit += t["K1_Nominal"]
                        if t["K2_Akun"] == piutang_akun: kredit += t["K2_Nominal"]
                        
                if debit > 0 or kredit > 0:
                    saldo_berjalan += (debit - kredit)
                        
                    ledger_entries.append({
                        "Waktu": t["Waktu"], "Deskripsi": t["Deskripsi"],
                        "Debit": debit, "Kredit": kredit, "Saldo Akhir": saldo_berjalan,
                        "Source_Sheet": t["Source_Sheet"],
                        "Row_Index": t["Row_Index"],
                        "Tipe_Entry": "Transaksi Normal", "SA_Detail_IDs": None
                        })
                    
            df_raw = pd.DataFrame(ledger_entries)
            df_raw.sort_values(by=['Waktu'], ascending=True, inplace=True)
            
            if not df_raw.empty:
                df_display, df_for_download, rows_to_delete_map, total_trx_to_delete = setup_data_editor_and_delete_logic(df_raw, f'ledger_editor_piutang_{selected_customer}', piutang_akun, is_subledger=True)
                
                add_download_button(df_for_download, f"Kartu_Piutang_{selected_customer}.xlsx", key_suffix=f"bb_piutang_{selected_customer}")
                st.markdown("---")

                if st.button(f"🗑️ Hapus {total_trx_to_delete} Transaksi Terpilih dari Kartu Piutang", key=f'delete_bb_button_piutang', disabled=total_trx_to_delete == 0):
                    deleted_count = execute_delete_transactions(rows_to_delete_map)
                    if deleted_count > 0:
                        st.success(f"{deleted_count} transaksi berhasil dihapus.")
                        st.session_state.pop(f'ledger_editor_piutang_{selected_customer}', None)  
                        st.rerun()
                    else:
                        st.warning("Tidak ada data yang dihapus.")
            else:
                st.info(f"Tidak ada mutasi yang tercatat untuk Customer {selected_customer}.")
            return

    # --- BB_UTANG (Kartu Utang Usaha) ---
    elif akun_type == 'BB_UTANG':
        report_title = "💸 Kartu Utang Usaha (Per Supplier)"
        st.title(report_title)
        
        utang_akun = "Utang usaha"
        utang_transactions = [
            t for t in transactions if 
            (t["Source_Sheet"] != "Saldo_Awal" and t.get("Customer") and (utang_akun in [t["D1_Akun"], t["D2_Akun"], t["K1_Akun"], t["K2_Akun"]])) or
            (t["Source_Sheet"] == "Saldo_Awal" and t.get("Customer") and t["K1_Akun"] == utang_akun)
        ]

        all_suppliers = {t["Customer"] for t in utang_transactions if t.get("Customer")}

        if not all_suppliers:
            st.info("Tidak ada data Utang Kredit atau Saldo Awal Utang yang tercatat.")
            return

        selected_supplier = st.selectbox("Pilih Supplier", options=sorted(list(all_suppliers)))

        if selected_supplier:
            st.subheader(f"Mutasi Utang untuk: {selected_supplier}")
            
            saldo_awal_utang = 0.0
            saldo_awal_data = [t for t in transactions if t["Source_Sheet"] == "Saldo_Awal" and t["K1_Akun"] == utang_akun and t.get("Customer") == selected_supplier]
            if saldo_awal_data:
                saldo_awal_utang = sum(t["K1_Nominal"] for t in saldo_awal_data)

            ledger_entries = []
            
            # 2. Tambahkan Saldo Awal
            if abs(saldo_awal_utang) > 0.01:
                sa_ids_string = ",".join([str(t["id"]) for t in saldo_awal_data])
                ledger_entries.append({
                    "Waktu": "Awal Periode",  "Deskripsi": "Saldo Awal",
                    "Debit": 0.0,  "Kredit": saldo_awal_utang,
                    "Saldo Akhir": saldo_awal_utang,
                    "Source_Sheet": "Saldo_Awal", "Row_Index": -1, 
                    "Tipe_Entry": "Saldo Awal Total", "SA_Detail_IDs": sa_ids_string
                })
            
            saldo_berjalan = saldo_awal_utang
            
            # 3. Tambahkan Transaksi Normal
            for t in transactions:
                if t["Source_Sheet"] == "Saldo_Awal": continue
                
                debit = 0.0
                kredit = 0.0
                
                if t["Customer"] == selected_supplier:
                    if t["Source_Sheet"] == "Pembelian" and t["K1_Akun"] == utang_akun:
                        kredit = t["K1_Nominal"]
                        
                    elif t["Source_Sheet"] == "Lain-lain":
                        if t["D1_Akun"] == utang_akun: debit += t["D1_Nominal"]
                        if t["D2_Akun"] == utang_akun: debit += t["D2_Nominal"]

                if debit > 0 or kredit > 0:
                    saldo_berjalan += (kredit - debit) 
                        
                    ledger_entries.append({
                        "Waktu": t["Waktu"], "Deskripsi": t["Deskripsi"],
                        "Debit": debit, "Kredit": kredit, "Saldo Akhir": saldo_berjalan,
                        "Source_Sheet": t["Source_Sheet"],
                        "Row_Index": t["Row_Index"],
                        "Tipe_Entry": "Transaksi Normal", "SA_Detail_IDs": None
                        })
                    
            df_raw = pd.DataFrame(ledger_entries)
            df_raw.sort_values(by=['Waktu'], ascending=True, inplace=True)
            
            if not df_raw.empty:
                df_display, df_for_download, rows_to_delete_map, total_trx_to_delete = setup_data_editor_and_delete_logic(df_raw, f'ledger_editor_utang_{selected_supplier}', utang_akun, is_subledger=True)
                
                add_download_button(df_for_download, f"Kartu_Utang_{selected_supplier}.xlsx", key_suffix=f"bb_utang_{selected_supplier}")
                st.markdown("---")
                
                if st.button(f"🗑️ Hapus {total_trx_to_delete} Transaksi Terpilih dari Kartu Utang", key=f'delete_bb_button_utang', disabled=total_trx_to_delete == 0):
                    deleted_count = execute_delete_transactions(rows_to_delete_map)
                    if deleted_count > 0:
                        st.success(f"{deleted_count} transaksi berhasil dihapus.")
                        st.session_state.pop(f'ledger_editor_utang_{selected_supplier}', None)  
                        st.rerun()
                    else:
                        st.warning("Tidak ada data yang dihapus.")
            else:
                st.info(f"Tidak ada mutasi yang tercatat untuk Supplier {selected_supplier}.")
            return

    # --- BB_UMUM (Buku Besar Umum) ---
    elif akun_type == 'BB_UMUM':
        st.title("📖 Buku Besar Umum")
        accounts_to_show = GENERAL_LEDGER_ACCOUNTS
        selected_account = st.selectbox("Pilih Akun Buku Besar", options=accounts_to_show)

        if selected_account:
            st.subheader(f"Mutasi Akun: {selected_account}")
            transactions = load_transactions_data(MAIN_SHEETS)  
            ledger_entries_raw = get_ledger_data_for_display(selected_account, transactions)
            
            if not ledger_entries_raw:
                st.info(f"Tidak ada mutasi yang tercatat untuk akun {selected_account}.")
                return

            df_raw = pd.DataFrame(ledger_entries_raw)
            
            if not df_raw.empty:
                
                df_display, df_for_download, rows_to_delete_map, total_trx_to_delete = setup_data_editor_and_delete_logic(df_raw, f'ledger_editor_{selected_account}', selected_account, is_subledger=False)
                
                add_download_button(df_for_download, f"Buku_Besar_{selected_account}.xlsx", key_suffix=f"bb_{selected_account}")
                st.markdown("---")

                if st.button(f"🗑️ Hapus {total_trx_to_delete} Transaksi Terpilih dari Buku Besar", key=f'delete_bb_button_{selected_account}', disabled=total_trx_to_delete == 0):
                    
                    deleted_count = execute_delete_transactions(rows_to_delete_map)
                    
                    if deleted_count > 0:
                        st.success(f"{deleted_count} transaksi berhasil dihapus.")
                        st.session_state.pop(f'ledger_editor_{selected_account}', None)  
                        st.rerun()
                    else:
                        st.warning("Tidak ada data yang dihapus.")

            else:
                st.info(f"Tidak ada mutasi yang tercatat untuk akun {selected_account}.")
    
    else:
        st.error("Tipe laporan tidak valid.")

def generate_detailed_inventory_card():
    """Menghasilkan Kartu Stok Persediaan Detail (Moving Average)."""
    st.title("📦 Kartu Stok Persediaan Detail (Moving Average)")
    
    if st.button("⬅️ Kembali ke Dashboard"):
        st.session_state['page'] = 'dashboard'
        st.rerun()

    st.markdown("---")
    
    db_path = st.session_state.get('db_path')
    if not db_path: 
        st.error("Database user tidak ditemukan.")
        return
        
    conn = get_db_connection(db_path)
    try:
        query = f"SELECT * FROM {INVENTORY_TABLE_NAME} ORDER BY Waktu"
        inventory_data_raw = pd.read_sql_query(query, conn)
    except Exception as e:
        st.error(f"Gagal memuat data Inventory: {e}")
        return
    finally:
        conn.close()
        
    inventory_data_raw.rename(columns={'id': 'Row_Index'}, inplace=True)  
        
    if inventory_data_raw.empty:
        st.info("Tidak ada data transaksi inventory yang tercatat.")
        add_download_button(inventory_data_raw, "Kartu_Stok_Inventory.xlsx", key_suffix="inventory_empty")
        return
        
    df = inventory_data_raw.copy()
    categories = df['Kategori'].unique()
    
    all_rows_to_delete = []
    
    for category in categories:
        st.subheader(f"Kartu Stok: Persediaan Kambing {category}")
        
        df_cat = df[df['Kategori'] == category].copy()
        
        saldo_ekor = 0
        saldo_total = 0.0
        inventory_card = []
        
        for index, row in df_cat.iterrows():
            waktu_str = str(row['Waktu']).split(' ')[0] 
            
            tipe = row['Tipe']
            jumlah = safe_int_conversion(row['Jumlah'])
            total = safe_float_conversion(row['Total'])
            harga = safe_float_conversion(row['Harga'])  
            row_index = row['Row_Index']  
            
            in_ekor, in_harga, in_total = 0, 0.0, 0.0
            out_ekor, out_harga, out_total = 0, 0.0, 0.0
            
            if tipe == "Pembelian" or tipe == "SALDO AWAL":
                in_ekor = jumlah
                in_harga = harga
                in_total = total
                
                saldo_ekor += in_ekor
                saldo_total += in_total
                
            elif tipe == "Penjualan":
                out_ekor = jumlah
                out_harga = harga
                out_total = total
                
                saldo_ekor -= out_ekor
                saldo_total -= out_total

            saldo_harga = saldo_total / saldo_ekor if saldo_ekor > 0 else 0.0
                
            inventory_card.append({
                "Tanggal": waktu_str, "Tipe": tipe,
                "IN Ekor": in_ekor, "IN Harga": in_harga, "IN Total": in_total,
                "OUT Ekor": out_ekor, "OUT Harga": out_harga, "OUT Total": out_total,
                "SALDO Ekor": saldo_ekor, "SALDO Harga Rata2": saldo_harga, "SALDO Total": saldo_total,
                "Row_Index": row_index
            })
        
        df_card = pd.DataFrame(inventory_card)
        
        cols_to_format = ["IN Harga", "IN Total", "OUT Harga", "OUT Total", "SALDO Harga Rata2", "SALDO Total"]
        
        df_for_download = df_card.drop(columns=['Row_Index'])
        
        df_display = df_card.copy()
        for col in cols_to_format:
            df_display[col] = df_display[col].apply(lambda x: f"Rp. {x:,.0f}")

        display_cols = [
            "Tanggal", "Tipe",
            "IN Ekor", "IN Harga", "IN Total",
            "OUT Ekor", "OUT Harga", "OUT Total",
            "SALDO Ekor", "SALDO Harga Rata2", "SALDO Total",
            "Row_Index"
        ]
        df_display = df_display[display_cols].copy()
        
        df_display.columns = [
            "Tanggal", "Tipe",
            "IN (ekor)", "IN (harga)", "IN (total)",
            "OUT (ekor)", "OUT (harga)", "OUT (total)",
            "Balance (ekor)", "Balance (harga rata-rata)", "Balance (total)",
            "Row_Index"
        ]
        
        is_saldo_awal_inv = (df_display['Tipe'] == 'SALDO AWAL')
        
        df_display_for_delete = df_display[['Row_Index']].copy()
        df_display = df_display.drop(columns=['Row_Index'])
        
        df_display.insert(0, 'Pilih', False)
        
        disabled_indices_list = is_saldo_awal_inv[is_saldo_awal_inv].index.tolist()
        disabled_status = [i in disabled_indices_list for i in df_display.index]
        
        edited_df_inv = st.data_editor(
            df_display,  
            column_config={"Pilih": st.column_config.CheckboxColumn(default=False)},
            disabled=disabled_status if len(disabled_status) == len(df_display) else None,
            hide_index=True,
            use_container_width=True,
            key=f'inventory_data_editor_{category}'
        )

        selected_indices = edited_df_inv[edited_df_inv['Pilih']].index.tolist()
        
        if selected_indices:
            selected_raw_ids = df_display_for_delete.iloc[selected_indices]['Row_Index'].tolist()
            all_rows_to_delete.extend(selected_raw_ids)
            
        st.markdown("---")
        
    rows_to_delete_unique = list(set(all_rows_to_delete))

    st.subheader("Opsi Unduh dan Hapus Data")
    
    if not inventory_data_raw.empty:
        add_download_button(inventory_data_raw.drop(columns=['Row_Index']), "Kartu_Stok_Semua_Data_Raw.xlsx", label="⬇️ Unduh Semua Data Inventory Raw (.xlsx)", key_suffix="all_inventory_cards_raw")
    

    if st.button(f"🗑️ Hapus {len(rows_to_delete_unique)} Baris Inventory Terpilih", key='delete_inventory_button', disabled=not rows_to_delete_unique):
        
        deleted_count = delete_rows_from_sheet("Inventory_Data", rows_to_delete_unique)
        
        if deleted_count > 0:
            st.warning("PERHATIAN: Hanya data *Inventory* yang dihapus. Anda mungkin perlu menghapus entri Jurnal terkait secara manual (via Jurnal Pembelian/Penjualan/Buku Besar).")
            st.success(f"{deleted_count} baris berhasil dihapus dari Kartu Stok Inventory.")
            # Hapus cache data editor untuk memaksa refresh
            st.session_state.pop('inventory_data_editor_jantan', None)
            st.session_state.pop('inventory_data_editor_betina', None)
            st.rerun()
        else:
            st.warning("Tidak ada data Inventory yang dihapus.")

# ======================================================================
# 7. FUNGSI UTILITY PENGHAPUSAN BUKU BESAR
# ======================================================================

def setup_data_editor_and_delete_logic(df_raw, editor_key, account_name, is_subledger=False):
    """Utility untuk membuat editor data dan menghitung entri yang akan dihapus."""
    df_display = df_raw.copy()
    
    is_saldo_awal_total = (df_display['Row_Index'] == -1)
    
    df_display_show = df_display[['Waktu', 'Deskripsi', 'Debit', 'Kredit', 'Saldo Akhir']].copy()
    df_for_download = df_display_show.copy()
    
    # Format mata uang untuk tampilan
    for col in ['Debit', 'Kredit', 'Saldo Akhir']:
        df_display_show[col] = df_display_show[col].apply(lambda x: f"Rp. {x:,.0f}" if abs(x) > 0.01 else "")

    df_display_show.insert(0, 'Pilih', False)
    
    # Non-aktifkan baris TOTAL Saldo Awal
    disabled_indices_list = is_saldo_awal_total[is_saldo_awal_total].index.tolist()
    disabled_status = [i in disabled_indices_list for i in df_display_show.index]

    edited_df = st.data_editor(
        df_display_show,  
        column_order=["Pilih", "Waktu", "Deskripsi", "Debit", "Kredit", "Saldo Akhir"],
        column_config={
            "Pilih": st.column_config.CheckboxColumn("Pilih", default=False),
            "Waktu": st.column_config.TextColumn("Tanggal"), 
            "Deskripsi": st.column_config.TextColumn("Deskripsi"),
            "Debit": st.column_config.TextColumn("Debit"),
            "Kredit": st.column_config.TextColumn("Kredit"),
            "Saldo Akhir": st.column_config.TextColumn("Saldo Akhir"),
        },
        disabled=disabled_status if len(disabled_status) == len(df_display_show) else None,
        hide_index=True,
        use_container_width=True,
        key=editor_key
    )
    
    selected_indices = edited_df[edited_df['Pilih']].index.tolist()
    
    rows_to_delete_map = {}
    total_trx_to_delete = 0

    for display_index in selected_indices:
        row_data = df_raw.iloc[display_index]
        
        if row_data['Row_Index'] == -1:
            # Baris Saldo Awal TOTAL dipilih
            sa_ids_to_delete = [int(id_str) for id_str in row_data['SA_Detail_IDs'].split(',') if id_str.strip()]
            
            if sa_ids_to_delete:
                if 'Saldo_Awal' not in rows_to_delete_map:
                    rows_to_delete_map['Saldo_Awal'] = []
                
                for id_sa in sa_ids_to_delete:
                    if id_sa not in rows_to_delete_map['Saldo_Awal']:
                        rows_to_delete_map['Saldo_Awal'].append(id_sa)
                        total_trx_to_delete += 1
            
        elif row_data['Row_Index'] > 0: 
            # Transaksi Normal
            sheet_name = row_data['Source_Sheet']
            row_id = int(row_data['Row_Index'])
            
            if sheet_name not in rows_to_delete_map:
                rows_to_delete_map[sheet_name] = []
            rows_to_delete_map[sheet_name].append(row_id)
            total_trx_to_delete += 1

    return edited_df, df_for_download, rows_to_delete_map, total_trx_to_delete

def execute_delete_transactions(rows_to_delete_map):
    """Utility untuk menjalankan logika penghapusan data, termasuk data inventory terkait."""
    deleted_count = 0
    
    for sheet_name, row_ids in rows_to_delete_map.items():
        
        if sheet_name in ["Penjualan", "Pembelian"]:
            # Dapatkan Waktu dari transaksi yang akan dihapus
            db_path = st.session_state.get('db_path')
            conn = get_db_connection(db_path)
            c = conn.cursor()
            
            placeholders = ', '.join(['?' for _ in row_ids])
            c.execute(f"SELECT Waktu FROM {TABLE_NAME} WHERE id IN ({placeholders})", row_ids)
            times_to_delete = {row['Waktu'] for row in c.fetchall()}
            conn.close()
            
            # Hapus data Inventory yang memiliki waktu yang sama
            conn_inv = get_db_connection(db_path)
            df_inv = pd.read_sql_query(f"SELECT id, Waktu FROM {INVENTORY_TABLE_NAME}", conn_inv)
            rows_inv_to_delete = df_inv[df_inv['Waktu'].isin(times_to_delete)]['id'].tolist()
            conn_inv.close()
            
            if rows_inv_to_delete:
                delete_rows_from_sheet("Inventory_Data", rows_inv_to_delete)
                st.info(f"Data Inventory terkait berhasil dihapus ({len(rows_inv_to_delete)} baris).")
                
            deleted_from_sheet = delete_rows_from_sheet(sheet_name, row_ids)
            deleted_count += deleted_from_sheet
        
        else: # Saldo_Awal atau Lain-lain
            deleted_from_sheet = delete_rows_from_sheet(sheet_name, row_ids)
            deleted_count += deleted_from_sheet
            
    return deleted_count

# ======================================================================
# 8. FUNGSI HALAMAN OTENTIKASI & TAMPILAN
# ======================================================================

def get_auth_page_styles(bg_base64, fallback_bg_color, input_bg_color, dark_header, text_color, button_color):
    """Mengembalikan string CSS untuk halaman login/register."""
    if bg_base64:
        bg_css = f"""
        .stApp {{
            background-image: url("data:image/jpeg;base64,{bg_base64}");
            background-size: cover;
            background-position: center;
            background-attachment: fixed;
        }}
        """
    else:
        bg_css = f""".stApp {{ background-color: {fallback_bg_color} !important; }}"""

    return f"""
        <style>
        {bg_css}
        section.main {{ display: flex; justify-content: center; align-items: center; min-height: 100vh; }}
        .block-container {{
            max-width: 400px !important; margin-top: 150px !important;
            background-color: rgba(255, 255, 255, 0.9); border-radius: 15px;
            padding: 30px; box-shadow: 0 5px 20px rgba(0, 0, 0, 0.4);
        }}
        .login-logo {{ width: 100px; margin: 0 auto 10px auto; display: block; border: 3px solid {dark_header}; border-radius: 50%; }}
        .login-title, .login-subtitle {{ color: {text_color} !important; font-weight: 700; text-align: center; }}
        [data-testid="stTextInput"] > div > div > input {{ background-color: {input_bg_color} !important; color: {text_color} !important; }}
        div.stButton button:not([key*="nav_to"]) {{ background-color: {button_color} !important; color: white !important; width: 100%; margin-top: 25px; }}
        div.stButton button[key*="nav_to"] {{ background-color: transparent !important; color: {button_color} !important; width: 100%; margin-top: 15px; border: none; }}
        </style>
    """

def register_page():
    """Halaman Pendaftaran User Baru."""
    logo_base64 = get_base64_of_file("kambing 3.png")  
    bg_base64 = get_base64_of_file("kambing5.jpg")  
    
    st.markdown(get_auth_page_styles(bg_base64, DARK_HEADER, "#F7F7F7", DARK_HEADER, TEXT_COLOR, BUTTON_COLOR), unsafe_allow_html=True)
    
    if logo_base64:
        st.markdown(f'<img src="data:image/png;base64,{logo_base64}" class="login-logo" />', unsafe_allow_html=True)
    
    st.markdown('<h2 class="login-title">SJF Digital</h2><h3 class="login-subtitle">Daftar Akun Baru</h3>', unsafe_allow_html=True)

    with st.form("register_form"):
        username = st.text_input("Username Baru")
        password = st.text_input("Password", type="password")
        confirm_password = st.text_input("Ulangi Password", type="password")
        submitted = st.form_submit_button("Daftar Akun")

        if submitted:
            if password != confirm_password:
                st.error("Password tidak cocok.")
            else:
                success, message = register_user(username, password)
                if success:
                    st.success(message)
                    st.session_state['page'] = 'login'
                    st.rerun()
                else:
                    st.error(message)
    
    if st.button("Sudah Punya Akun? Login", key="nav_to_login", help="Kembali ke halaman login"):
        st.session_state['page'] = 'login'
        st.rerun()

def login_page():
    """Halaman Login User."""
    logo_base64 = get_base64_of_file("kambing 3.png")  
    bg_base64 = get_base64_of_file("kambing5.jpg")  

    st.markdown(get_auth_page_styles(bg_base64, DARK_HEADER, "#F7F7F7", DARK_HEADER, TEXT_COLOR, BUTTON_COLOR), unsafe_allow_html=True)
    
    if logo_base64:
        st.markdown(f'<img src="data:image/png;base64,{logo_base64}" class="login-logo" />', unsafe_allow_html=True)
    
    st.markdown('<h2 class="login-title">SJF Digital</h2><h3 class="login-subtitle">Login Pengguna</h3>', unsafe_allow_html=True)

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Masuk Aplikasi")

        if submitted:
            conn_master = get_master_db_connection()
            c_master = conn_master.cursor()
            hashed_input = hash_password(password)
            
            c_master.execute("SELECT password_hash, db_path FROM users WHERE username = ?", (username,))
            user_data = c_master.fetchone()
            conn_master.close()

            if user_data and user_data['password_hash'] == hashed_input:
                st.session_state['logged_in'] = True
                st.session_state['username'] = username
                st.session_state['db_path'] = user_data['db_path']  
                st.success(f"Selamat datang, {username}!")
                st.session_state['page'] = 'dashboard'  
                st.rerun()
            else:
                st.error("Username atau Password salah!")
    
    if st.button("Belum Punya Akun? Daftar Sekarang", key="nav_to_register", help="Arahkan ke halaman pendaftaran"):
        st.session_state['page'] = 'register'
        st.rerun()

def render_metric_card(col, title, value, unit="", is_money=True):
    """Render kartu metrik di dashboard."""
    value = float(value)
    if is_money:
        value_str = f"Rp. {value:,.0f}"
        
    else:
        value_str = f"{value:,.0f} {unit}"
    
    with col:
        st.markdown(
            f"""
            <div class="metric-card">
                <small>{title}</small>
                <p>{value_str}</p>
            </div>
            """, unsafe_allow_html=True
        )


def dashboard_page():
    """Halaman Dashboard Utama Aplikasi."""
    
    kambing5_base64 = get_base64_of_file("kambing5.jpg")
    
    if not kambing5_base64:
        st.warning("Aset gambar 'kambing5.jpg' tidak ditemukan. Menggunakan warna latar belakang solid.")

    # Gaya CSS untuk Dashboard
    st.markdown(
        f"""
        <style>
        .stApp {{ background-color: {BG_PAGE}; }}
        .stSelectbox label, .stTextInput label, .stNumberInput label, 
        .stMetric label, h1, h2, h3, h4, h5, h6 {{
            color: {TEXT_COLOR} !important; font-weight: 600;
        }}
        [data-testid="stTextInput"] > div > div > input, 
        [data-testid="stNumberInput"] > div > div > input,
        .stSelectbox > div > button {{
            color: {TEXT_COLOR} !important; background-color: #F8F5F2;
        }}
        .main-banner {{ 
            background-image: url("data:image/png;base64,{kambing5_base64 or ''}"); 
            background-size: cover; background-position: center 25%; border-radius: 15px;
            height: 250px; position: relative; overflow: hidden; margin-bottom: 20px;
            box-shadow: 0 8px 25px rgba(0, 0, 0, 0.2);
        }}
        .banner-overlay {{ 
            background: linear-gradient(to bottom, rgba(62, 47, 36, 0.7) 0%, rgba(62, 47, 36, 0.1) 100%);
            padding: 20px 0; color: white; position: absolute; top: 0; left: 0; right: 0; text-align: center;
            font-weight: 700;
        }}
        .banner-overlay h1 {{ font-size: 2.5rem; letter-spacing: 2px; text-shadow: 2px 2px 5px rgba(0,0,0,0.7); }}
        .metric-card {{
            background-color: #FFFFFF; border-radius: 12px; padding: 20px; margin: 5px 0; 
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08); height: 100%;
            border-left: 5px solid {ACCENT_GOLD};
            width: 100%; box-sizing: border-box; 
        }}
        .metric-card p {{ font-size: 1.5rem; font-weight: 700; color: {DARK_HEADER}; margin-bottom: 5px; }}
        .metric-card small {{ color: #6c757d; }}
        
        div.stButton button {{
            background-color: #D9EAD3; color: {TEXT_COLOR};
            border: 1px solid #C5D8BF; border-radius: 10px;
            height: 90px; font-weight: 600;
            box-shadow: 0 3px 8px rgba(0, 0, 0, 0.1);
            transition: all 0.2s ease-out; margin: 5px 0;
            white-space: normal; line-height: 1.2; text-align: center;
        }}
        div.stButton > button:hover {{
            background-color: #C5D8BF;
            transform: translateY(-2px); 
            box-shadow: 0 6px 12px rgba(0, 0, 0, 0.15);
        }}
        header {{ visibility: hidden; }}
        footer {{ visibility: hidden; }}
        </style>
        """, unsafe_allow_html=True
    )

    # Header Banner
    st.markdown('<div class="main-banner">', unsafe_allow_html=True)
    st.markdown('<div class="banner-overlay"><h1>SUBUH JAYA FARM</h1><p>Digital Accounting System</p></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Info User dan Logout
    col_user, col_logout = st.columns([1, 0.15]) 
    with col_user:
        st.markdown(f"**Halo, {st.session_state.get('username', 'Pengguna')}!** Ini Ringkasan Bisnis Anda:")

    with col_logout:
        if st.button("🚪 Logout", key="logout_btn", use_container_width=True, help="Keluar dari aplikasi"):
            st.session_state.pop('logged_in')
            st.session_state.pop('username')
            st.session_state.pop('db_path')
            st.session_state['page'] = 'login'
            st.rerun()

    st.markdown("---")

    # KPI Sederhana
    saldo_kas, total_penjualan, laba_rugi, total_stok_ekor, total_stok_nilai = get_dashboard_kpis()
    
    st.subheader("📊 Key Financial Indicators (Current)")
    
    col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4) 
    
    render_metric_card(col_kpi1, "Saldo Kas", saldo_kas)
    render_metric_card(col_kpi2, "Total Penjualan (Kredit + Tunai)", total_penjualan)
    
    # Kartu Laba Rugi (dengan warna dinamis)
    with col_kpi3:
        border_color = '#28a745' if laba_rugi >= 0 else '#dc3545'
        text_color = '#28a745' if laba_rugi >= 0 else '#dc3545'
        value_str = f"Rp. {laba_rugi:,.0f}"
        
        st.markdown(
            f"""
            <div style="background-color: #FFFFFF; border-radius: 12px; padding: 20px; 
                        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08); height: 100%;
                        border-left: 5px solid {border_color};
                        width: 100%; box-sizing: border-box; margin: 5px 0;">
                <small style="color: #6c757d;">Laba Bersih</small>
                <p style="color: {text_color}; font-weight: 700; font-size: 1.5rem; margin-top: 5px; margin-bottom: 0;">{value_str}</p>
            </div>
            """, unsafe_allow_html=True
        )

    render_metric_card(col_kpi4, "Total Stok Kambing", total_stok_ekor, unit="Ekor", is_money=False)
    
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("---")
    
    # Toggle Form Input Transaksi
    st.markdown('<div style="text-align: center; margin-top: 10px;">', unsafe_allow_html=True)
    if 'transaction_type' not in st.session_state:
        st.session_state['transaction_type'] = None
    
    if st.button("➕ Buka Form Input Transaksi", key="toggle_form_btn", use_container_width=False, 
                    on_click=lambda: st.session_state.update({'show_form': not st.session_state.get('show_form', False)})):
        pass
    st.markdown('</div>', unsafe_allow_html=True)

    # --- FORM INPUT TRANSAKSI (HANYA DITAMPILKAN JIKA show_form=True) ---
    if st.session_state.get('show_form', False):
        
        st.markdown('<div id="form-container" class="shadow-deep" style="background-color: #FCFBF8; border-radius: 15px; padding: 30px; margin: 30px auto; max-width: 800px;">', unsafe_allow_html=True)
        st.subheader("**Pilih Jenis Transaksi**")
        
        transaction_options = {
            "Lain-lain / Jurnal Umum (Non Ternak)": "Lain-lain",
            "Pembelian Ternak": "Pembelian",
            "Penjualan Ternak": "Penjualan",
            "SALDO AWAL Buku Besar (Akun Non-Inventory)": "Saldo_Awal",
            "SALDO AWAL Inventory (Stok Kambing)": "Saldo_Awal_Inventory",
            "SALDO AWAL Utang & Piutang (Per Mitra)": "Saldo_Awal_Mitra"
        }
        
        if 'selected_transaction_category' not in st.session_state:
            st.session_state['selected_transaction_category'] = "Lain-lain"
            
        selected_key = st.selectbox(
            "Jenis Transaksi", 
            options=list(transaction_options.keys()), 
            key="trx_selector"
        )
        selected_category = transaction_options[selected_key]
        st.session_state['selected_transaction_category'] = selected_category
        
        st.markdown("---")
        
        existing_parties = get_customer_supplier_list()
        customer_options = ["(Pilih/Input Baru)"] + existing_parties

        # --- Saldo Awal Mitra ---
        if selected_category == "Saldo_Awal_Mitra":
            st.markdown("### 🤝 Input Saldo Awal Utang/Piutang (Per Mitra)")
            st.warning("Input ini akan membuat entri di Kartu Utang/Piutang. Akun penyeimbang Ekuitas Awal akan dihitung di Laporan Posisi Keuangan.")
            
            with st.form(key="form_saldo_awal_mitra"):
                
                cols_base = st.columns(3)
                with cols_base[0]: tanggal_input = st.date_input("Tanggal Saldo Awal", datetime.now().date(), key="sam_date") 
                with cols_base[1]: jenis_saldo = st.selectbox("Jenis Saldo", ["Utang", "Piutang"], key="sam_jenis")
                
                with cols_base[2]:  
                    selected_party = st.selectbox("Nama Mitra", customer_options, key="sam_cust_select", help="Pilih Mitra yang memiliki saldo awal.")
                
                final_customer = selected_party
                if selected_party == "(Pilih/Input Baru)":
                    final_customer = st.text_input("Input Nama Mitra Baru", key="sam_cust_new")
                
                st.markdown("---")
                
                cols_nominal = st.columns(2)
                with cols_nominal[0]:  
                    nominal = st.number_input(f"Jumlah Saldo ({jenis_saldo})", min_value=1.0, format="%.0f", key="sam_nominal")
                with cols_nominal[1]:
                    akun_mutasi = "Piutang usaha" if jenis_saldo == "Piutang" else "Utang usaha"
                    st.text(f"Akun Terkait: {akun_mutasi}")
                    st.caption(f"Posisi: {'Debit' if jenis_saldo == 'Piutang' else 'Kredit'} (Akun Lawan Kosong)")
                
                submitted = st.form_submit_button("SIMPAN SALDO AWAL UTANG/PIUTANG")
                
                if submitted:
                    if not final_customer or nominal <= 0:
                        st.error("Nama Mitra dan Jumlah Saldo harus diisi.")
                        return
                    
                    if jenis_saldo == "Piutang":
                        d1_akun = "Piutang usaha"; d1_nominal = nominal
                        k1_akun = None; k1_nominal = None
                    else:
                        d1_akun = None; d1_nominal = None
                        k1_akun = "Utang usaha"; k1_nominal = nominal
                        
                    try:
                        jurnal_row = [
                            str(tanggal_input), 
                            f"Saldo Awal {jenis_saldo} dari {final_customer}",  
                            f"SALDO AWAL {jenis_saldo.upper()}",
                            d1_akun, d1_nominal, None, None,  
                            k1_akun, k1_nominal, None, None,  
                            final_customer, None,
                            None, None,
                            nominal 
                        ]
                        append_row_to_sheet("Saldo_Awal", jurnal_row)
                        st.success(f"Saldo Awal {jenis_saldo} untuk '{final_customer}' berhasil disimpan! Nominal: Rp. {nominal:,.0f}.")
                        st.session_state['show_form'] = False
                        st.rerun()
                    except Exception as e:
                        st.error(f"Gagal menyimpan data Saldo Awal Mitra: {e}")

        # --- Saldo Awal Inventory ---
        elif selected_category == "Saldo_Awal_Inventory":
            st.markdown("### 🐑 Input Saldo Awal Inventory (Stok Kambing)")
            st.warning("Input ini akan membuat entri di Kartu Stok dan Buku Besar. Akun penyeimbang Ekuitas Awal akan dihitung di Laporan Posisi Keuangan.")
            
            with st.form(key="form_saldo_awal_inventory"):
                
                cols_base = st.columns(3)
                with cols_base[0]: tanggal_input = st.date_input("Tanggal Saldo Awal", datetime.now().date(), key="sai_date") 
                with cols_base[1]: deskripsi = st.text_input("Deskripsi", value="Pencatatan Saldo Awal Inventory", key="sai_desc")
                with cols_base[2]: kategori_akun = st.selectbox("Jenis Kambing", INVENTORY_ACCOUNT_CHOICES, key="sai_kat")
                
                cols_inv = st.columns(2)
                with cols_inv[0]: jumlah = st.number_input("Jumlah (Ekor)", min_value=1, format="%.0f", key="sai_jumlah")
                with cols_inv[1]: harga_satuan = st.number_input("Harga Satuan Beli Awal (Cost Unit)", min_value=1.0, format="%.0f", key="sai_harga")
                
                total_nominal = harga_satuan * jumlah
                kategori_bb = kategori_akun.replace('Persediaan kambing ', '').title()
                
                st.metric(label="Total Nilai Inventory", value=f"Rp. {total_nominal:,.0f}")
                
                submitted = st.form_submit_button("SIMPAN SALDO AWAL INVENTORY")
                
                if submitted:
                    if total_nominal <= 0 or jumlah <= 0:
                        st.error("Harga Satuan dan Jumlah Ekor harus lebih dari nol (0).")
                        return
                        
                    try:
                        waktu_format_db = str(tanggal_input) 
                        
                        # 1. Simpan ke tabel Inventory
                        append_row_to_sheet("Inventory_Data",  
                            [waktu_format_db, "SALDO AWAL", kategori_bb, harga_satuan, jumlah, total_nominal]
                        )
                        
                        # 2. Simpan ke tabel Jurnal (Source_Sheet: Saldo_Awal)
                        jurnal_row = [
                            waktu_format_db, deskripsi, "SALDO AWAL INVENTORY",
                            kategori_akun, total_nominal, None, None,
                            None, None, None, None, 
                            None, kategori_bb,
                            harga_satuan,  
                            jumlah,
                            total_nominal  
                        ]
                        append_row_to_sheet("Saldo_Awal", jurnal_row)
                        
                        st.success(f"Saldo Awal Inventory '{kategori_akun}' berhasil disimpan! Total: Rp. {total_nominal:,.0f}.")
                        st.session_state['show_form'] = False
                        st.rerun()
                    except Exception as e:
                        st.error(f"Gagal menyimpan data Saldo Awal Inventory: {e}")

        # --- Saldo Awal Akun ---
        elif selected_category == "Saldo_Awal":
            st.markdown("### 💰 Input Saldo Awal Akun (Hanya Debit ATAU Kredit)")
            st.warning("Masukkan entri per akun. Isi Nominal di sisi Debit *atau* Kredit (sesuai sifat normal akun).")
            
            with st.form(key="form_saldo_awal"):
                
                cols_base = st.columns(3)
                with cols_base[0]: tanggal_input = st.date_input("Tanggal Saldo Awal", datetime.now().date(), key="sa_date") 
                with cols_base[1]: deskripsi = st.text_input("Deskripsi Transaksi", value="Pencatatan Saldo Awal", key="sa_desc")
                with cols_base[2]: st.empty()  
                
                st.markdown("##### Pilih Akun dan Nominal (Isi HANYA Debit ATAU Kredit)")

                cols_acc = st.columns(4)
                
                debit_1_index = DEBIT_CHOICES.index("Kas") if "Kas" in DEBIT_CHOICES else 0
                kredit_1_index = DEBIT_CHOICES.index("Modal") if "Modal" in DEBIT_CHOICES else 0

                with cols_acc[0]:
                    d1_akun = st.selectbox("Akun Debit (Dipilih Jika Saldo Normal Debit)", DEBIT_CHOICES, key="sa_d1a", index=debit_1_index)
                with cols_acc[1]:
                    d1_nominal = st.number_input("Nominal Debit", min_value=0.0, format="%.0f", key="sa_d1n")
                
                with cols_acc[2]:
                    k1_akun = st.selectbox("Akun Kredit (Dipilih Jika Saldo Normal Kredit)", DEBIT_CHOICES, key="sa_k1a", index=kredit_1_index)
                with cols_acc[3]:
                    k1_nominal = st.number_input("Nominal Kredit", min_value=0.0, format="%.0f", key="sa_k1n")
                
                submitted = st.form_submit_button("SIMPAN SALDO AWAL")
                
                if submitted:
                    
                    is_debit_filled = d1_nominal > 0; is_kredit_filled = k1_nominal > 0
                    
                    if is_debit_filled and is_kredit_filled: 
                        st.error("Anda harus mengisi Nominal di sisi Debit *atau* Kredit, tidak keduanya.")
                        return
                    if not is_debit_filled and not is_kredit_filled: 
                        st.error("Anda harus mengisi Nominal di sisi Debit *atau* Kredit.")
                        return
                        
                    if is_debit_filled:
                        final_d_akun = d1_akun; final_d_nominal = d1_nominal
                        final_k_akun = "Modal"; final_k_nominal = d1_nominal
                        total_nominal = d1_nominal
                    else:
                        final_d_akun = "Modal"; final_d_nominal = k1_nominal 
                        final_k_akun = k1_akun; final_k_nominal = k1_nominal
                        total_nominal = k1_nominal
                    
                    # *Khusus* jika akun yang dipilih adalah Modal, tidak perlu penyeimbang ke Modal lagi
                    if d1_akun == "Modal" and is_debit_filled:
                        final_k_akun = None; final_k_nominal = None
                    if k1_akun == "Modal" and is_kredit_filled:
                        final_d_akun = None; final_d_nominal = None


                    try:
                        waktu_format_db = str(tanggal_input) 
                        jurnal_row = [
                            waktu_format_db, deskripsi, "SALDO AWAL",
                            final_d_akun, final_d_nominal, None, None,
                            final_k_akun, final_k_nominal, None, None,
                            None, None,
                            None, None,
                            total_nominal
                        ]
                        append_row_to_sheet("Saldo_Awal", jurnal_row)
                        
                        if is_debit_filled:
                            st.success(f"Saldo Awal Debit Akun '{d1_akun}' berhasil disimpan! Nominal: Rp. {total_nominal:,.0f}")
                        else:
                            st.success(f"Saldo Awal Kredit Akun '{k1_akun}' berhasil disimpan! Nominal: Rp. {total_nominal:,.0f}")
                            
                        st.session_state['show_form'] = False
                        st.rerun()
                    except Exception as e:
                        st.error(f"Gagal menyimpan data Saldo Awal: {e}")

        # --- Jurnal Umum ---
        elif selected_category == "Lain-lain":
            st.markdown("### 📒 Input Transaksi Lain-lain / Jurnal Umum (Sederhana)")
            st.warning("Nominal Jurnal dihitung otomatis dari (Harga Satuan).")
            
            with st.form(key="form_lain_lain"):
                
                cols_base = st.columns(3)
                with cols_base[0]: deskripsi = st.text_input("Deskripsi Transaksi", key="ll_desc")
                with cols_base[1]: tanggal_input = st.date_input("Tanggal Transaksi", datetime.now().date(), key="ll_date") 
                
                with cols_base[2]:  
                    selected_party = st.selectbox("Customer/Supplier", customer_options, key="ll_cust_select", help="Pilih jika transaksi ini terkait Utang/Piutang/Pihak Ketiga.")
                
                final_customer = selected_party
                if selected_party == "(Pilih/Input Baru)":
                    final_customer = st.text_input("Input Nama Customer/Supplier Baru (Opsional)", key="ll_cust_new")

                st.markdown("##### Pilih Akun")

                cols_acc = st.columns(2)
                debit_1_index = DEBIT_CHOICES.index("Kas") if "Kas" in DEBIT_CHOICES else 0
                kredit_1_index = DEBIT_CHOICES.index("Utang usaha") if "Utang usaha" in DEBIT_CHOICES else 0

                with cols_acc[0]: d1_akun = st.selectbox("Debit Akun", DEBIT_CHOICES, key="ll_d1a", index=debit_1_index)
                with cols_acc[1]: k1_akun = st.selectbox("Kredit Akun", DEBIT_CHOICES, key="ll_k1a", index=kredit_1_index)
                
                st.markdown("---")
                st.markdown("##### Nominal Transaksi")

                harga_satuan = st.number_input("Harga Satuan/Nilai Transaksi", min_value=0.0, format="%.0f", key="ll_harga_satuan")
                
                total_nominal = harga_satuan
                jumlah_satuan = 1.0  
                
                st.metric(label="Total Nominal Jurnal (Debit = Kredit)", value=f"Rp. {total_nominal:,.0f}")
                
                submitted = st.form_submit_button("SIMPAN TRANSAKSI JURNAL UMUM")

                if submitted:
                    
                    if not deskripsi: st.error("Deskripsi harus diisi."); return
                    if total_nominal <= 0: st.error("Total Nominal Transaksi harus lebih besar dari nol."); return

                    customer_to_save = final_customer if final_customer != "(Pilih/Input Baru)" and final_customer else None
                    
                    try:
                        waktu_format_db = str(tanggal_input) 
                        jurnal_row = [
                            waktu_format_db, deskripsi, "Jurnal Umum",
                            d1_akun, total_nominal, None, None,
                            k1_akun, total_nominal, None, None,
                            customer_to_save, None,
                            harga_satuan,  
                            jumlah_satuan,
                            total_nominal
                        ]
                        
                        append_row_to_sheet("Lain-lain", jurnal_row)
                        
                        st.success(f"Transaksi Jurnal Umum '{deskripsi}' berhasil disimpan! Total: Rp. {total_nominal:,.0f}")
                        st.session_state['show_form'] = False
                        st.rerun()
                    except Exception as e:
                        st.error(f"Gagal menyimpan data Lain-lain: {e}")

        # --- Pembelian Ternak ---
        elif selected_category == "Pembelian":
            st.markdown("### 🛒 Input Transaksi Pembelian Ternak")
            
            with st.form(key="form_pembelian"):
                
                cols_base = st.columns(3)
                with cols_base[0]: deskripsi = st.text_input("Deskripsi Pembelian", key="beli_desc")
                with cols_base[1]: tanggal_input = st.date_input("Tanggal Transaksi", datetime.now().date(), key="beli_date") 
                with cols_base[2]: metode = st.selectbox("Metode Pembayaran", ["Tunai", "Kredit"], key="beli_metode")

                cols_meta = st.columns(2)
                with cols_meta[0]: customer = st.text_input("Supplier (Wajib diisi untuk Kartu Utang)", key="beli_cust", help="Input manual nama Supplier untuk dicatat di Kartu Utang (jika Kredit).")
                with cols_meta[1]: kategori_akun = st.selectbox("Kategori Ternak", INVENTORY_ACCOUNT_CHOICES, key="beli_kat")
                
                cols_inv = st.columns(2)
                with cols_inv[0]: harga_satuan = st.number_input("Harga Satuan Beli (Cost Unit)", min_value=0.0, format="%.0f", key="beli_harga")  
                with cols_inv[1]: jumlah = st.number_input("Jumlah (Ekor)", min_value=0.0, format="%.0f", key="beli_jumlah")
                
                total_nominal = harga_satuan * jumlah
                kategori_bb = kategori_akun.replace('Persediaan kambing ', '').title()
                
                st.metric(label="Total Nilai Pembelian (Bruto)", value=f"Rp. {total_nominal:,.0f}")

                submitted = st.form_submit_button("SIMPAN TRANSAKSI PEMBELIAN")

                if submitted:
                    if total_nominal <= 0 or jumlah <= 0: st.error("Harga Satuan Beli dan Jumlah Ekor harus > 0."); return
                    if metode == "Kredit" and not customer: st.error("Pembelian Kredit WAJIB mengisi Supplier."); return
                    
                    try:
                        waktu_format_db = str(tanggal_input) 
                        d1_akun_auto = kategori_akun
                        k1_akun_auto = "Kas" if metode == "Tunai" else "Utang usaha"
                        
                        jurnal_row = [
                            waktu_format_db, deskripsi, metode,
                            d1_akun_auto, total_nominal, None, None,
                            k1_akun_auto, total_nominal, None, None,
                            customer, kategori_bb,
                            harga_satuan,  
                            jumlah,  
                            total_nominal
                        ]
                        append_row_to_sheet("Pembelian", jurnal_row)
                        
                        append_row_to_sheet("Inventory_Data", [jurnal_row[0], "Pembelian", kategori_bb, harga_satuan, jumlah, total_nominal])
                        
                        st.success(f"Transaksi Pembelian '{deskripsi}' berhasil disimpan! Total: Rp. {total_nominal:,.0f}")
                        st.session_state['show_form'] = False
                        st.rerun()
                    except Exception as e:
                        st.error(f"Gagal menyimpan data Pembelian: {e}")

        # --- Penjualan Ternak ---
        elif selected_category == "Penjualan":
            st.markdown("### 💰 Input Transaksi Penjualan Ternak")

            def update_kategori_state():
                st.session_state['jual_kategori_akun'] = st.session_state['temp_jual_kat']

            kategori_akun_selected = st.selectbox(
                "Kategori Ternak",  
                INVENTORY_ACCOUNT_CHOICES,  
                key="temp_jual_kat",  
                on_change=update_kategori_state,
                index=INVENTORY_ACCOUNT_CHOICES.index(st.session_state['jual_kategori_akun'])
            )
            st.session_state['jual_kategori_akun'] = kategori_akun_selected
            
            kategori_akun = st.session_state['jual_kategori_akun']
            kategori_bb = kategori_akun.replace('Persediaan kambing ', '').title()  
            saldo_ekor_last, avg_cost_last = get_last_average_cost(kategori_bb)

            with st.form(key="form_penjualan"):
                
                cols_base = st.columns(3)
                with cols_base[0]: deskripsi = st.text_input("Deskripsi Penjualan", key="jual_desc")
                with cols_base[1]: tanggal_input = st.date_input("Tanggal Transaksi", datetime.now().date(), key="jual_date") 
                with cols_base[2]: metode = st.selectbox("Metode Pembayaran", ["Tunai", "Kredit"], key="jual_metode")

                cols_meta = st.columns(2)
                with cols_meta[0]: customer = st.text_input("Customer (Wajib diisi untuk Kartu Piutang)", key="jual_cust", help="Input manual nama Customer untuk dicatat di Kartu Piutang (jika Kredit).")
                with cols_meta[1]:  
                    st.text("Kategori yang Dipilih:")
                    st.caption(kategori_akun)

                cols_inv = st.columns(3)
                with cols_inv[0]:  
                    harga_satuan_jual = st.number_input("Harga Satuan Jual", min_value=0.0, format="%.0f", key="jual_harga")  
                with cols_inv[1]:  
                    jumlah = st.number_input("Jumlah (Ekor)", min_value=0.0, format="%.0f", key="jual_jumlah")
                with cols_inv[2]:
                    st.metric(label="HPP Otomatis/Unit", value=f"Rp. {avg_cost_last:,.0f}")
                    st.caption(f"Saldo Ekor: {saldo_ekor_last:,.0f}")
                
                total_penjualan_bruto = harga_satuan_jual * jumlah
                total_hpp_calc = avg_cost_last * jumlah  

                st.metric(label="Total Penjualan Bruto", value=f"Rp. {total_penjualan_bruto:,.0f}")
                st.metric(label="Total HPP Otomatis", value=f"Rp. {total_hpp_calc:,.0f}")
                
                submitted = st.form_submit_button("SIMPAN TRANSAKSI PENJUALan")

                if submitted:
                    if total_penjualan_bruto <= 0 or jumlah <= 0: 
                        st.error("Harga Satuan Jual dan Jumlah Ekor harus lebih besar dari 0.")
                        return
                    
                    if metode == "Kredit" and not customer: 
                        st.error("Penjualan Kredit WAJIB mengisi Customer.")
                        return
                        
                    if saldo_ekor_last < jumlah: 
                        st.error(f"Ekor Penjualan ({jumlah:,.0f}) melebihi Saldo Ekor ({saldo_ekor_last:,.0f}). Transaksi Dibatalkan.")
                        return
                    
                    try:
                        waktu_format_db = str(tanggal_input) 
                        
                        d1_akun_jual = "Piutang usaha" if metode == "Kredit" else "Kas"  
                        k1_akun_jual = "Penjualan"
                        d1_nominal_jual = total_penjualan_bruto
                        k1_nominal_jual = total_penjualan_bruto
                        d2_akun_hpp = "HPP"
                        k2_akun_hpp = kategori_akun

                        jurnal_row = [
                            waktu_format_db, deskripsi, metode,
                            d1_akun_jual, d1_nominal_jual, d2_akun_hpp, total_hpp_calc,
                            k1_akun_jual, k1_nominal_jual, k2_akun_hpp, total_hpp_calc,
                            customer, kategori_bb,
                            harga_satuan_jual,  
                            jumlah,  
                            total_penjualan_bruto
                        ]
                        append_row_to_sheet("Penjualan", jurnal_row)
                        
                        append_row_to_sheet("Inventory_Data", [jurnal_row[0], "Penjualan", kategori_bb, avg_cost_last, jumlah, total_hpp_calc])
                        
                        st.success(f"Transaksi Penjualan '{deskripsi}' berhasil disimpan! Total Jual: Rp. {total_penjualan_bruto:,.0f}. HPP: Rp. {total_hpp_calc:,.0f}")
                        st.session_state['show_form'] = False
                        st.rerun()
                    except Exception as e:
                        st.error(f"Gagal menyimpan data Penjualan: {e}")
        
        st.markdown('</div>', unsafe_allow_html=True)

    
    # --- NAVIGASI CEPAT LAPORAN ---
    st.markdown('<h3 style="text-align: center; margin-top: 20px;">Navigasi Cepat Laporan</h3>', unsafe_allow_html=True)
    
    st.markdown("#### 1. Jurnal dan Buku Besar")
    nav_items_jurnal_bb = [
        ("📒 Jurnal Umum", 'jurnal_umum'), 
        ("🛒 Jurnal Beli", 'jurnal_pembelian'), 
        ("💰 Jurnal Jual", 'jurnal_penjualan'),
        ("📖 Buku Besar (Umum)", 'buku_besar'),
    ]
    cols_nav_jurnal = st.columns(len(nav_items_jurnal_bb))
    for i, (icon_text, page_key) in enumerate(nav_items_jurnal_bb):
        with cols_nav_jurnal[i]:
            if st.button(icon_text, key=f"nav_{page_key}", use_container_width=True):
                st.session_state['page'] = page_key
                st.rerun()

    st.markdown("<br>")
    
    st.markdown("#### 2. Kartu Detail (Sub-Ledger)")
    nav_items_sub_ledger = [
        ("🤝 Kartu Piutang", 'bb_piutang'), 
        ("💸 Kartu Utang", 'bb_utang'), 
        ("📦 Kartu Stok Inventory", 'inventory'),
    ]
    cols_nav_sub = st.columns(len(nav_items_sub_ledger))
    for i, (icon_text, page_key) in enumerate(nav_items_sub_ledger):
        with cols_nav_sub[i]:
            if st.button(icon_text, key=f"nav_{page_key}", use_container_width=True):
                st.session_state['page'] = page_key
                st.rerun()
    
    st.markdown("<br>")

    st.markdown("#### 3. Laporan Keuangan Utama")
    nav_items_laporan = [
        ("🧾 Neraca Saldo", 'neraca_saldo'),  
        ("📈 Laba Rugi", 'laba_rugi'),  
        ("📊 Lap. Pos. Keuangan", 'posisi_keuangan'),
    ]
    cols_nav_laporan = st.columns(len(nav_items_laporan))
    for i, (icon_text, page_key) in enumerate(nav_items_laporan):
        with cols_nav_laporan[i]:
            if st.button(icon_text, key=f"nav_{page_key}", use_container_width=True):
                st.session_state['page'] = page_key
                st.rerun()


def main():
    """Fungsi Utama Aplikasi Streamlit."""
    
    # Inisialisasi Session State
    if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
    if 'page' not in st.session_state: st.session_state['page'] = 'login'  
    if 'show_form' not in st.session_state: st.session_state['show_form'] = False
    if 'laba_rugi_cache' not in st.session_state: st.session_state['laba_rugi_cache'] = 0.0
    if 'db_path' not in st.session_state: st.session_state['db_path'] = None  
    
    global INVENTORY_ACCOUNT_CHOICES 
    INVENTORY_ACCOUNT_CHOICES = ["Persediaan kambing jantan", "Persediaan kambing betina"]
    if 'jual_kategori_akun' not in st.session_state:
        st.session_state['jual_kategori_akun'] = INVENTORY_ACCOUNT_CHOICES[0]

    # Routing Halaman
    if not st.session_state['logged_in']:
        if st.session_state['page'] == 'register':
            register_page() 
        else:
            login_page() 
    else:
        if st.session_state['page'] == 'dashboard':
            dashboard_page()
        elif st.session_state['page'] == 'jurnal_umum':
            report_page("📒 Jurnal Umum (Lain-lain)", ["Lain-lain"])  
        elif st.session_state['page'] == 'jurnal_pembelian':
            report_page("🛒 Jurnal Pembelian", ["Pembelian"])
        elif st.session_state['page'] == 'jurnal_penjualan':
            report_page("💰 Jurnal Penjualan", ["Penjualan"])
            
        elif st.session_state['page'] == 'buku_besar':
            generate_general_ledger_report('BB_UMUM')
        elif st.session_state['page'] == 'bb_utang':
            generate_general_ledger_report('BB_UTANG')
        elif st.session_state['page'] == 'bb_piutang':
            generate_general_ledger_report('BB_PIUTANG')

        elif st.session_state['page'] == 'inventory':
            generate_detailed_inventory_card()

        elif st.session_state['page'] == 'neraca_saldo':
            generate_neraca_saldo_page()
            
        elif st.session_state['page'] == 'laba_rugi':
            laba_rugi_result = generate_laba_rugi_page()
            st.session_state['laba_rugi_cache'] = laba_rugi_result
        elif st.session_state['page'] == 'neraca' or st.session_state['page'] == 'posisi_keuangan':
            generate_balance_sheet("📊 Laporan Posisi Keuangan")
        elif st.session_state['page'] == 'saldo_awal':
             st.session_state['show_form'] = True
             st.session_state['selected_transaction_category'] = "Saldo_Awal"
             st.session_state['page'] = 'dashboard'
             st.rerun()


if __name__ == "__main__":
    st.set_page_config(layout="wide", page_title="SJF Digital Accounting")
    setup_master_database()
    main()
