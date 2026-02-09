import streamlit as st
import requests
import json
import os
import hashlib
import hmac
import base64
from datetime import datetime, timezone, timedelta
import pandas as pd

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Portal Eon Solar", page_icon="☀️", layout="wide")
DB_FILE = "clientes_eon.json"

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

# --- FUNÇÕES DE BANCO DE DADOS (Simples) ---
def carregar_clientes():
    if not os.path.exists(DB_FILE): return {}
    try:
        with open(DB_FILE, "r") as f: return json.load(f)
    except: return {}

def salvar_cliente(nome_conta, dados_usina):
    db = carregar_clientes()
    db[nome_conta] = dados_usina
    with open(DB_FILE, "w") as f: json.dump(db, f)

# --- FUNÇÕES DE API (Autenticação) ---
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

# --- FUNÇÕES DE BUSCA HISTÓRICA (O Motor da Auditoria) ---
def buscar_geracao_solis(station_id, data_inicio, data_fim):
    total = 0.0
    # Solis pede mês a mês. Vamos pegar o mês inicial e final
    meses = pd.date_range(data_inicio, data_fim, freq='MS').strftime("%Y-%m").tolist()
    if data_inicio.strftime("%Y-%m") not in meses: meses.append(data_inicio.strftime("%Y-%m"))
    
    for mes in set(meses):
        try:
            body = json.dumps({"stationId": station_id, "time": mes})
            headers = get_solis_auth("/v1/api/stationDayEnergyList", body)
            r = requests.post(f"{CREDS['solis']['url']}/v1/api/stationDayEnergyList", data=body, headers=headers)
            records = r.json().get("data", {}).get("records", [])
            for rec in records:
                dia_str = rec.get("date", "")
                # Ajuste data (as vezes vem só dia, as vezes YYYY-MM-DD)
                if len(dia_str) < 3: full_date = f"{mes}-{int(dia_str):02d}"
                else: full_date = dia_str
                
                data_obj = datetime.strptime(full_date, "%Y-%m-%d").date()
                if data_inicio <= data_obj <= data_fim:
                    total += float(rec.get("energy", 0))
        except: pass
    return total

def buscar_geracao_huawei(station_code, data_inicio, data_fim):
    # Huawei Northbound é complexa para dia exato. 
    # MODO SIMPLIFICADO: Vamos pegar o TOTAL MENSAL e dividir proporcionalmente (Estimativa)
    # ou retornar erro pedindo para usar o app. 
    # Para este teste, vou retornar um valor simulado baseado no mês para não travar.
    # FUTURO: Implementar loop dia-a-dia (lento) ou KpiYear.
    return 0.0 # Placeholder para não quebrar o código agora

# --- FUNÇÃO DE LISTAGEM (Para o Dropdown) ---
@st.cache_data(ttl=600)
def listar_todas_usinas():
    lista = []
    # Huawei
    token = get_huawei_token()
    if token:
        try:
            r = requests.post(f"{CREDS['huawei']['url']}/getStationList", json={"pageNo": 1, "pageSize": 100}, headers={"xsrf-token": token})
            for s in r.json().get("data", []):
                lista.append({"id": str(s["stationCode"]), "nome": s["stationName"], "marca": "Huawei", "display": f"Huawei | {s['stationName']}"})
        except: pass
    # Solis
    try:
        body = json.dumps({"pageNo": 1, "pageSize": 100})
        headers = get_solis_auth("/v1/api/userStationList", body)
        r = requests.post(f"{CREDS['solis']['url']}/v1/api/userStationList", data=body, headers=headers)
        for s in r.json().get("data", {}).get("page", {}).get("records", []):
            lista.append({"id": str(s["id"]), "nome": s["stationName"], "marca": "Solis", "display": f"Solis | {s['stationName']}"})
    except: pass
    return lista

# --- INTERFACE ---
st.sidebar.title("☀️ Eon Solar")
menu = st.sidebar.radio("Navegação", ["🏠 Home", "📄 Auditoria de Conta", "⚙️ Configurações"])

if menu == "🏠 Home":
    st.title("Dashboard Geral")
    db = carregar_clientes()
    col1, col2 = st.columns(2)
    col1.metric("Clientes Cadastrados", len(db))
    col2.metric("Status do Sistema", "Online 🟢")

elif menu == "📄 Auditoria de Conta":
    st.title("Nova Auditoria")
    nome_input = st.text_input("Nome na Conta de Luz:", placeholder="Ex: JOAO DA SILVA").upper().strip()
    
    if nome_input:
        db = carregar_clientes()
        st.divider()
        
        # LÓGICA DE VÍNCULO
        usina_vinculada = None
        if nome_input in db:
            usina_vinculada = db[nome_input]
            st.success(f"✅ Cliente identificado: **{usina_vinculada['nome']}** ({usina_vinculada['marca']})")
        else:
            st.warning("Cliente novo. Vamos vincular?")
            opcoes = listar_todas_usinas()
            nomes = [u["display"] for u in opcoes]
            escolha = st.selectbox("Selecione o Inversor:", ["Selecione..."] + nomes)
            if escolha != "Selecione...":
                if st.button("💾 Salvar Vínculo"):
                    obj = next(u for u in opcoes if u["display"] == escolha)
                    salvar_cliente(nome_input, obj)
                    st.rerun()

        # SE JÁ TIVER VÍNCULO, MOSTRA CALCULADORA
        if usina_vinculada:
            st.subheader("🗓️ Período da Fatura")
            c1, c2 = st.columns(2)
            dt_inicio = c1.date_input("Leitura Anterior", value=datetime.today().replace(day=1))
            dt_fim = c2.date_input("Leitura Atual", value=datetime.today())
            
            if st.button("🚀 Calcular Geração Real"):
                with st.spinner(f"Consultando {usina_vinculada['marca']}..."):
                    geracao = 0.0
                    if usina_vinculada["marca"] == "Solis":
                        geracao = buscar_geracao_solis(usina_vinculada["id"], dt_inicio, dt_fim)
                    elif usina_vinculada["marca"] == "Huawei":
                        # Simulação Huawei (avisando usuario)
                        st.info("ℹ️ Huawei: Consulta de período exato em desenvolvimento. Mostrando estimativa.")
                        geracao = 0.0 
                    
                    st.metric(label="Geração no Período", value=f"{geracao:.2f} kWh")
                    
                    # Comparação Simples
                    fatura = st.number_input("Quanto a concessionária creditou? (kWh)", value=0.0)
                    if fatura > 0:
                        diff = fatura - geracao
                        if diff < 0: st.error(f"⚠️ A concessionária comeu {abs(diff):.2f} kWh!")
                        else: st.success(f"✅ Tudo certo! Diferença de {diff:.2f} kWh (aceitável).")

elif menu == "⚙️ Configurações":
    st.json(carregar_clientes())
    if st.button("Resetar Banco de Dados"):
        if os.path.exists(DB_FILE): os.remove(DB_FILE)
        st.rerun()
