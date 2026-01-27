import streamlit as st
import google.generativeai as genai
import tempfile
import os
import json
import re
import io

# Tenta importar pypdf
try:
    import pypdf
except ImportError:
    st.error("⚠️ Biblioteca 'pypdf' não encontrada. Verifique o requirements.txt")
    st.stop()

# --- 1. Configuração Visual ---
st.set_page_config(
    page_title="Portal Auditor Eon (PRO)",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
    .stApp { background-color: #0e1117; }
    
    [data-testid="stMetric"] {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.2);
        border: 1px solid #e0e0e0;
    }
    [data-testid="stMetricLabel"] { color: #666666 !important; font-size: 14px; }
    [data-testid="stMetricValue"] { color: #1f1f1f !important; font-weight: bold; }

    .stButton>button {
        width: 100%;
        border-radius: 8px;
        height: 3em;
        font-weight: bold;
        border: none;
    }
    
    h1 { color: #ff4b4b; }
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

# --- 2. Autenticação ---
try:
    if "GOOGLE_API_KEY" in st.secrets:
        api_key = st.secrets["GOOGLE_API_KEY"]
        genai.configure(api_key=api_key)
    else:
        st.error("⚠️ Configure a chave API nos 'Secrets'.")
        st.stop()
except Exception as e:
    st.error(f"Erro de conexão: {e}")
    st.stop()

# --- 3. Funções Inteligentes (MODO PRO ATIVADO) ---

def selecionar_modelo_pro():
    # Agora que você paga, usamos o MELHOR sem medo.
    return "models/gemini-1.5-pro"

def limpar_json(texto):
    try:
        match = re.search(r'\{.*\}', texto, re.DOTALL)
        if match: return json.loads(match.group(0))
        return json.loads(texto)
    except:
        return {} 

def verificar_e_desbloquear_pdf(arquivo_bytes, senha=None):
    try:
        buffer = io.BytesIO(arquivo_bytes)
        leitor = pypdf.PdfReader(buffer)
        
        if leitor.is_encrypted:
            if not senha: return None, 'bloqueado'
            try:
                if leitor.decrypt(senha):
                    writer = pypdf.PdfWriter()
                    for page in leitor.pages: writer.add_page(page)
                    novo_buffer = io.BytesIO()
                    writer.write(novo_buffer)
                    novo_buffer.seek(0)
                    return novo_buffer.getvalue(), 'ok'
                else: return None, 'senha_errada'
            except: return None, 'senha_errada'
        return arquivo_bytes, 'ok'
    except Exception as e:
        return None, f"erro_leitura: {e}"

def extrair_datas(pdf_path, modelo):
    # Sem time.sleep() -> Velocidade Máxima 🚀
    model = genai.GenerativeModel(modelo)
    file_ref = genai.upload_file(pdf_path)
    prompt = 'Extraia as datas da conta (Leitura Anterior e Atual). JSON: { "inicio": "DD/MM", "fim": "DD/MM", "dias": "XX" }'
    try:
        # Temperature 0.0 para precisão máxima
        res = model.generate_content([file_ref, prompt], generation_config={"temperature": 0.0})
        return limpar_json(res.text)
    except:
        return {"inicio": "?", "fim": "?", "dias": "?"}

def analisar_performance_completa(pdf_path, modelo, geracao_usuario):
    # Sem time.sleep() -> O Google Cloud aguenta o tranco agora.
    model = genai.GenerativeModel(modelo)
    file_ref = genai.upload_file(pdf_path)
    
    prompt = f"""
    ATUE COMO: Auditor Técnico Sênior de Energia Solar.
    
    INPUTS:
    1. Fatura de Energia (PDF).
    2. Geração Real do Inversor: {geracao_usuario} kWh.

    DIRETRIZES TÉCNICAS RÍGIDAS (Seja Literal):
    - Autoconsumo = {geracao_usuario} - Energia Injetada (Valor exato da conta).
    - Consumo Real = Consumo Rede + Autoconsumo.
    - Fio B: Identifique o valor pago explicitamente.
    - Mínimo: Verifique se o consumo da rede superou o mínimo (30/50/100).

    SAÍDA OBRIGATÓRIA (JSON puro):
    {{
        "metricas": {{
            "conta_atual": "R$ Valor",
            "sem_solar": "R$ Valor Estimado",
            "economia": "R$ Valor",
            "pct": "XX%"
        }},
        "relatorio": "Relatório Markdown detalhado com tabelas e explicação técnica.",
        "whatsapp": "Mensagem formatada em TÓPICOS (Lista com emojis). DEVE CONTER OBRIGATORIAMENTE: 1. Comparativo (Atual vs Sem Solar) e Economia. 2. Dados Técnicos (Geração, Injeção e Autoconsumo calculado). 3. Custo do Fio B (se houver). 4. Status do Mínimo."
    }}
    """
    
    try:
        res = model.generate_content(
            [file_ref, prompt], 
            generation_config={"response_mime_type": "application/json", "temperature": 0.0}
        )
        return json.loads(res.text)
    except:
        res = model.generate_content([file_ref, prompt], generation_config={"temperature": 0.0})
        return limpar_json(res.text)

# --- 4. Interface ---

modelo_ativo = selecionar_modelo_pro()

col_logo, col_titulo = st.columns([1, 5])
with col_logo: st.markdown("# ⚡")
with col_titulo:
    st.title("Portal Auditor Eon (PRO)")
    st.caption(f"Motor: {modelo_ativo} | Plano: Enterprise/Pago")

st.markdown("---")

if 'dados_fatura' not in st.session_state: st.session_state['dados_fatura'] = None
if 'etapa' not in st.session_state: st.session_state['etapa'] = 1
if 'pdf_processado' not in st.session_state: st.session_state['pdf_processado'] = None

container = st.container()

with container:
    st.subheader("📂 1. Nova Análise")
    uploaded_file = st.file_uploader("Upload da Fatura", type=["pdf"], label_visibility="collapsed")

    if uploaded_file:
        if st.session_state['pdf_processado'] is None:
            bytes_iniciais = uploaded_file.getvalue()
            pdf_final, status = verificar_e_desbloquear_pdf(bytes_iniciais)
            
            if status == 'bloqueado':
                st.warning("🔒 Arquivo protegido.")
                col_pass, col_ok = st.columns([3, 1])
                senha = col_pass.text_input("Senha (CPF):", type="password")
                if senha:
                    pdf_desbloqueado, status_senha = verificar_e_desbloquear_pdf(bytes_iniciais, senha)
                    if status_senha == 'ok':
                        st.session_state['pdf_processado'] = pdf_desbloqueado
                        st.success("🔓 Sucesso!")
                        st.rerun()
                    else:
                        st.error("❌ Senha incorreta.")
                st.stop()
            elif status == 'ok':
                st.session_state['pdf_processado'] = pdf_final
            else:
                st.error(f"Erro: {status}")
                st.stop()

        if st.session_state['pdf_processado']:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                tmp_file.write(st.session_state['pdf_processado'])
                tmp_path = tmp_file.name

            if st.session_state['etapa'] == 1:
                if st.button("▶️ Ler Fatura", type="primary"):
                    with st.status("Processando dados...", expanded=True) as status:
                        try:
                            datas = extrair_datas(tmp_path, modelo_ativo)
                            st.session_state['dados_fatura'] = datas
                            st.session_state['etapa'] = 2
                            status.update(label="✅ Leitura concluída!", state="complete", expanded=False)
                            st.rerun()
                        except Exception as e:
                            status.update(label="❌ Erro", state="error")
                            st.error(str(e))

            if st.session_state['etapa'] >= 2:
                datas = st.session_state['dados_fatura'] or {}
                st.markdown("---")
                st.subheader("☀️ 2. Usina")
                st.info(f"Período: **{datas.get('inicio', '?')}** a **{datas.get('fim', '?')}**")
                
                c1, c2 = st.columns([2, 1])
                geracao_input = c1.number_input("Geração (kWh):", min_value=0, step=10)
                
                if c2.button("🚀 Gerar Relatório", type="primary"):
                    if geracao_input > 0:
                        with st.spinner("O Auditor PRO está analisando..."):
                            try:
                                dados = analisar_performance_completa(tmp_path, modelo_ativo, geracao_input)
                                
                                st.markdown("---")
                                st.subheader("🎯 Resultado Financeiro")
                                
                                met = dados.get("metricas", {})
                                k1, k2, k3, k4 = st.columns(4)
                                k1.metric("Atual", met.get("conta_atual", "-"))
                                k2.metric("Sem Solar", met.get("sem_solar", "-"), delta="Evitado", delta_color="inverse")
                                k3.metric("Economia", met.get("economia", "-"))
                                k4.metric("ROI", met.get("pct", "-"))

                                with st.expander("📄 Relatório Técnico", expanded=True):
                                    st.markdown(dados.get("relatorio", ""))

                                st.success("📲 WhatsApp:")
                                st.code(dados.get("whatsapp", ""), language="text")
                                
                                if st.button("Nova Análise"):
                                    st.session_state['etapa'] = 1
                                    st.session_state['pdf_processado'] = None
                                    st.rerun()
                            except Exception as e:
                                st.error(f"Erro: {e}")
                    else:
                        st.warning("Digite a geração.")
    else:
        st.session_state['pdf_processado'] = None