import streamlit as st
import requests
import json
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- CONFIGURAÇÃO SIMPLES ---
st.set_page_config(page_title="Microscópio Huawei", page_icon="🔬", layout="wide")

# --- CONEXÃO GOOGLE SHEETS ---
def conectar_gsheets():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        credentials = Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets"])
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
                db[row["Nome_Conta"]] = {"id": str(row["ID_Inversor"]), "marca": row["Marca"]}
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

# --- LOGIN HUAWEI ---
def get_token():
    try:
        r = requests.post(f"{CREDS['huawei']['url']}/login", json={"userName": CREDS['huawei']['user'], "systemCode": CREDS['huawei']['pass']}, timeout=10)
        if r.json().get("success"): return r.headers.get("xsrf-token")
    except Exception as e:
        st.error(f"Erro login: {e}")
    return None

# --- INTERFACE ---
st.sidebar.title("🔬 Microscópio")
menu = st.sidebar.radio("Menu", ["🏠 Home", "🕵️ Investigar Dia"])

if menu == "🏠 Home":
    st.title("Ferramenta de Diagnóstico Puro")
    st.info("Use o menu ao lado para investigar o que a API está realmente entregando.")

elif menu == "🕵️ Investigar Dia":
    st.title("Raio-X do Dia")
    
    nome = st.text_input("Nome do Cliente:", "JOAO DA SILVA").upper().strip()
    data_alvo = st.date_input("Data para Investigar:", datetime.today())
    
    db = carregar_clientes()
    usina = db.get(nome)
    
    if usina and st.button("🔎 EXAMINAR DADOS BRUTOS"):
        st.write(f"Conectando na usina ID: `{usina['id']}`...")
        
        token = get_token()
        if not token:
            st.error("Falha no Login Huawei")
            st.stop()
            
        headers = {"xsrf-token": token}
        
        # 1. QUEM SÃO OS APARELHOS?
        st.subheader("1. Lista de Dispositivos (getDevList)")
        try:
            r = requests.post(f"{CREDS['huawei']['url']}/getDevList", json={"stationCodes": usina['id']}, headers=headers)
            devs = r.json().get("data", [])
            st.json(devs) # MOSTRA O JSON PURO DOS APARELHOS
            
            ids_dispositivos = [d.get("id") for d in devs]
        except Exception as e: st.error(str(e))

        # 2. O QUE A ESTAÇÃO DIZ DO DIA? (Curva de Potência)
        st.subheader("2. Curva da Estação (getKpiStationDay)")
        st.caption("Aqui deveria ter a potência (active_power) a cada 5 min.")
        collect_time = int(datetime(data_alvo.year, data_alvo.month, data_alvo.day).timestamp() * 1000)
        try:
            payload = {"stationCodes": usina['id'], "collectTime": collect_time}
            r = requests.post(f"{CREDS['huawei']['url']}/getKpiStationDay", json=payload, headers=headers)
            dados = r.json()
            st.json(dados) # MOSTRA O JSON PURO
        except Exception as e: st.error(str(e))

        # 3. O QUE CADA APARELHO DIZ DO DIA? (Curva de Potência)
        st.subheader("3. Curva por Dispositivo (getDevKpiDay)")
        for dev_id in ids_dispositivos:
            st.markdown(f"**Dispositivo ID: {dev_id}**")
            try:
                payload = {"devIds": str(dev_id), "collectTime": collect_time}
                r = requests.post(f"{CREDS['huawei']['url']}/getDevKpiDay", json=payload, headers=headers)
                dados = r.json()
                # Mostra só os 3 primeiros registros para não poluir, ou tudo se for pouco
                lista_dados = dados.get("data", [])
                if lista_dados:
                    st.success(f"Encontrados {len(lista_dados)} pontos de dados!")
                    st.json(lista_dados[:3]) # Mostra amostra
                else:
                    st.warning("Lista vazia []")
            except Exception as e: st.error(str(e))

        # 4. TOTAIS DO DIA (Mês/Ano)
        st.subheader("4. Totais Diários (getKpiStationMonth)")
        st.caption("Aqui procuramos o valor total do dia (daily_yield).")
        collect_time_month = int(datetime(data_alvo.year, data_alvo.month, 1).timestamp() * 1000)
        try:
            payload = {"stationCodes": usina['id'], "collectTime": collect_time_month}
            r = requests.post(f"{CREDS['huawei']['url']}/getKpiStationMonth", json=payload, headers=headers)
            dados = r.json().get("data", [])
            # Tenta achar o dia específico
            dia_encontrado = next((d for d in dados if datetime.fromtimestamp(d.get("collectTime")/1000).day == data_alvo.day), None)
            if dia_encontrado:
                st.json(dia_encontrado)
            else:
                st.warning("Dia não encontrado na lista do mês.")
                st.json(dados) # Mostra tudo pra ver o que tem
        except Exception as e: st.error(str(e))
