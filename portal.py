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
st.set_page_config(page_title="Portal Eon Solar", page_icon="⚡", layout="wide")

# --- CONEXÃO GOOGLE SHEETS ---
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

def conectar_gsheets():
    try:
        if "gcp_service_account" not in st.secrets: return None
        creds_dict = dict(st.secrets["gcp_service_account"])
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
                db[str(row["Nome_Conta"]).upper().strip()] = {
                    "id": str(row["ID_Inversor"]), "marca": row["Marca"], "nome": row["Nome_Inversor"]
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

# --- BUSCA SOLIS ---
def buscar_geracao_solis(station_id, data_inicio, data_fim):
    dados_diarios = {} 
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
                if len(dia_str) < 3: full_date = f"{mes}-{int(dia_str):02d}"
                else: full_date = dia_str
                data_obj = datetime.strptime(full_date, "%Y-%m-%d").date()
                if data_inicio <= data_obj <= data_fim:
                    dados_diarios[data_obj] = float(rec.get("energy", 0))
        except: pass
        
    if dados_diarios:
        df = pd.DataFrame(list(dados_diarios.items()), columns=['Data', 'kWh'])
        df['Data'] = pd.to_datetime(df['Data'])
        df = df.set_index('Data').sort_index()
        return df['kWh'].sum(), df
    return 0.0, pd.DataFrame()

# --- BUSCA HUAWEI "TRATOR" (Focado no Total) ---
def buscar_geracao_huawei(station_code, data_inicio, data_fim):
    token = get_huawei_token()
    if not token: return 0.0, pd.DataFrame()
    
    headers = {"xsrf-token": token}
    total_final = 0.0
    
    # Datas para consulta
    ts_inicio = pd.Timestamp(data_inicio)
    ts_fim = pd.Timestamp(data_fim)
    
    # 1. TENTATIVA ANUAL (Mais limpa)
    # Baixa o ano inteiro e procura o mês específico
    try:
        st.toast(f"Consultando fechamento anual...", icon="📅")
        collect_time_year = int(datetime(ts_inicio.year, 1, 1).timestamp() * 1000)
        r = requests.post(f"{CREDS['huawei']['url']}/getKpiStationYear", json={"stationCodes": station_code, "collectTime": collect_time_year}, headers=headers, timeout=5)
        meses_ano = r.json().get("data", [])
        
        for m in meses_ano:
            ms = m.get("collectTime", 0)
            if ms > 0:
                data_mes = datetime.fromtimestamp(ms / 1000).date()
                # Se o mês do registro for o mesmo do mês pedido (ex: Janeiro)
                if data_mes.year == ts_inicio.year and data_mes.month == ts_inicio.month:
                    mapa = m.get("dataItemMap", {})
                    val = float(mapa.get("inverter_power", 0) or mapa.get("product_power", 0) or 0)
                    if val > 0:
                        return val, pd.DataFrame() # Retorna direto se achou!
    except: pass
    
    # 2. TENTATIVA MENSAL (Se anual falhou, varre dias)
    # Baixa Mês Anterior + Atual + Seguinte para garantir que pegamos tudo
    st.toast(f"Varrendo registros diários...", icon="🔍")
    
    dt_margem_inicio = ts_inicio - timedelta(days=32)
    dt_margem_fim = ts_fim + timedelta(days=32)
    meses_para_consultar = pd.date_range(dt_margem_inicio, dt_margem_fim, freq='MS').tolist()
    
    dados_diarios = {}
    cache_meses = set()
    
    for mes_obj in meses_para_consultar:
        collect_time = int(datetime(mes_obj.year, mes_obj.month, 15).timestamp() * 1000) # Dia 15 para segurança
        chave = f"{mes_obj.year}-{mes_obj.month}"
        if chave in cache_meses: continue
        cache_meses.add(chave)
        
        try:
            r = requests.post(f"{CREDS['huawei']['url']}/getKpiStationMonth", json={"stationCodes": station_code, "collectTime": collect_time}, headers=headers, timeout=5)
            lista_dias = r.json().get("data", [])
            
            if isinstance(lista_dias, list):
                for item in lista_dias:
                    ms = item.get("collectTime", 0)
                    if ms > 0:
                        data_real = datetime.fromtimestamp(ms / 1000).date()
                        mapa = item.get("dataItemMap", {})
                        
                        # Pega valor de energia
                        val = float(mapa.get("inverter_power", 0) or mapa.get("inverterYield", 0) or mapa.get("product_power", 0) or 0)
                        
                        # ESTRATÉGIA "O DIA GIGANTE"
                        # Se acharmos um valor > 500 kWh num dia só, isso é o TOTAL DO MÊS bugado. Usamos ele.
                        if val > 500 and (data_inicio <= data_real <= data_fim):
                            st.toast(f"Encontrado registro consolidado no dia {data_real.strftime('%d/%m')}", icon="📦")
                            return val, pd.DataFrame() # Retorna o valor gigante como total
                        
                        # Se for valor normal, guarda para somar
                        if val > 0 and (data_inicio <= data_real <= data_fim):
                            dados_diarios[data_real] = val
        except: pass

    # 3. SOMA MANUAL (Se não achou gigante)
    if dados_diarios:
        df = pd.DataFrame(list(dados_diarios.items()), columns=['Data', 'kWh'])
        df['Data'] = pd.to_datetime(df['Data'])
        df = df.set_index('Data').sort_index()
        return df['kWh'].sum(), df
    
    return 0.0, pd.DataFrame()

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
st.sidebar.title("☀️ Eon Solar")
menu = st.sidebar.radio("Navegação", ["🏠 Home", "📄 Auditoria de Conta", "⚙️ Configurações"])

if menu == "🏠 Home":
    st.title("Dashboard Geral")
    with st.spinner("Conectando..."):
        db = carregar_clientes()
    c1, c2 = st.columns(2)
    c1.metric("Clientes", len(db))
    c2.metric("Status", "Online 🟢")

elif menu == "📄 Auditoria de Conta":
    st.title("Nova Auditoria")
    nome_input = st.text_input("Nome na Conta:", placeholder="JOAO DA SILVA").upper().strip()
    
    if nome_input:
        db = carregar_clientes()
        st.divider()
        usina_vinculada = db.get(nome_input)
        
        if usina_vinculada:
            st.success(f"✅ Cliente: **{usina_vinculada['nome']}**")
        else:
            st.warning(f"Cliente '{nome_input}' não encontrado.")
            opcoes = listar_todas_usinas()
            nomes = [u["display"] for u in opcoes]
            escolha = st.selectbox("Vincular Inversor:", ["Selecione..."] + nomes)
            if escolha != "Selecione..." and st.button("Salvar"):
                obj = next(u for u in opcoes if u["display"] == escolha)
                salvar_cliente(nome_input, obj)
                st.rerun()

        if usina_vinculada:
            st.subheader("🗓️ Análise de Geração")
            c1, c2 = st.columns(2)
            dt_inicio = c1.date_input("Início", value=datetime.today().replace(day=1))
            dt_fim = c2.date_input("Fim", value=datetime.today())
            
            if st.button("🚀 Auditar Geração"):
                with st.spinner(f"Obtendo total da {usina_vinculada['marca']}..."):
                    if usina_vinculada["marca"] == "Solis":
                        total, df_diario = buscar_geracao_solis(usina_vinculada["id"], dt_inicio, dt_fim)
                    elif usina_vinculada["marca"] == "Huawei":
                        total, df_diario = buscar_geracao_huawei(usina_vinculada["id"], dt_inicio, dt_fim)
                    
                    # RESULTADO PRINCIPAL (GRANDE)
                    st.metric("Geração Total no Período", f"{total:.2f} kWh")
                    
                    fatura = st.number_input("Crédito na Fatura (kWh)", value=0.0)
                    
                    if fatura > 0:
                        diff = fatura - total
                        st.divider()
                        if diff < -5: st.error(f"⚠️ DIVERGÊNCIA: {diff:.2f} kWh (Faltou crédito)")
                        elif diff > 5: st.warning(f"⚠️ DIVERGÊNCIA: +{diff:.2f} kWh (Sobrou crédito)")
                        else: st.success(f"✅ CONTA BATIDA (Diferença: {diff:.2f} kWh)")

elif menu == "⚙️ Configurações":
    st.info("Sistema Conectado.")
    if st.button("Recarregar"): st.cache_data.clear(); st.rerun()
