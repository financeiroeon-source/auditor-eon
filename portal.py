import streamlit as st
import requests
import json
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Microscópio v3.0 (Corrigido)", page_icon="🔬", layout="wide")

# --- CONEXÃO GOOGLE SHEETS ---
def conectar_gsheets():
    try:
        if "gcp_service_account" not in st.secrets:
            st.error("❌ Erro: Segredo 'gcp_service_account' ausente.")
            return None
        creds_dict = dict(st.secrets["gcp_service_account"])
        SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        credentials = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        client = gspread.authorize(credentials)
        return client.open("Banco de Dados Eon").sheet1
    except Exception as e:
        st.error(f"❌ Erro Planilha: {e}")
        return None

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
st.title("🔬 Microscópio v3.0 (Busca Precisa)")

db = carregar_clientes()
if not db: st.stop()

col1, col2 = st.columns(2)
nome_input = col1.text_input("Cliente:", "JOAO DA SILVA").upper().strip()
data_alvo = col2.date_input("Data Exata:", datetime(2026, 1, 1))

usina = db.get(nome_input)

if usina:
    st.success(f"Alvo: **{nome_input}** (ID: `{usina['id']}`)")
    
    if st.button("🔎 BUSCAR DADO EXATO"):
        token = get_token()
        if not token: st.error("Erro Login Huawei"); st.stop()
        headers = {"xsrf-token": token}
        
        # TRUQUE: Pede o dia 15 do mês para garantir que venha o mês certo
        # Se pedirmos dia 1, as vezes vem o mês anterior.
        data_segura = data_alvo.replace(day=15)
        collect_time = int(datetime(data_segura.year, data_segura.month, data_segura.day).timestamp() * 1000)
        
        st.write(f"⏳ Consultando tabela mensal de {data_alvo.strftime('%B/%Y')}...")
        
        try:
            # Usa getKpiStationMonth que provou ser o que retorna a lista diária
            payload = {"stationCodes": usina['id'], "collectTime": collect_time}
            r = requests.post(f"{CREDS['huawei']['url']}/getKpiStationMonth", json=payload, headers=headers)
            dados = r.json().get("data", [])
            
            # PROCURA O DIA EXATO NA LISTA
            encontrado = None
            lista_tabela = []
            
            for item in dados:
                ms = item.get("collectTime", 0)
                data_item = datetime.fromtimestamp(ms / 1000).date()
                
                # Extrai valores candidatos
                mapa = item.get("dataItemMap", {})
                val_inv = mapa.get("inverter_power", 0)
                val_prod = mapa.get("product_power", 0)
                val_yield = mapa.get("daily_energy_yield", 0)
                
                # Guarda na tabela visual
                lista_tabela.append({
                    "Data": data_item.strftime("%d/%m/%Y"),
                    "inverter_power (kWh?)": val_inv,
                    "product_power": val_prod,
                    "daily_yield": val_yield
                })
                
                if data_item == data_alvo:
                    encontrado = item
            
            # MOSTRA RESULTADO
            if encontrado:
                mapa = encontrado.get("dataItemMap", {})
                val_final = mapa.get("inverter_power", 0) # Apostando nesse campo baseado no PDF
                
                st.divider()
                st.markdown(f"### 🎉 ENCONTRADO!")
                st.markdown(f"Data: **{data_alvo.strftime('%d/%m/%Y')}**")
                
                col_a, col_b, col_c = st.columns(3)
                col_a.metric("inverter_power", f"{mapa.get('inverter_power')} kWh")
                col_b.metric("inverterYield", f"{mapa.get('inverterYield')} kWh")
                col_c.metric("PVYield", f"{mapa.get('PVYield')} kWh")
                
                if abs(float(val_final) - 62.20) < 1:
                    st.success("✅ **BINGO!** O valor bate com o esperado (62.20)!")
                    st.caption(f"Campo correto identificado: 'inverter_power' ou 'inverterYield'.")
                else:
                    st.warning(f"⚠️ Valor encontrado ({val_final}) é diferente de 62.20.")
            else:
                st.error(f"❌ Dia {data_alvo} não encontrado na lista retornada pela API.")
                st.write("Lista recebida (confira as datas):")
                st.dataframe(lista_tabela)
                
        except Exception as e:
            st.error(f"Erro API: {e}")

else:
    st.warning("Cliente não encontrado.")
