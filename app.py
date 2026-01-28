import streamlit as st
import google.generativeai as genai
import tempfile
import os
import json
import re
import io
import time

# Tenta importar pypdf
try:
    import pypdf
except ImportError:
    st.error("⚠️ Biblioteca 'pypdf' não encontrada. Verifique o requirements.txt")
    st.stop()

# --- 1. Configuração Visual ---
st.set_page_config(
    page_title="Portal Auditor Eon",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
    .stApp { background-color: #0e1117; }
    .stButton>button { width: 100%; border-radius: 8px; height: 3em; font-weight: bold; border: none; }
    h1 { color: #ff4b4b; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. Autenticação e Diagnóstico ---
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

# --- 3. Funções Inteligentes (COM FALLBACK DE SEGURANÇA) ---

def tentar_modelo(nome_modelo, prompt, file_ref):
    """Tenta gerar conteúdo com um modelo específico. Retorna o resultado ou None se falhar."""
    try:
        model = genai.GenerativeModel(nome_modelo)
        # Tenta com temperature 0 para precisão
        res = model.generate_content([file_ref, prompt], generation_config={"temperature": 0.0})
        return res
    except Exception:
        return None

def processar_inteligente(pdf_path, prompt_texto, tipo_retorno="json"):
    """
    Tenta o Gemini 1.5 Pro. Se falhar (erro 404), tenta o Gemini 1.5 Flash.
    Se falhar, usa o Gemini 1.0 Pro (Tanque de Guerra).
    """
    file_ref = genai.upload_file(pdf_path)
    
    # 1. Tentativa: O melhor (1.5 Pro)
    modelos_para_tentar = ["models/gemini-1.5-pro", "gemini-1.5-pro"]
    
    # Se a biblioteca for velha, ela só aceita 'gemini-pro'
    try:
        if genai.__version__ < "0.4.0":
            modelos_para_tentar = ["gemini-pro"]
    except:
        pass # Se não der pra ler a versão, segue o jogo

    # Adiciona os fallbacks
    modelos_para_tentar.extend(["models/gemini-1.5-flash", "gemini-1.5-flash", "models/gemini-pro", "gemini-pro"])

    ultimo_erro = ""

    for modelo_nome in modelos_para_tentar:
        try:
            model = genai.GenerativeModel(modelo_nome)
            
            # Configuração específica para JSON se solicitado
            config = {"temperature": 0.0}
            if tipo_retorno == "json" and "1.5" in modelo_nome:
                config["response_mime_type"] = "application/json"
            
            res = model.generate_content([file_ref, prompt_texto], generation_config=config)
            
            # Se chegou aqui, funcionou!
            # Vamos mostrar qual modelo salvou a pátria (só pra debug)
            # st.toast(f"Usando modelo: {modelo_nome}") 
            
            if tipo_retorno == "json":
                return json.loads(res.text) if "1.5" in modelo_nome else limpar_json_manual(res.text)
            return limpar_json_manual(res.text)
            
        except Exception as e:
            ultimo_erro = str(e)
            continue # Tenta o próximo da lista

    # Se todos falharem
    raise Exception(f"Falha em todos os modelos. Último erro: {ultimo_erro}")

def limpar_json_manual(texto):
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
            if leitor.decrypt(senha):
                writer = pypdf.PdfWriter()
                for page in leitor.pages: writer.add_page(page)
                novo_buffer = io.BytesIO()
                writer.write(novo_buffer)
                novo_buffer.seek(0)
                return novo_buffer.getvalue(), 'ok'
            return None, 'senha_errada'
        return arquivo_bytes, 'ok'
    except: return None, 'erro_leitura'

# --- 4. Interface ---

col_logo, col_titulo = st.columns([1, 5])
with col_logo: st.markdown("# ⚡")
with col_titulo:
    st.title("Portal Auditor Eon")
    st.caption("Sistema Multi-Modelo (Auto-Recovery)")

st.markdown("---")

if 'etapa' not in st.session_state: st.session_state['etapa'] = 1
if 'pdf_processado' not in st.session_state: st.session_state['pdf_processado'] = None
if 'dados_fatura' not in st.session_state: st.session_state['dados_fatura'] = None

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
                    else: st.error("❌ Senha incorreta.")
                st.stop()
            elif status == 'ok':
                st.session_state['pdf_processado'] = pdf_final
            else:
                st.error("Erro no PDF.")
                st.stop()

        if st.session_state['pdf_processado']:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                tmp_file.write(st.session_state['pdf_processado'])
                tmp_path = tmp_file.name

            if st.session_state['etapa'] == 1:
                if st.button("▶️ Ler Fatura", type="primary"):
                    with st.status("Tentando conexão com IA...", expanded=True) as status:
                        try:
                            prompt_datas = 'Extraia as datas da conta (Leitura Anterior e Atual). JSON: { "inicio": "DD/MM", "fim": "DD/MM", "dias": "XX" }'
                            datas = processar_inteligente(tmp_path, prompt_datas, "json")
                            st.session_state['dados_fatura'] = datas
                            st.session_state['etapa'] = 2
                            status.update(label="✅ Feito!", state="complete", expanded=False)
                            st.rerun()
                        except Exception as e:
                            status.update(label="❌ Erro Fatal", state="error")
                            st.error(f"Erro: {e}")

            if st.session_state['etapa'] >= 2:
                datas = st.session_state['dados_fatura'] or {}
                st.markdown("---")
                st.subheader("☀️ 2. Usina")
                st.info(f"Período: **{datas.get('inicio', '?')}** a **{datas.get('fim', '?')}**")
                
                c1, c2 = st.columns([2, 1])
                geracao_input = c1.number_input("Geração (kWh):", min_value=0, step=10)
                
                if c2.button("🚀 Gerar Relatório", type="primary"):
                    with st.spinner("Analisando (isso pode levar alguns segundos)..."):
                        try:
                            prompt_analise = f"""
                            ATUE COMO: Auditor Técnico Sênior de Energia Solar.
                            INPUTS: Fatura (PDF) e Geração Inversor ({geracao_input} kWh).
                            
                            DIRETRIZES TÉCNICAS:
                            - Seja LITERAL com os dados da conta.
                            - Autoconsumo = {geracao_input} - Energia Injetada.
                            - Consumo Real = Consumo Rede + Autoconsumo.

                            SAÍDA JSON:
                            {{
                                "metricas": {{ "conta_atual": "R$", "sem_solar": "R$", "economia": "R$", "pct": "%" }},
                                "relatorio": "Texto markdown.",
                                "whatsapp": "Texto em tópicos."
                            }}
                            """
                            dados = processar_inteligente(tmp_path, prompt_analise, "json")
                            
                            st.markdown("---")
                            st.subheader("🎯 Resultado")
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