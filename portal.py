import streamlit as st
import requests
import json
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Microscópio Huawei v2.1", page_icon="🔬", layout="wide")

# --- CONEXÃO GOOGLE SHEETS (CORRIGIDA) ---
def conectar_gsheets():
    try:
        # Verifica se o segredo existe
        if "gcp_service_account" not in st.secrets:
            st.error("❌ Erro: Segredo 'gcp_service_account' não encontrado no Secrets.")
            return None
            
        creds_dict = dict(st.secrets["gcp_service_account"])
        
        # AQUI ESTAVA O PROBLEMA: ADICIONAMOS O ESCOPO "DRIVE"
        SCOPES = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        
        credentials = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        client = gspread.authorize(credentials)
        sheet = client.open("Banco de Dados Eon").sheet1
        return sheet
    except Exception as e:
        st.error(f"❌ Erro ao conectar na Planilha: {e}")
        return None

def carregar_clientes():
    sheet = conectar_gsheets()
    if not sheet: return {}
    
    try:
        rows = sheet.get_all_records()
        db = {}
        for row in rows:
            if "Nome_Conta" in row and row["Nome_Conta"]:
                # Normaliza para maiúsculas e remove espaços extras
                chave = str(row["Nome_Conta"]).upper().strip()
                db[chave] = {"id": str(row["ID_Inversor"]), "marca": row["Marca"]}
        return db
    except Exception as e:
        st.error(f"❌ Erro ao ler linhas: {e}")
        return {}

# --- CREDENCIAIS HUAWEI ---
CREDS = {
    "huawei": {
        "user": "Eon.solar",
        "pass": "eonsolar2024",
        "url": "https://la5.fusionsolar.huawei.com/thirdData"
    }
}

def get_token():
    try:
        r = requests.post(f"{CREDS['huawei']['url']}/login", json={"userName": CREDS['huawei']['user'], "systemCode": CREDS['huawei']['pass']}, timeout=10)
        if r.json().get("success"): return r.headers.get("xsrf-token")
    except: pass
    return None

# --- INTERFACE ---
st.title("🔬 Microscópio de Dados v2.1")

# 1. DIAGNÓSTICO DA PLANILHA
st.markdown("### 1. Status do Banco de Dados")
db = carregar_clientes()

if len(db) > 0:
    st.success(f"✅ Banco conectado! {len(db)} clientes carregados.")
    st.caption(f"Exemplos na lista: {', '.join(list(db.keys())[:3])}...")
else:
    st.error("⚠️ O Banco de Dados está vazio ou não conectou.")
    st.stop() 

st.divider()

# 2. SELEÇÃO DO CLIENTE
col_nome, col_data = st.columns(2)
nome_input = col_nome.text_input("Nome do Cliente:", "JOAO DA SILVA").upper().strip()
data_alvo = col_data.date_input("Data para Investigar:", datetime.today())

# Verifica se o cliente existe
usina = db.get(nome_input)

if usina:
    st.info(f"🎯 Cliente Encontrado: **{nome_input}** | ID Usina: `{usina['id']}`")
    
    if st.button("🔎 EXAMINAR DADOS BRUTOS (CLIQUE AQUI)"):
        
        st.write("--- INICIANDO VARREDURA ---")
        token = get_token()
        if not token:
            st.error("❌ Falha de Login na Huawei API.")
            st.stop()
            
        headers = {"xsrf-token": token}
        collect_time = int(datetime(data_alvo.year, data_alvo.month, data_alvo.day).timestamp() * 1000)
        
        # A) LISTA DISPOSITIVOS
        st.markdown("#### A) Dispositivos na Usina")
        ids_dispositivos = []
        try:
            r = requests.post(f"{CREDS['huawei']['url']}/getDevList", json={"stationCodes": usina['id']}, headers=headers)
            devs = r.json().get("data", [])
            st.json(devs)
            ids_dispositivos = [d.get("id") for d in devs]
        except Exception as e: st.error(f"Erro DevList: {e}")

        # B) DADOS DA ESTAÇÃO
        st.markdown(f"#### B) Dados da Estação (Dia {data_alvo.strftime('%d/%m')})")
        try:
            payload = {"stationCodes": usina['id'], "collectTime": collect_time}
            r = requests.post(f"{CREDS['huawei']['url']}/getKpiStationDay", json=payload, headers=headers)
            st.json(r.json())
        except Exception as e: st.error(f"Erro StationDay: {e}")

        # C) DADOS DOS DISPOSITIVOS
        st.markdown("#### C) Dados dos Dispositivos (Tentativa de achar Curva)")
        if not ids_dispositivos:
            st.warning("Nenhum dispositivo encontrado para varrer.")
        
        for dev_id in ids_dispositivos:
            with st.expander(f"Dispositivo ID: {dev_id}"):
                try:
                    payload = {"devIds": str(dev_id), "collectTime": collect_time}
                    r = requests.post(f"{CREDS['huawei']['url']}/getDevKpiDay", json=payload, headers=headers)
                    dados = r.json().get("data", [])
                    if dados:
                        st.success("TEM DADOS! 👇")
                        st.json(dados[:5]) # Mostra os 5 primeiros pontos
                    else:
                        st.warning("Lista vazia [] (Sem curva neste dia)")
                except Exception as e: st.error(str(e))

else:
    st.warning(f"❌ Cliente '{nome_input}' não encontrado na lista carregada.")
    with st.expander("Ver lista de nomes disponíveis no sistema"):
        st.write(list(db.keys()))
