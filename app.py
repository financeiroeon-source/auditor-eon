import streamlit as st
import google.generativeai as genai
import tempfile
import os
import json
import re
import io
import time # Adicionado para pausas de segurança

# Tenta importar pypdf para desbloquear senhas
try:
    import pypdf
except ImportError:
    st.error("⚠️ Biblioteca 'pypdf' não encontrada. No terminal, rode: pip install pypdf")
    st.stop()

# --- 1. Configuração Visual (MANTIDA IGUAL) ---
st.set_page_config(
    page_title="Portal Auditor Eon",
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

# --- 2. Autenticação (MANTIDA IGUAL) ---
try:
    if "GOOGLE_API_KEY" in st.secrets:
        api_key = st.secrets["GOOGLE_API_KEY"]
        genai.configure(api_key=api_key)
    else:
        st.error("⚠️ ERRO: Configure o arquivo .streamlit/secrets.toml")
        st.stop()
except Exception as e:
    st.error(f"Erro de conexão: {e}")
    st.stop()

# --- 3. Funções Inteligentes (ATUALIZADAS PARA MODO PRO) ---

def selecionar_modelo_pro():
    # Tenta listar os modelos disponíveis na sua conta para pegar o nome exato
    try:
        modelos = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        # 1. Tenta o PRO mais recente
        for m in modelos:
            if "gemini-1.5-pro" in m: return m
            
        # 2. Se não achar o PRO, tenta o 2.0 Flash (que é melhor que o 1.5 Flash)
        for m in modelos:
            if "gemini-2.0-flash" in m: return m
            
        # 3. Fallback para o clássico
        return "models/gemini-1.5-flash"
    except:
        # Se der erro na listagem, usa o nome padrão seguro
        return "models/gemini-1.5-flash"

def limpar_json(texto):
    try:
        match = re.search(r'\{.*\}', texto, re.DOTALL)
        if match: return json.loads(match.group(0))
        return json.loads(texto)
    except:
        return {} 

def verificar_e_desbloquear_pdf(arquivo_bytes, senha=None):
    """
    Verifica se o PDF está bloqueado e tenta desbloquear.
    """
    try:
        buffer = io.BytesIO(arquivo_bytes)
        leitor = pypdf.PdfReader(buffer)
        
        if leitor.is_encrypted:
            if not senha:
                return None, 'bloqueado'
            
            # Tenta desbloquear com a senha
            try:
                if leitor.decrypt(senha):
                    # Cria novo PDF desbloqueado
                    writer = pypdf.PdfWriter()
                    for page in leitor.pages:
                        writer.add_page(page)
                    
                    novo_buffer = io.BytesIO()
                    writer.write(novo_buffer)
                    novo_buffer.seek(0)
                    return novo_buffer.getvalue(), 'ok'
                else:
                    return None, 'senha_errada'
            except:
                return None, 'senha_errada'
        
        return arquivo_bytes, 'ok' # Não estava bloqueado
    except Exception as e:
        return None, f"erro_leitura: {e}"

def extrair_datas(pdf_path, modelo):
    # Pausa técnica para evitar erro 429 (Too Many Requests) no plano gratuito
    time.sleep(1)
    
    model = genai.GenerativeModel(modelo)
    file_ref = genai.upload_file(pdf_path)
    prompt = 'Extraia as datas da conta (Leitura Anterior e Atual). JSON: { "inicio": "DD/MM", "fim": "DD/MM", "dias": "XX" }'
    try:
        # Temperature 0.0 = Criatividade Zero (Consistência)
        res = model.generate_content([file_ref, prompt], generation_config={"temperature": 0.0})
        return limpar_json(res.text)
    except:
        return {"inicio": "?", "fim": "?", "dias": "?"}

def analisar_performance_completa(pdf_path, modelo, geracao_usuario):
    # Pausa técnica: O modelo Pro é pesado, damos 2s para o Google respirar
    time.sleep(2)
    
    model = genai.GenerativeModel(modelo)
    file_ref = genai.upload_file(pdf_path)
    
    # --- PROMPT MANTIDO EXATAMENTE IGUAL ---
    prompt = f"""
    ATUE COMO: Auditor Técnico Sênior de Energia Solar.
    
    INPUTS:
    1. Fatura de Energia (PDF).
    2. Geração Real do Inversor: {geracao_usuario} kWh.

    DIRETRIZES TÉCNICAS:
    - Autoconsumo = {geracao_usuario} - Energia Injetada.
    - Consumo Real = Consumo Rede + Autoconsumo.
    - Fio B: Identifique o valor pago.
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
        "whatsapp": "Mensagem formatada em TÓPICOS (Lista com emojis). DEVE CONTER OBRIGATORIAMENTE: 1. Comparativo (Atual vs Sem Solar) e Economia. 2. Dados Técnicos (Geração, Injeção e Autoconsumo calculado). 3. Custo do Fio B (se houver). 4. Status do Mínimo. Mantenha tom consultivo, amigável e detalhista."
    }}
    """
    
    try:
        # Temperature 0.0 aqui também!
        res = model.generate_content(
            [file_ref, prompt], 
            generation_config={"response_mime_type": "application/json", "temperature": 0.0}
        )
        return json.loads(res.text)
    except:
        # Fallback também com temperatura zero
        res = model.generate_content([file_ref, prompt], generation_config={"temperature": 0.0})
        return limpar_json(res.text)

# --- 4. Interface ---

# Agora chamamos a função PRO
modelo_ativo = selecionar_modelo_pro()

col_logo, col_titulo = st.columns([1, 5])
with col_logo: st.markdown("# ⚡")
with col_titulo:
    st.title("Portal Auditor Eon")
    # Atualizei o caption para você saber que está rodando o Pro
    st.caption(f"Motor IA: {modelo_ativo} | Precisão Máxima (Temp 0.0)")

st.markdown("---")

# Inicialização de Variáveis de Sessão
if 'dados_fatura' not in st.session_state: st.session_state['dados_fatura'] = None
if 'etapa' not in st.session_state: st.session_state['etapa'] = 1
if 'pdf_processado' not in st.session_state: st.session_state['pdf_processado'] = None

container = st.container()

with container:
    st.subheader("📂 1. Nova Análise")
    uploaded_file = st.file_uploader("Upload da Fatura", type=["pdf"], label_visibility="collapsed")

    if uploaded_file:
        # --- LÓGICA DE SENHA (MANTIDA) ---
        if st.session_state['pdf_processado'] is None:
            bytes_iniciais = uploaded_file.getvalue()
            pdf_final, status = verificar_e_desbloquear_pdf(bytes_iniciais)
            
            if status == 'bloqueado':
                st.warning("🔒 Arquivo protegido por senha.")
                col_pass, col_ok = st.columns([3, 1])
                senha = col_pass.text_input("Digite a senha (geralmente 5 primeiros dígitos do CPF):", type="password")
                
                if senha:
                    pdf_desbloqueado, status_senha = verificar_e_desbloquear_pdf(bytes_iniciais, senha)
                    if status_senha == 'ok':
                        st.session_state['pdf_processado'] = pdf_desbloqueado
                        st.success("🔓 Desbloqueado!")
                        st.rerun()
                    else:
                        st.error("❌ Senha incorreta.")
                st.stop() # Para aqui até desbloquear
            
            elif status == 'ok':
                st.session_state['pdf_processado'] = pdf_final
            else:
                st.error(f"Erro no PDF: {status}")
                st.stop()

        # --- FLUXO NORMAL (Usando o PDF processado) ---
        if st.session_state['pdf_processado']:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                tmp_file.write(st.session_state['pdf_processado'])
                tmp_path = tmp_file.name

            if st.session_state['etapa'] == 1:
                if st.button("▶️ Ler Fatura", type="primary"):
                    with st.status("Lendo dados (Modo Pro)...", expanded=True) as status:
                        try:
                            datas = extrair_datas(tmp_path, modelo_ativo)
                            st.session_state['dados_fatura'] = datas
                            st.session_state['etapa'] = 2
                            status.update(label="✅ Sucesso!", state="complete", expanded=False)
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
                        with st.spinner("Auditor trabalhando (Pode levar ~15 seg)..."):
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
                                st.error(f"Erro na análise: {e}. Se for '429', aguarde 1 minuto.")
                    else:
                        st.warning("Digite a geração.")
    else:
        # Reseta se o usuário remover o arquivo da tela
        st.session_state['pdf_processado'] = None