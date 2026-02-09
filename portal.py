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
st.set_page_config(page_title="Portal Eon Solar", page_icon="☀️", layout="wide")

# --- CONEXÃO GOOGLE SHEETS ---
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

def conectar_gsheets():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        credentials = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        client = gspread.authorize(credentials)
        return client.open("Banco de Dados Eon").sheet1
    except Exception as e:
        # st.error(f"Erro plan: {e}") # Silenciado para não poluir visualmente se der erro pontual
        return None

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
    except Exception as e:
        st.error(f"Erro Sheets: {e}")
        return False

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

# --- FUNÇÕES DE AUTENTICAÇÃO ---
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

# --- BUSCA SOLIS (MANTIDA IGUAL) ---
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

# --- BUSCA HUAWEI "ARRASTÃO" (DEEP SCAN) ---
def buscar_geracao_huawei(station_code, data_inicio, data_fim):
    token = get_huawei_token()
    if not token: return 0.0, pd.DataFrame()
    
    headers = {"xsrf-token": token}
    dados_diarios = {} # Vai somar a geração de TODOS os dispositivos
    
    # 1. LISTA TODOS OS DISPOSITIVOS DA USINA
    dev_ids = []
    try:
        r = requests.post(f"{CREDS['huawei']['url']}/getDevList", json={"stationCodes": station_code}, headers=headers, timeout=10)
        devices = r.json().get("data", [])
        # Pega IDs de tudo que não for medidor de consumo puro (tenta Inversores e Baterias)
        # Tipos comuns: 1=Inversor, 38=Dongle. Vamos tentar ler todos.
        dev_ids = [d.get("id") for d in devices if d.get("id")]
    except: pass

    if not dev_ids:
        st.warning("Nenhum dispositivo encontrado na usina.")
        return 0.0, pd.DataFrame()

    st.toast(f"Varrendo {len(dev_ids)} dispositivo(s)...", icon="🔍")
    
    # 2. VARREDURA POR DISPOSITIVO
    ts_inicio = pd.Timestamp(data_inicio)
    ts_fim = pd.Timestamp(data_fim)
    meses = pd.date_range(ts_inicio, ts_fim, freq='MS').tolist()
    if not meses or ts_inicio.replace(day=1) < meses[0]:
        meses.insert(0, ts_inicio.replace(day=1))
    
    progresso = st.empty()
    
    # Dicionário temporário para evitar duplicatas (Data -> Soma kWh)
    temp_dados = {}

    for dev_id in dev_ids:
        for mes_obj in meses:
            progresso.text(f"Lendo Dev {dev_id} ({mes_obj.month}/{mes_obj.year})...")
            collect_time = int(datetime(mes_obj.year, mes_obj.month, 1).timestamp() * 1000)
            
            payload = {"devIds": str(dev_id), "collectTime": collect_time}
            
            try:
                # Endpoint de DISPOSITIVO (o segredo está aqui)
                r = requests.post(f"{CREDS['huawei']['url']}/getDevKpiMonth", json=payload, headers=headers, timeout=10)
                dados = r.json().get("data", [])
                
                if isinstance(dados, list):
                    for dia_kpi in dados:
                        mapa = dia_kpi.get("dataItemMap", {})
                        
                        # Chave mágica dos dispositivos: daily_energy_yield
                        val = float(mapa.get("daily_energy_yield", 0) or mapa.get("daily_yield", 0) or 0)
                        
                        tempo_ms = dia_kpi.get("collectTime", 0)
                        if tempo_ms > 0 and val > 0:
                            data_registro = datetime.fromtimestamp(tempo_ms / 1000).date()
                            
                            # Soma no dia (caso tenha mais de 1 inversor)
                            if data_registro not in temp_dados: temp_dados[data_registro] = 0.0
                            temp_dados[data_registro] += val
            except: pass

    progresso.empty()

    # Filtra pelo período escolhido
    for dt, val in temp_dados.items():
        if data_inicio <= dt <= data_fim:
            dados_diarios[dt] = val

    if not dados_diarios:
        # PLANO C: Se falhar tudo, tenta Estação normal
        return 0.0, pd.DataFrame()

    df = pd.DataFrame(list(dados_diarios.items()), columns=['Data', 'kWh'])
    df['Data'] = pd.to_datetime(df['Data'])
    df = df.set_index('Data').sort_index()
    
    # Filtro final de segurança
    mask = (df.index >= pd.to_datetime(data_inicio)) & (df.index <= pd.to_datetime(data_fim))
    df_final = df.loc[mask]
    
    return df_final['kWh'].sum(), df_final[['kWh']]

# --- FUNÇÃO LISTAGEM ---
@st.cache_data(ttl=600)
def listar_todas_usinas():
    lista = []
    # Huawei
    try:
        token = get_huawei_token()
        if token:
            r = requests.post(f"{CREDS['huawei']['url']}/getStationList", json={"pageNo": 1, "pageSize": 100}, headers={"xsrf-token": token}, timeout=10)
            dados_brutos = r.json().get("data", [])
            estacoes = dados_brutos if isinstance(dados_brutos, list) else dados_brutos.get("list", [])
            for s in estacoes:
                lista.append({"id": str(s.get("stationCode")), "nome": s.get("stationName"), "marca": "Huawei", "display": f"Huawei | {s.get('stationName')}"})
    except: pass
    # Solis
    try:
        body = json.dumps({"pageNo": 1, "pageSize": 100})
        headers = get_solis_auth("/v1/api/userStationList", body)
        r = requests.post(f"{CREDS['solis']['url']}/v1/api/userStationList", data=body, headers=headers, timeout=10)
        dados = r.json().get("data", {}).get("page", {}).get("records", [])
        for s in dados:
            lista.append({"id": str(s.get("id")), "nome": s.get("stationName"), "marca": "Solis", "display": f"Solis | {s.get('stationName')}"})
    except: pass
    return lista

# --- INTERFACE ---
st.sidebar.title("☀️ Eon Solar")
menu = st.sidebar.radio("Navegação", ["🏠 Home", "📄 Auditoria de Conta", "⚙️ Configurações"])

if menu == "🏠 Home":
    st.title("Dashboard Geral")
    with st.spinner("Sincronizando com Google Sheets..."):
        db = carregar_clientes()
    c1, c2 = st.columns(2)
    c1.metric("Clientes Cadastrados", len(db))
    c2.metric("Status", "Operacional 🟢")

elif menu == "📄 Auditoria de Conta":
    st.title("Nova Auditoria")
    nome_input = st.text_input("Nome na Conta de Luz:", placeholder="Ex: JOAO DA SILVA").upper().strip()
    
    if nome_input:
        db = carregar_clientes()
        st.divider()
        usina_vinculada = db.get(nome_input)
        
        if usina_vinculada:
            st.success(f"✅ Cliente identificado: **{usina_vinculada['nome']}** ({usina_vinculada['marca']})")
        else:
            st.warning(f"Cliente '{nome_input}' não encontrado.")
            opcoes = listar_todas_usinas()
            nomes = [u["display"] for u in opcoes]
            escolha = st.selectbox("Vincular a qual inversor?", ["Selecione..."] + nomes)
            if escolha != "Selecione..." and st.button("💾 Salvar Vínculo"):
                with st.spinner("Salvando..."):
                    obj = next(u for u in opcoes if u["display"] == escolha)
                    salvar_cliente(nome_input, obj)
                    st.rerun()

        if usina_vinculada:
            st.subheader("🗓️ Análise de Geração")
            c1, c2 = st.columns(2)
            dt_inicio = c1.date_input("Início", value=datetime.today().replace(day=1))
            dt_fim = c2.date_input("Fim", value=datetime.today())
            
            if st.button("🚀 Auditar Geração"):
                with st.spinner(f"Baixando dados da {usina_vinculada['marca']}..."):
                    total, df_diario = 0.0, pd.DataFrame()
                    
                    if usina_vinculada["marca"] == "Solis":
                        total, df_diario = buscar_geracao_solis(usina_vinculada["id"], dt_inicio, dt_fim)
                    elif usina_vinculada["marca"] == "Huawei":
                        total, df_diario = buscar_geracao_huawei(usina_vinculada["id"], dt_inicio, dt_fim)
                    
                    col_metrica, col_fatura = st.columns(2)
                    col_metrica.metric("Geração Total (Inversor)", f"{total:.2f} kWh")
                    
                    fatura = col_fatura.number_input("Crédito na Fatura (kWh)", value=0.0)
                    
                    if not df_diario.empty:
                        st.subheader("📊 Histórico Diário")
                        
                        df_diario.index = pd.to_datetime(df_diario.index)
                        calendario_completo = pd.date_range(start=pd.to_datetime(dt_inicio), end=pd.to_datetime(dt_fim))
                        df_completo = df_diario.reindex(calendario_completo, fill_value=0.0)
                        
                        chart_data = df_completo.copy()
                        chart_data.index = chart_data.index.strftime("%d/%m")
                        st.bar_chart(chart_data, color="#FFA500") 
                        
                        with st.expander("🔎 Ver Tabela Detalhada"):
                            st.dataframe(df_completo.style.format("{:.2f} kWh"))
                    
                    if fatura > 0:
                        diff = fatura - total
                        st.divider()
                        if diff < -5:
                            st.error(f"⚠️ DIVERGÊNCIA: Faltou creditar {abs(diff):.2f} kWh")
                        elif diff > 5:
                            st.warning(f"⚠️ DIVERGÊNCIA: Creditou a mais (+{diff:.2f} kWh)")
                        else:
                            st.success(f"✅ CONTA BATIDA (Diferença: {diff:.2f} kWh)")

elif menu == "⚙️ Configurações":
    st.info("Banco de Dados conectado ao Google Sheets.")
    if st.button("Forçar Recarregamento"):
        st.cache_data.clear()
        st.rerun()
