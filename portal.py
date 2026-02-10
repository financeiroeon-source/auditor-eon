import streamlit as st
import requests
import json
import hashlib
import hmac
import base64
from datetime import datetime, timezone, timedelta
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Portal Eon Solar - DIAGNÓSTICO", page_icon="🕵️", layout="wide")

# --- CONEXÃO GOOGLE SHEETS ---
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

def conectar_gsheets():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        credentials = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        client = gspread.authorize(credentials)
        return client.open("Banco de Dados Eon").sheet1
    except: return None

def carregar_clientes():
    try:
        sheet = conectar_gsheets()
        if not sheet: return {}
        rows = sheet.get_all_records()
        db = {}
        for row in rows:
            if "Nome_Conta" in row and row["Nome_Conta"]:
                db[row["Nome_Conta"]] = {
                    "id": str(row["ID_Inversor"]),
                    "marca": row["Marca"],
                    "nome": row["Nome_Inversor"]
                }
        return db
    except: return {}

def salvar_cliente(nome_conta, dados_usina):
    try:
        sheet = conectar_gsheets()
        if not sheet: return False
        sheet.append_row([nome_conta, str(dados_usina["id"]), dados_usina["marca"], dados_usina["nome"]])
        return True
    except: return False

# --- CREDENCIAIS ---
CREDS = {
    "huawei": {
        "user": "Eon.solar",
        "pass": "eonsolar2024",
        "url": "https://la5.fusionsolar.huawei.com/thirdData"
    },
    "solis": {
        "key_id": "1300386381676798170",
        "key_secret": "70b315e18b914435abe726846e950eab",
        "url": "https://www.soliscloud.com:13333"
    }
}

# --- AUTH ---
def get_huawei_token():
    try:
        r = requests.post(f"{CREDS['huawei']['url']}/login", json={"userName": CREDS['huawei']['user'], "systemCode": CREDS['huawei']['pass']}, timeout=10)
        if r.json().get("success"): return r.headers.get("xsrf-token")
    except: pass
    return None

def get_solis_auth(resource, body):
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
    content_md5 = base64.b64encode(hashlib.md5(body.encode('utf-8')).digest()).decode('utf-8')
    key = CREDS['solis']['key_secret'].encode('utf-8')
    sign_str = f"POST\n{content_md5}\napplication/json\n{now}\n{resource}"
    signature = hmac.new(key, sign_str.encode('utf-8'), hashlib.sha1).digest()
    auth = f"API {CREDS['solis']['key_id']}:{base64.b64encode(signature).decode('utf-8')}"
    return {"Authorization": auth, "Content-MD5": content_md5, "Content-Type": "application/json", "Date": now}

# --- LISTAGEM ---
@st.cache_data(ttl=600)
def listar_todas_usinas():
    lista = []
    try:
        token = get_huawei_token()
        if token:
            r = requests.post(f"{CREDS['huawei']['url']}/getStationList", json={"pageNo": 1, "pageSize": 100}, headers={"xsrf-token": token}, timeout=10)
            d = r.json().get("data", [])
            estacoes = d if isinstance(d, list) else d.get("list", [])
            for s in estacoes:
                lista.append({"id": str(s.get("stationCode")), "nome": s.get("stationName"), "marca": "Huawei", "display": f"Huawei | {s.get('stationName')}"})
    except: pass
    try:
        body = json.dumps({"pageNo": 1, "pageSize": 100})
        headers = get_solis_auth("/v1/api/userStationList", body)
        r = requests.post(f"{CREDS['solis']['url']}/v1/api/userStationList", data=body, headers=headers, timeout=10)
        d = r.json().get("data", {}).get("page", {}).get("records", [])
        for s in d:
            lista.append({"id": str(s.get("id")), "nome": s.get("stationName"), "marca": "Solis", "display": f"Solis | {s.get('stationName')}"})
    except: pass
    return lista

# --- INTERFACE ---
st.sidebar.title("🕵️ Eon Raio-X")
menu = st.sidebar.radio("Menu", ["🏠 Home", "🧬 Diagnóstico de Dados"])

if menu == "🏠 Home":
    st.title("Modo de Diagnóstico")
    st.info("Use a aba 'Diagnóstico de Dados' para investigar a API da Huawei.")
    db = carregar_clientes()
    st.metric("Clientes", len(db))

elif menu == "🧬 Diagnóstico de Dados":
    st.title("Raio-X da Huawei")
    
    nome_input = st.text_input("Cliente:", "JOAO DA SILVA").upper().strip()
    db = carregar_clientes()
    usina = db.get(nome_input)
    
    if usina:
        st.success(f"Alvo: {usina['nome']} (ID: {usina['id']})")
        
        c1, c2 = st.columns(2)
        dt_inicio = c1.date_input("Início", value=datetime(2026, 1, 1))
        dt_fim = c2.date_input("Fim", value=datetime(2026, 1, 10)) # Pega só 10 dias para ser rápido
        
        if st.button("🔍 INICIAR VARREDURA PROFUNDA"):
            token = get_huawei_token()
            headers = {"xsrf-token": token}
            
            # 1. LISTA DEVICES
            st.write("--- 1. Dispositivos Encontrados ---")
            dev_ids = []
            try:
                r = requests.post(f"{CREDS['huawei']['url']}/getDevList", json={"stationCodes": usina['id']}, headers=headers)
                devs = r.json().get("data", [])
                st.json(devs)
                dev_ids = [d.get("id") for d in devs]
            except Exception as e: st.error(f"Erro lista dev: {e}")
            
            # 2. PUXA DADOS BRUTOS DE CADA DEVICE
            st.write("--- 2. Matriz de Dados (Dia a Dia) ---")
            
            # Prepara a tabela mestre
            tabela_mestre = []
            
            # Varre dias
            dias = pd.date_range(dt_inicio, dt_fim)
            
            progress = st.progress(0)
            
            for i, dia in enumerate(dias):
                collect_time = int(datetime(dia.year, dia.month, 1).timestamp() * 1000)
                
                # Para cada dispositivo...
                for dev_id in dev_ids:
                    try:
                        # Tenta endpoint de Device
                        payload = {"devIds": str(dev_id), "collectTime": collect_time}
                        r = requests.post(f"{CREDS['huawei']['url']}/getDevKpiMonth", json=payload, headers=headers)
                        dados = r.json().get("data", [])
                        
                        # Acha o dia específico na lista do mês
                        dia_kpi = next((d for d in dados if datetime.fromtimestamp(d.get("collectTime",0)/1000).date() == dia.date()), None)
                        
                        if dia_kpi:
                            mapa = dia_kpi.get("dataItemMap", {})
                            linha = {
                                "Data": dia.strftime("%d/%m"),
                                "Device ID": dev_id,
                                "daily_energy_yield": mapa.get("daily_energy_yield"),
                                "daily_yield": mapa.get("daily_yield"),
                                "product_power": mapa.get("product_power"),
                                "inverter_power": mapa.get("inverter_power"),
                                "active_power": mapa.get("active_power"),
                                "cumulative_energy": mapa.get("cumulative_energy")
                            }
                            tabela_mestre.append(linha)
                    except: pass
                progress.progress((i + 1) / len(dias))
                
            # MOSTRA A TABELA FINAL
            if tabela_mestre:
                df = pd.DataFrame(tabela_mestre)
                st.dataframe(df, use_container_width=True)
                st.warning("⚠️ Olhe a tabela acima. Qual coluna tem valores que parecem geração diária (ex: 20, 40, 60)?")
            else:
                st.error("Nenhum dado retornado pela API para esses dias.")

    else:
        st.warning("Cliente não encontrado ou não vinculado.")
        opcoes = listar_todas_usinas()
        nomes = [u["display"] for u in opcoes]
        esc = st.selectbox("Vincular:", ["Selecione..."] + nomes)
        if esc != "Selecione..." and st.button("Salvar"):
            obj = next(u for u in opcoes if u["display"] == esc)
            salvar_cliente(nome_input, obj)
            st.rerun()
