import streamlit as st
import requests
import json
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="CSI Huawei - Investigação", page_icon="🕵️", layout="wide")

# --- CONEXÃO GOOGLE SHEETS ---
def conectar_gsheets():
    try:
        if "gcp_service_account" not in st.secrets: return None
        creds_dict = dict(st.secrets["gcp_service_account"])
        SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        credentials = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        client = gspread.authorize(credentials)
        return client.open("Banco de Dados Eon").sheet1
    except: return None

def carregar_clientes():
    sheet = conectar_gsheets()
    if not sheet: return {}
    try:
        rows = sheet.get_all_records()
        db = {}
        for row in rows:
            if "Nome_Conta" in row and row["Nome_Conta"]:
                db[str(row["Nome_Conta"]).upper().strip()] = {"id": str(row["ID_Inversor"]), "marca": row["Marca"]}
        return db
    except: return {}

# --- CREDENCIAIS ---
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
st.title("🕵️ CSI: Investigação da Curva")

db = carregar_clientes()
col1, col2 = st.columns(2)
nome_input = col1.text_input("Cliente:", "JOAO DA SILVA").upper().strip()
data_alvo = col2.date_input("Dia do Erro (ex: 01/01):", datetime(2026, 1, 1))

usina = db.get(nome_input)

if usina:
    st.info(f"Analisando: **{nome_input}** (ID: `{usina['id']}`)")
    
    if st.button("🔬 ABRIR PACOTE DE DADOS"):
        token = get_token()
        headers = {"xsrf-token": token}
        
        collect_time_day = int(datetime(data_alvo.year, data_alvo.month, data_alvo.day).timestamp() * 1000)
        
        st.write(f"Baixando curva do dia {data_alvo.strftime('%d/%m/%Y')}...")
        
        # 1. TENTA PEGAR A CURVA
        try:
            r = requests.post(f"{CREDS['huawei']['url']}/getKpiStationDay", json={"stationCodes": usina['id'], "collectTime": collect_time_day}, headers=headers)
            dados_curva = r.json().get("data", [])
            
            if dados_curva:
                qtd = len(dados_curva)
                st.success(f"📦 Encontrados {qtd} pacotes de dados neste dia!")
                
                # PEGA O PACOTE DO MEIO-DIA (Para garantir que tem sol e geração)
                # Se pegar o primeiro (00:00) vai ser zero mesmo.
                indice_meio_dia = int(qtd / 2) 
                pacote_amostra = dados_curva[indice_meio_dia]
                
                hora_pacote = datetime.fromtimestamp(pacote_amostra["collectTime"]/1000).strftime('%H:%M:%S')
                
                st.divider()
                st.markdown(f"### 🧬 Conteúdo do Pacote das {hora_pacote}")
                st.markdown("Procure abaixo qualquer campo que tenha valor maior que 0:")
                
                # EXIBE O MAPA DE DADOS CRU
                mapa = pacote_amostra.get("dataItemMap", {})
                st.json(mapa)
                
                # DICA AUTOMÁTICA
                candidatos = []
                for k, v in mapa.items():
                    try:
                        if float(v) > 0:
                            candidatos.append(f"{k} = {v}")
                    except: pass
                
                if candidatos:
                    st.success("💡 Campos com valor encontrados:")
                    for c in candidatos:
                        st.code(c)
                else:
                    st.warning("⚠️ Todos os campos neste pacote estão zerados ou nulos.")
                    
            else:
                st.error("A API retornou lista vazia [] para a curva deste dia.")
                
        except Exception as e: st.error(str(e))

else:
    st.warning("Cliente não encontrado.")
