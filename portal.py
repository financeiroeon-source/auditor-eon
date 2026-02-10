import streamlit as st
import requests
import json
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Microscópio Final", page_icon="🔬", layout="wide")

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
st.title("🔬 Microscópio: A Busca pelos 62.20 kWh")

db = carregar_clientes()
col1, col2 = st.columns(2)
nome_input = col1.text_input("Cliente:", "JOAO DA SILVA").upper().strip()
data_alvo = col2.date_input("Data Alvo (Dia do Erro):", datetime(2026, 1, 1))

usina = db.get(nome_input)

if usina:
    st.info(f"Analisando: **{nome_input}** (ID: `{usina['id']}`)")
    
    if st.button("🔎 INVESTIGAR A FUNDO"):
        token = get_token()
        headers = {"xsrf-token": token}
        
        # 1. VISÃO GERAL DO MÊS (Para ver se só o dia 1 está errado)
        st.subheader("1. Tabela Mensal (Janeiro)")
        data_segura = data_alvo.replace(day=15) # Pede dia 15 para pegar o mês certo
        collect_time_month = int(datetime(data_segura.year, data_segura.month, data_segura.day).timestamp() * 1000)
        
        try:
            r = requests.post(f"{CREDS['huawei']['url']}/getKpiStationMonth", json={"stationCodes": usina['id'], "collectTime": collect_time_month}, headers=headers)
            dados_mes = r.json().get("data", [])
            
            tabela = []
            for item in dados_mes:
                dt = datetime.fromtimestamp(item["collectTime"]/1000).strftime("%d/%m")
                val = item.get("dataItemMap", {}).get("inverter_power", 0)
                tabela.append({"Dia": dt, "Valor (kWh)": val})
            
            df = pd.DataFrame(tabela)
            # Mostra os primeiros 5 dias para vermos o contraste
            st.dataframe(df.head(10), use_container_width=True)
            
        except Exception as e: st.error(str(e))
        
        # 2. TENTATIVA DE RESGATE (INTEGRAL DA CURVA)
        st.subheader(f"2. Tentativa de Resgate: Reconstruir o dia {data_alvo.strftime('%d/%m')}")
        st.caption("Baixando potência a cada 5 minutos para somar manualmente...")
        
        collect_time_day = int(datetime(data_alvo.year, data_alvo.month, data_alvo.day).timestamp() * 1000)
        
        try:
            # Pede a curva intra-dia (getKpiStationDay)
            r = requests.post(f"{CREDS['huawei']['url']}/getKpiStationDay", json={"stationCodes": usina['id'], "collectTime": collect_time_day}, headers=headers)
            dados_curva = r.json().get("data", [])
            
            if dados_curva:
                pontos = []
                soma_potencias = 0
                contagem = 0
                
                for p in dados_curva:
                    # active_power geralmente vem em kW
                    pot = p.get("dataItemMap", {}).get("active_power", 0)
                    if pot is not None:
                        soma_potencias += float(pot)
                        contagem += 1
                        pontos.append(float(pot))
                
                if contagem > 0:
                    # Cálculo: Soma das potências (kW) / 12 (pois são amostras de 5 min = 12 por hora)
                    estimativa = soma_potencias / 12
                    
                    c1, c2 = st.columns(2)
                    c1.metric("Pontos de Curva Encontrados", contagem)
                    c2.metric("Geração Recalculada", f"{estimativa:.2f} kWh")
                    
                    st.line_chart(pontos)
                    
                    if abs(estimativa - 62.20) < 5:
                        st.success("🎉 SUCESSO! Conseguimos reconstruir o valor através da curva!")
                    else:
                        st.warning(f"O valor recalculado ({estimativa:.2f}) ainda está diferente de 62.20. A amostragem pode não ser de 5 min.")
                else:
                    st.error("A curva de potência veio zerada.")
            else:
                st.error("A API não entregou a curva intra-dia para esta data (Lista Vazia).")
                st.write("JSON Retornado:", r.json())
                
        except Exception as e: st.error(str(e))

else:
    st.warning("Cliente não encontrado.")
