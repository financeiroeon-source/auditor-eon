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

# --- IMPORTA O LEITOR DE PDF ---
try:
    import processador_pdf
except ImportError:
    st.warning("⚠️ Módulo 'processador_pdf.py' não encontrado. O upload de PDF não funcionará.")

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

# --- BUSCA SOLIS (Lógica Completa) ---
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

# --- BUSCA HUAWEI (O "TRATOR" - Lógica Completa) ---
def buscar_geracao_huawei(station_code, data_inicio, data_fim):
    token = get_huawei_token()
    if not token: return 0.0, pd.DataFrame()
    
    headers = {"xsrf-token": token}
    ts_inicio = pd.Timestamp(data_inicio)
    ts_fim = pd.Timestamp(data_fim)
    
    # 1. TENTATIVA ANUAL (Rápida)
    try:
        collect_time_year = int(datetime(ts_inicio.year, 1, 1).timestamp() * 1000)
        r = requests.post(f"{CREDS['huawei']['url']}/getKpiStationYear", json={"stationCodes": station_code, "collectTime": collect_time_year}, headers=headers, timeout=5)
        meses_ano = r.json().get("data", [])
        
        for m in meses_ano:
            ms = m.get("collectTime", 0)
            if ms > 0:
                data_mes = datetime.fromtimestamp(ms / 1000).date()
                # Verifica se é o mês exato pedido (se a busca for de um mês fechado, ex: 01/01 a 31/01)
                if data_mes.year == ts_inicio.year and data_mes.month == ts_inicio.month and ts_inicio.day == 1:
                    mapa = m.get("dataItemMap", {})
                    val = float(mapa.get("inverter_power", 0) or mapa.get("product_power", 0) or 0)
                    if val > 0:
                        return val, pd.DataFrame()
    except: pass
    
    # 2. TENTATIVA MENSAL (Varredura detalhada)
    dt_margem_inicio = ts_inicio - timedelta(days=32)
    dt_margem_fim = ts_fim + timedelta(days=32)
    meses_para_consultar = pd.date_range(dt_margem_inicio, dt_margem_fim, freq='MS').tolist()
    
    dados_diarios = {}
    cache_meses = set()
    
    for mes_obj in meses_para_consultar:
        collect_time = int(datetime(mes_obj.year, mes_obj.month, 15).timestamp() * 1000)
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
                        
                        val = float(mapa.get("inverter_power", 0) or mapa.get("inverterYield", 0) or mapa.get("product_power", 0) or 0)
                        
                        # Se achar valor gigante (>500) dentro do período, assume que é o acumulado mensal bugado
                        if val > 500 and (data_inicio <= data_real <= data_fim):
                            return val, pd.DataFrame()
                        
                        if val > 0 and (data_inicio <= data_real <= data_fim):
                            dados_diarios[data_real] = val
        except: pass

    if dados_diarios:
        df = pd.DataFrame(list(dados_diarios.items()), columns=['Data', 'kWh'])
        df['Data'] = pd.to_datetime(df['Data'])
        df = df.set_index('Data').sort_index()
        return df['kWh'].sum(), df
    
    return 0.0, pd.DataFrame()

# --- LISTAGEM DE USINAS ---
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
st.sidebar.title("💰 Eon Solar")
menu = st.sidebar.radio("Navegação", ["🏠 Home", "📄 Auditoria Financeira", "⚙️ Configurações"])

if menu == "🏠 Home":
    st.title("Dashboard Geral")
    with st.spinner("Conectando..."):
        db = carregar_clientes()
    c1, c2 = st.columns(2)
    c1.metric("Clientes", len(db))
    c2.metric("Status", "Online 🟢")

elif menu == "📄 Auditoria Financeira":
    st.title("Auditoria de Precisão")
    
    # 1. UPLOAD
    st.markdown("### 1. Dados da Concessionária (PDF)")
    uploaded_file = st.file_uploader("Arraste a conta de luz aqui", type="pdf")
    
    # Variáveis Padrão
    nome_padrao = "JOAO DA SILVA"
    tarifa_cons = 0.0
    tarifa_cred = 0.0
    kwh_creditado = 0.0
    cip = 0.0
    dt_inicio_padrao = datetime.today().replace(day=1)

    if uploaded_file:
        with st.spinner("Analisando Fatura (TUSD, TE, ICMS, CIP)..."):
            try:
                dados_pdf = processador_pdf.extrair_dados_fatura(uploaded_file)
                
                if dados_pdf["tarifa_consumo_calc"] > 0: tarifa_cons = dados_pdf["tarifa_consumo_calc"]
                if dados_pdf["tarifa_credito_calc"] > 0: tarifa_cred = dados_pdf["tarifa_credito_calc"]
                if dados_pdf["injetado_kwh"] > 0: kwh_creditado = dados_pdf["injetado_kwh"]
                if dados_pdf["cip_cosip"] > 0: cip = dados_pdf["cip_cosip"]
                if dados_pdf["mes_referencia"]: dt_inicio_padrao = dados_pdf["mes_referencia"]
                
                st.success("✅ Leitura Completa! Tarifas e impostos identificados.")
                
                with st.expander("🔎 Ver Detalhes Extraídos do PDF"):
                    c_a, c_b, c_c = st.columns(3)
                    c_a.metric("Tarifa Consumo (TUSD+TE)", f"R$ {tarifa_cons:.4f}")
                    c_b.metric("Tarifa Crédito (GD)", f"R$ {tarifa_cred:.4f}")
                    c_c.metric("Ilum. Pública (CIP)", f"R$ {cip:.2f}")
            except Exception as e:
                st.error(f"Erro ao processar PDF: {e}")

    # 2. CONFERÊNCIA
    st.divider()
    st.markdown("### 2. Cruzamento de Dados")
    
    col_nome, col_vazio = st.columns([2, 1])
    nome_input = col_nome.text_input("Nome do Cliente:", value=nome_padrao).upper().strip()
    
    if nome_input:
        db = carregar_clientes()
        usina = db.get(nome_input)
        
        if usina:
            st.info(f"Conectado a: **{usina['nome']}** ({usina['marca']})")
            
            # Inputs finais para cálculo
            import calendar
            last_day = calendar.monthrange(dt_inicio_padrao.year, dt_inicio_padrao.month)[1]
            dt_fim_padrao = dt_inicio_padrao.replace(day=last_day)
            
            col_d1, col_d2, col_t1, col_kwh = st.columns(4)
            d_ini = col_d1.date_input("Início", dt_inicio_padrao)
            d_fim = col_d2.date_input("Fim", dt_fim_padrao)
            
            # Tarifa final aplicada (prioriza a tarifa de crédito se houver)
            t_final = col_t1.number_input("Tarifa Média (R$)", value=tarifa_cred if tarifa_cred > 0 else (tarifa_cons if tarifa_cons > 0 else 1.00), format="%.4f")
            k_cred = col_kwh.number_input("Crédito na Conta (kWh)", value=kwh_creditado)

            if st.button("🚀 Executar Auditoria", type="primary"):
                with st.spinner("Buscando Geração Real..."):
                    if usina["marca"] == "Huawei":
                        kwh_gerado, _ = buscar_geracao_huawei(usina["id"], d_ini, d_fim)
                    else:
                        kwh_gerado, _ = buscar_geracao_solis(usina["id"], d_ini, d_fim)
                    
                    st.divider()
                    
                    # CÁLCULO FINANCEIRO REAL
                    diff_kwh = k_cred - kwh_gerado
                    valor_diff = diff_kwh * t_final
                    
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Geração Inversor", f"{kwh_gerado:.2f} kWh")
                    c2.metric("Crédito Fatura", f"{k_cred:.2f} kWh")
                    
                    delta_color = "normal"
                    if diff_kwh < -5: delta_color = "inverse" # Vermelho se negativo
                    elif diff_kwh > 5: delta_color = "off"    # Verde/Cinza se positivo
                    
                    c3.metric("Diferença", f"{diff_kwh:.2f} kWh", delta=f"R$ {valor_diff:.2f}", delta_color=delta_color)
                    
                    if diff_kwh < -5:
                        st.error(f"🚨 **ALERTA DE PREJUÍZO:** A concessionária deixou de creditar **{abs(diff_kwh):.2f} kWh**.")
                        st.write(f"Considerando a tarifa de R$ {t_final:.4f}, isso representa **R$ {abs(valor_diff):.2f}** a menos no bolso do cliente.")
                    elif diff_kwh > 5:
                        st.success(f"✅ **LUCRO OPERACIONAL:** Creditado a mais que o gerado.")
                    else:
                        st.info("✅ **CONTA BATIDA!** Nenhuma divergência financeira relevante.")

        else:
            st.warning("Cliente não encontrado.")

elif menu == "⚙️ Configurações":
    st.info("Sistema Conectado.")
    if st.button("Recarregar"): st.cache_data.clear(); st.rerun()
