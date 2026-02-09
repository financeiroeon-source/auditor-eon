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

# --- CONEXÃO GOOGLE SHEETS (O Novo Cérebro) ---
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

def conectar_gsheets():
    # Pega as credenciais que você colou no Secrets
    creds_dict = dict(st.secrets["gcp_service_account"])
    credentials = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(credentials)
    # Abre a planilha pelo nome exato
    return client.open("Banco de Dados Eon").sheet1

def carregar_clientes():
    try:
        sheet = conectar_gsheets()
        rows = sheet.get_all_records()
        # Converte a Tabela do Google para o Dicionário do Python
        db = {}
        for row in rows:
            # Garante que as chaves existem para evitar erro de coluna vazia
            if "Nome_Conta" in row and row["Nome_Conta"]:
                db[row["Nome_Conta"]] = {
                    "id": str(row["ID_Inversor"]),
                    "marca": row["Marca"],
                    "nome": row["Nome_Inversor"]
                }
        return db
    except Exception as e:
        # Se der erro (ex: planilha vazia ou nome errado), retorna vazio mas avisa no log
        print(f"Erro ao ler planilha: {e}")
        return {}

def salvar_cliente(nome_conta, dados_usina):
    try:
        sheet = conectar_gsheets()
        # Adiciona uma nova linha no final da planilha
        sheet.append_row([
            nome_conta,
            str(dados_usina["id"]),
            dados_usina["marca"],
            dados_usina["nome"]
        ])
        return True
    except Exception as e:
        st.error(f"Erro ao salvar no Google Sheets: {e}")
        return False

# --- CREDENCIAIS DAS USINAS ---
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
                    total += float(rec.get("energy", 0))
        except: pass
    return total

def buscar_geracao_huawei(station_code, data_inicio, data_fim):
    total_energia = 0.0
    token = get_huawei_token()
    if not token:
        st.error("Falha de autenticação na Huawei.")
        return 0.0

    ts_inicio = pd.Timestamp(data_inicio)
    ts_fim = pd.Timestamp(data_fim)
    meses_para_consultar = pd.date_range(ts_inicio, ts_fim, freq='MS').tolist()
    if not meses_para_consultar or ts_inicio.replace(day=1) < meses_para_consultar[0]:
        meses_para_consultar.insert(0, ts_inicio.replace(day=1))
    
    headers = {"xsrf-token": token}
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
                            total_energia += producao
        except Exception as e:
            print(f"Erro mês {mes_obj}: {e}")
            
    progresso.empty()
    return total_energia

# --- FUNÇÃO DE LISTAGEM ---
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
    with st.spinner("Carregando banco de dados da nuvem..."):
        db = carregar_clientes()
    
    col1, col2 = st.columns(2)
    col1.metric("Clientes Cadastrados", len(db))
    col2.metric("Status do Sistema", "Online 🟢")

elif menu == "📄 Auditoria de Conta":
    st.title("Nova Auditoria")
    nome_input = st.text_input("Nome na Conta de Luz:", placeholder="Ex: JOAO DA SILVA").upper().strip()
    
    if nome_input:
        # Carrega SEMPRE da nuvem para garantir dados frescos
        db = carregar_clientes()
        st.divider()
        
        usina_vinculada = None
        if nome_input in db:
            usina_vinculada = db[nome_input]
            st.success(f"✅ Cliente identificado: **{usina_vinculada['nome']}** ({usina_vinculada['marca']})")
        else:
            st.warning(f"Cliente '{nome_input}' não encontrado na planilha.")
            st.write("Vamos cadastrar agora?")
            opcoes = listar_todas_usinas()
            nomes = [u["display"] for u in opcoes]
            escolha = st.selectbox("Selecione o Inversor:", ["Selecione..."] + nomes)
            if escolha != "Selecione...":
                if st.button("💾 Salvar na Planilha"):
                    with st.spinner("Salvando no Google Sheets..."):
                        obj = next(u for u in opcoes if u["display"] == escolha)
                        if salvar_cliente(nome_input, obj):
                            st.toast("Salvo com sucesso!", icon="☁️")
                            st.rerun()

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
                        geracao = buscar_geracao_huawei(usina_vinculada["id"], dt_inicio, dt_fim)
                    
                    st.metric(label="Geração no Período", value=f"{geracao:.2f} kWh")
                    
                    fatura = st.number_input("Quanto a concessionária creditou? (kWh)", value=0.0)
                    if fatura > 0:
                        diff = fatura - geracao
                        st.divider()
                        if diff < -5:
                            st.error(f"⚠️ A concessionária comeu {abs(diff):.2f} kWh!")
                            st.write(f"Era para ter: **{geracao:.2f}** | Veio: **{fatura:.2f}**")
                        elif diff > 5:
                            st.warning(f"🤔 Estranho... Creditou {diff:.2f} kWh A MAIS.")
                        else:
                            st.success(f"✅ Tudo certo! Diferença de {diff:.2f} kWh.")

elif menu == "⚙️ Configurações":
    st.write("Banco de Dados (Google Sheets):")
    st.info("Os dados agora estão seguros na sua planilha 'Banco de Dados Eon'.")
    if st.button("Recarregar Dados da Nuvem"):
        st.cache_data.clear()
        st.rerun()
