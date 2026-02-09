import streamlit as st
import requests
import json
import os
import hashlib
import hmac
import base64
from datetime import datetime, timezone

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Portal Eon Solar", page_icon="☀️", layout="wide")

# --- 1. BANCO DE DADOS SIMPLES (Arquivo JSON) ---
# Isso substitui o Google Sheets por enquanto, para testarmos a lógica.
DB_FILE = "clientes_eon.json"

def carregar_clientes():
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def salvar_cliente(nome_conta, dados_usina):
    db = carregar_clientes()
    db[nome_conta] = dados_usina
    with open(DB_FILE, "w") as f:
        json.dump(db, f, indent=4)
    return True

# --- 2. CREDENCIAIS (Sua Chave Mestra) ---
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

# --- 3. FUNÇÕES DE CONEXÃO (API) ---
# Função simplificada para pegar SÓ A LISTA de usinas para o cadastro
@st.cache_data(ttl=600) # Guarda na memória por 10 min para não ficar lento
def listar_todas_usinas():
    lista_unificada = []

    # --- HUAWEI ---
    try:
        s = requests.Session()
        r = s.post(f"{CREDS['huawei']['url']}/login", json={"userName": CREDS['huawei']['user'], "systemCode": CREDS['huawei']['pass']}, timeout=10)
        token = r.headers.get("xsrf-token")
        if token:
            r_list = s.post(f"{CREDS['huawei']['url']}/getStationList", json={"pageNo": 1, "pageSize": 100}, headers={"xsrf-token": token}, timeout=10)
            data = r_list.json().get("data", [])
            stations = data if isinstance(data, list) else data.get("list", [])
            for st_hw in stations:
                lista_unificada.append({
                    "id": str(st_hw.get("stationCode")),
                    "nome": st_hw.get("stationName"),
                    "marca": "Huawei",
                    "display": f"Huawei | {st_hw.get('stationName')}"
                })
    except Exception as e:
        print(f"Erro Huawei: {e}")

    # --- SOLIS ---
    try:
        resource = "/v1/api/userStationList"
        body = json.dumps({"pageNo": 1, "pageSize": 100})
        now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        content_md5 = base64.b64encode(hashlib.md5(body.encode('utf-8')).digest()).decode('utf-8')
        key = CREDS['solis']['key_secret'].encode('utf-8')
        sign_str = f"POST\n{content_md5}\napplication/json\n{now}\n{resource}"
        signature = hmac.new(key, sign_str.encode('utf-8'), hashlib.sha1).digest()
        auth = f"API {CREDS['solis']['key_id']}:{base64.b64encode(signature).decode('utf-8')}"
        headers = {"Authorization": auth, "Content-MD5": content_md5, "Content-Type": "application/json", "Date": now}
        
        r = requests.post(f"{CREDS['solis']['url']}{resource}", data=body, headers=headers, timeout=10)
        data = r.json().get("data", {}).get("page", {}).get("records", [])
        for st_sl in data:
            lista_unificada.append({
                "id": str(st_sl.get("id")),
                "nome": st_sl.get("stationName"),
                "marca": "Solis",
                "display": f"Solis | {st_sl.get('stationName')}"
            })
    except Exception as e:
        print(f"Erro Solis: {e}")

    return lista_unificada

# --- 4. INTERFACE DO SISTEMA ---

# Menu Lateral
st.sidebar.title("☀️ Eon Solar")
menu = st.sidebar.radio("Navegação", ["🏠 Home", "📄 Auditoria de Conta", "⚙️ Configurações"])

# --- PÁGINA: HOME ---
if menu == "🏠 Home":
    st.title("Dashboard Geral")
    st.info("Aqui teremos o resumo de toda a frota (Online/Offline).")
    
    # Carrega dados salvos
    clientes_salvos = carregar_clientes()
    col1, col2 = st.columns(2)
    col1.metric("Clientes Cadastrados", len(clientes_salvos))
    col2.metric("Usinas Conectadas", "Carregando...")

# --- PÁGINA: AUDITORIA (O CORAÇÃO DO SISTEMA) ---
elif menu == "📄 Auditoria de Conta":
    st.title("Nova Auditoria")
    st.markdown("Simule o upload da conta digitando o nome abaixo.")
    
    # 1. Entrada de Dados (Simulando o PDF)
    nome_cliente_input = st.text_input("Nome do Cliente (como na conta de luz):", placeholder="Ex: JOSE DA SILVA")
    
    if nome_cliente_input:
        nome_limpo = nome_cliente_input.upper().strip()
        db = carregar_clientes()
        
        st.divider()
        
        # CENÁRIO A: Cliente Já Existe
        if nome_limpo in db:
            usina = db[nome_limpo]
            st.success(f"✅ Cliente identificado! Vinculado à usina: **{usina['nome']} ({usina['marca']})**")
            
            # Aqui entraria a lógica de puxar a geração automática
            st.info(f"🤖 O sistema agora buscaria automaticamente a geração da {usina['marca']} para o ID {usina['id']}.")
            if st.button("Simular Auditoria"):
                st.write("📊 Gráfico de Geração x Fatura apareceria aqui.")
                
        # CENÁRIO B: Cliente Novo (Vínculo Assistido)
        else:
            st.warning(f"⚠️ Cliente '{nome_limpo}' não encontrado no banco de dados.")
            st.write("Vamos vincular agora? O sistema encontrou as seguintes usinas disponíveis:")
            
            # Busca lista nas APIs (Huawei + Solis)
            with st.spinner("Buscando usinas nas plataformas..."):
                opcoes_usinas = listar_todas_usinas()
            
            if not opcoes_usinas:
                st.error("Erro ao carregar lista de usinas ou nenhuma usina encontrada.")
            else:
                # Cria lista para o Dropdown
                lista_nomes = [u["display"] for u in opcoes_usinas]
                escolha = st.selectbox("Selecione qual inversor pertence a este cliente:", ["Selecione..."] + lista_nomes)
                
                if escolha != "Selecione...":
                    # Acha o objeto original da escolha
                    usina_selecionada = next(u for u in opcoes_usinas if u["display"] == escolha)
                    
                    col_save, col_cancel = st.columns([1, 4])
                    if col_save.button("💾 Salvar Vínculo"):
                        salvar_cliente(nome_limpo, usina_selecionada)
                        st.toast(f"Vínculo salvo! {nome_limpo} agora é {usina_selecionada['nome']}", icon="🎉")
                        st.rerun() # Recarrega a página para cair no Cenário A

# --- PÁGINA: CONFIGURAÇÕES ---
elif menu == "⚙️ Configurações":
    st.title("Gestão de Dados")
    st.write("Banco de Dados Atual (JSON):")
    st.json(carregar_clientes())
    
    if st.button("Limpar Banco de Dados (Reset)"):
        if os.path.exists(DB_FILE):
            os.remove(DB_FILE)
            st.rerun()
