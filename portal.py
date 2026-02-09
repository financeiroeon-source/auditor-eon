import streamlit as st
import requests
import json
import hashlib
import hmac
import base64
from datetime import datetime, timezone
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Portal Eon Solar", page_icon="☀️", layout="wide")

# --- CONEXÃO GOOGLE SHEETS ---
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

def conectar_gsheets():
    creds_dict = dict(st.secrets["gcp_service_account"])
    credentials = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(credentials)
    return client.open("Banco de Dados Eon").sheet1

def carregar_clientes():
    try:
        sheet = conectar_gsheets()
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
    except Exception as e:
        print(f"Erro plan: {e}")
        return {}

def salvar_cliente(nome_conta, dados_usina):
    try:
        sheet = conectar_gsheets()
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

# --- AUTH APIS ---
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

# --- FUNÇÕES DE BUSCA (RETORNANDO DADOS PARA GRÁFICO) ---
def buscar_geracao_solis(station_id, data_inicio, data_fim):
    dados_diarios = {} # Dicionario data: valor
    
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
        
    # Cria DataFrame para o gráfico
    if dados_diarios:
        df = pd.DataFrame(list(dados_diarios.items()), columns=['Data', 'kWh'])
        df = df.set_index('Data').sort_index()
        return df['kWh'].sum(), df
    return 0.0, pd.DataFrame()

def buscar_geracao_huawei(station_code, data_inicio, data_fim):
    token = get_huawei_token()
    if not token: return 0.0, pd.DataFrame()

    ts_inicio = pd.Timestamp(data_inicio)
    ts_fim = pd.Timestamp(data_fim)
    meses_para_consultar = pd.date_range(ts_inicio, ts_fim, freq='MS').tolist()
    if not meses_para_consultar or ts_inicio.replace(day=1) < meses_para_consultar[0]:
        meses_para_consultar.insert(0, ts_inicio.replace(day=1))
    
    headers = {"xsrf-token": token}
    dados_diarios = {}
    progresso = st.empty()

    for mes_obj in meses_para_consultar:
        progresso.text(f"Consultando Huawei: Mês {mes_obj.month}/{mes_obj.year}...")
        collect_time = int(datetime(mes_obj.year, mes_obj.month, 1).timestamp() * 1000)
        payload = {"stationCodes": station_code, "collectTime": collect_time}
        try:
            r = requests.post(f"{CREDS['huawei']['url']}/getKpiStationMonth", json=payload, headers=headers, timeout=15)
            dados = r.json().get("data", [])
            if isinstance(dados, list):
                for dia_kpi in dados:
                    mapa = dia_kpi.get("dataItemMap", {})
                    producao = float(mapa.get("inverter_power", 0) or mapa.get("product_power", 0) or 0)
                    tempo_ms = dia_kpi.get("collectTime", 0)
                    if tempo_ms > 0:
                        data_registro = datetime.fromtimestamp(tempo_ms / 1000).date()
                        if data_inicio <= data_registro <= data_fim:
                            dados_diarios[data_registro] = producao
        except: pass
            
    progresso.empty()
    
    if dados_diarios:
        df = pd.DataFrame(list(dados_diarios.items()), columns=['Data', 'kWh'])
        df = df.set_index('Data').sort_index()
        return df['kWh'].sum(), df
    return 0.0, pd.DataFrame()

# --- FUNÇÃO LISTAGEM (MANTIDA IGUAL) ---
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
                    
                    # --- MOSTRA OS RESULTADOS ---
                    col_metrica, col_fatura = st.columns(2)
                    col_metrica.metric("Geração Total (Inversor)", f"{total:.2f} kWh")
                    
                    fatura = col_fatura.number_input("Crédito na Fatura (kWh)", value=0.0)
                    
                    if not df_diario.empty:
                        st.subheader("📊 Histórico Diário")
                        
                        # --- CORREÇÃO VISUAL DO GRÁFICO ---
                        # 1. Garante que o índice é datetime
                        df_diario.index = pd.to_datetime(df_diario.index)
                        
                        # 2. Cria um calendário completo do início ao fim (preenche buracos com 0)
                        calendario_completo = pd.date_range(start=dt_inicio, end=dt_fim)
                        df_completo = df_diario.reindex(calendario_completo, fill_value=0.0)
                        
                        # 3. Formata a data para ficar bonitinha no eixo X (Dia/Mês)
                        df_completo.index = df_completo.index.strftime("%d/%m")
                        
                        # 4. Plota o gráfico preenchido
                        st.bar_chart(df_completo, color="#FFA500") 
                    
                    if fatura > 0:
                        diff = fatura - total
                        st.divider()
                        if diff < -5:
                            st.error(f"⚠️ DIVERGÊNCIA NEGATIVA: {diff:.2f} kWh")
                            st.caption("A concessionária creditou MENOS do que o inversor gerou.")
                        elif diff > 5:
                            st.warning(f"⚠️ DIVERGÊNCIA POSITIVA: +{diff:.2f} kWh")
                        else:
                            st.success(f"✅ AUDITORIA APROVADA (Diferença: {diff:.2f} kWh)")

elif menu == "⚙️ Configurações":
    st.info("Banco de Dados conectado ao Google Sheets.")
    if st.button("Forçar Recarregamento"):
        st.cache_data.clear()
        st.rerun()
