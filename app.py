import streamlit as st
import pandas as pd
import fitz  # PyMuPDF
import google.generativeai as genai
import json
from calculos import realizar_auditoria_gd

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Auditor-Eon AI", layout="wide")

st.markdown("""
    <style>
    .selo-verde { padding: 15px; border-radius: 8px; background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb; text-align: center; font-weight: bold; font-size: 18px; }
    .selo-amarelo { padding: 15px; border-radius: 8px; background-color: #fff3cd; color: #856404; border: 1px solid #ffeeba; text-align: center; font-weight: bold; font-size: 18px; }
    .stButton>button { width: 100%; border-radius: 8px; height: 50px; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# --- BARRA LATERAL ---
with st.sidebar:
    st.header("🤖 Configuração da IA")
    api_key = st.text_input("Cole sua Google API Key:", type="password")
    st.markdown("[Gerar Chave Gratuita](https://aistudio.google.com/app/apikey)")
    st.divider()
    st.info("Sistema configurado para diferenciar Consumo Físico de Consumo Faturado (Disp).")

# --- FUNÇÃO: ESCOLHE O MELHOR MODELO (SEM ERRO 404) ---
def obter_modelo_disponivel():
    try:
        modelos = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                modelos.append(m.name)
        if not modelos: return "gemini-pro"
        
        # Prioridade: Flash > Pro 1.5 > Pro 1.0
        for m in modelos:
            if 'flash' in m and '1.5' in m: return m
        for m in modelos:
            if 'pro' in m and '1.5' in m: return m
            
        return modelos[0]
    except:
        return "gemini-pro"

# --- CÉREBRO DA IA (PROMPT ATUALIZADO) ---
def analisar_com_ia(texto_fatura, chave_api):
    try:
        genai.configure(api_key=chave_api)
        nome_modelo = obter_modelo_disponivel()
        model = genai.GenerativeModel(nome_modelo)
        
        prompt = f"""
        Você é um auditor especialista em Geração Distribuída (GD).
        Analise o texto da fatura e extraia os dados com precisão cirúrgica.
        
        DIFERENCIAÇÃO IMPORTANTE:
        1. "consumo_rede_kwh": É a ENERGIA TOTAL que entrou na unidade (Energia Ativa Injetada pela Concessionária). Se houver postos tarifários (Ponta/Fora Ponta), SOME ELES.
        2. "consumo_faturado_kwh": É a energia que foi EFETIVAMENTE COBRADA. 
           - Em contas com Solar (GD), se a geração cobriu tudo, este valor será o Custo de Disponibilidade (30, 50 ou 100 kWh).
           - Se não tiver solar, geralmente é igual ao consumo da rede.
        
        IGNORE números gigantes (ex: 11013876) que são leituras de medidor.
        
        Retorne APENAS um JSON com estes campos:
        - "consumo_rede_kwh": (float) Total físico consumido da rede.
        - "consumo_faturado_kwh": (float) Total faturado (Disponibilidade ou saldo).
        - "injetada_kwh": (float) Energia injetada/compensada. Use 0.0 se não achar.
        - "valor_total": (float) Valor monetário total (R$).
        - "custos_extras": (float) Soma de CIP, Multas e Juros.
        - "nome": (string) Nome do Cliente.
        - "cidade": (string) Cidade.
        - "distribuidora": (string) Concessionária.
        - "mes_referencia": (string) Mês/Ano.

        Texto da Fatura:
        {texto_fatura}
        """
        
        response = model.generate_content(prompt)
        texto_limpo = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(texto_limpo)

    except Exception as e:
        st.error(f"Erro na IA ({nome_modelo}): {e}")
        return None

# --- LEITOR PDF ---
def ler_pdf(arquivo):
    texto = ""
    with fitz.open(stream=arquivo.read(), filetype="pdf") as doc:
        for page in doc:
            texto += page.get_text() + "\n"
    return texto

# --- TELA PRINCIPAL ---
st.title("⚡ Auditor-Eon: Análise Detalhada (Rede vs Faturado)")

if 'dados_lidos' not in st.session_state:
    st.session_state['dados_lidos'] = None

# UPLOAD
uploaded_file = st.file_uploader("Arraste sua conta de luz (PDF)", type=["pdf"])

if uploaded_file and not api_key:
    st.warning("👈 Insira sua API Key na barra lateral.")

if uploaded_file and api
