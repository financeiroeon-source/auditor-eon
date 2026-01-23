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
    st.header("🤖 Cérebro da IA")
    api_key = st.text_input("Cole sua Google API Key:", type="password")
    st.markdown("[Gerar Chave Gratuita](https://aistudio.google.com/app/apikey)")
    st.divider()
    st.caption("Usando modelo: **Gemini 1.5 Flash**")

# --- FUNÇÃO DE INTELIGÊNCIA ARTIFICIAL ---
def analisar_com_ia(texto_fatura, chave_api):
    try:
        # Configura a IA
        genai.configure(api_key=chave_api)
        
        # Usa o modelo mais moderno e leve (Flash)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = f"""
        Você é um auditor de faturas de energia elétrica.
        Analise o texto extraído do PDF abaixo e retorne um JSON.
        
        Se encontrar números como "11013876", IGNORE, pois é leitura de medidor.
        Busque valores de consumo real (geralmente entre 100 e 5000 kWh).
        
        Campos Obrigatórios no JSON:
        - "consumo_kwh": (float) O consumo ativo faturado.
        - "injetada_kwh": (float) Energia injetada/compensada da GD. Se não tiver, use 0.0.
        - "valor_total": (float) Valor final da conta (R$).
        - "custos_extras": (float) Soma de CIP, Multas e Juros.
        - "nome": (string) Nome do cliente.
        - "cidade": (string) Cidade.
        - "distribuidora": (string) Concessionária.
        - "mes_referencia": (string) Mês/Ano.

        Texto da Fatura:
        {texto_fatura}
        """
        
        # Gera a resposta
        response = model.generate_content(prompt)
        
        # Limpa a resposta para pegar só o JSON
        texto_limpo = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(texto_limpo)

    except Exception as e:
        st.error(f"Erro na IA: {e}")
        return None

# --- LEITOR DE PDF ---
def ler_pdf(arquivo):
    texto = ""
    with fitz.open(stream=arquivo.read(), filetype="pdf") as doc:
        for page in doc:
            texto += page.get_text() + "\n"
    return texto

# --- TELA PRINCIPAL ---
st.title("⚡ Auditor-Eon: IA Generativa")

if 'dados_lidos' not in st.session_state:
    st.session_state['dados_lidos'] = None

# UPLOAD
uploaded_file = st.file_uploader("Arraste sua conta de luz (PDF)", type=["pdf"])

if uploaded_file and not api_key:
    st.warning("👈 Cole sua API Key na barra lateral para iniciar.")

if uploaded_file and api_key and st.session_state['dados_lidos'] is None:
    with st.spinner("A IA está analisando a fatura..."):
        texto = ler_pdf(uploaded_file)
        dados_ia = analisar_com_ia(texto, api_key)
        
        if dados_ia:
            st.session_state['dados_lidos'] = dados_ia
            st.success("Análise Concluída!")
            st.rerun()

# CALIBRAGEM
if st.session_state['dados_lidos']:
    dados = st.session_state['dados_lidos']
    
    st.divider()
    st.subheader("🛠️ Passo 2: Calibragem")
    
    c1, c2, c3 = st.columns(3)
    with c1: dados['consumo_kwh'] = st.number_input("Consumo (kWh):", value=float(dados.get('consumo_kwh', 0)))
    with c2: dados['injetada_kwh'] = st.number_input("Injetada (kWh):", value=float(dados.get('injetada_kwh', 0)))
    with c3: dados['valor_total'] = st.number_input("Valor (R$):", value=float(dados.get('valor_total', 0)))

    st.markdown("---")
    
    col_info, col_inp = st.columns([1, 1])
    with col_info: st.info("Insira a Geração Total do Inversor:")
    with col_inp:
        geracao_inversor = st.number_input("Geração Total (kWh):", min_value=0.0, value=float(dados.get('injetada_kwh', 0)))

    if st.button("GERAR AUDITORIA 🚀", type="primary"):
        res = realizar_auditoria_gd(dados, geracao_inversor)
        
        st.markdown("---")
        st.markdown(f"### 📊 Relatório: {dados.get('nome', 'Cliente')}")
        
        if "Confirmada" in res['selo']: st.markdown(f'<div class="selo-verde">{res["selo"]}</div>', unsafe_allow_html=True)
        else: st.markdown(f'<div class="selo-amarelo">{res["selo"]}</div>', unsafe_allow_html=True)
            
        st.divider()
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Economia Real", f"R$ {res['economia_reais']:.2f}")
        k2.metric("Economia (%)", f"{res['economia_perc']:.1f}%")
        k3.metric("Autoconsumo", f"{res['consumo_instantaneo']:.0f} kWh")
        k4.metric("Conta Sem Solar", f"R$ {res['conta_sem_solar']:.2f}")
        
        st.divider()
        ce, cd = st.columns(2)
        with ce:
            st.subheader("⚡ Energia")
            st.dataframe(pd.DataFrame({"Item": ["Consumo Rede", "Geração Total", "Autoconsumo", "Carga Real"], "Valor": [dados['consumo_kwh'], geracao_inversor, res['consumo_instantaneo'], res['carga_total']]}), hide_index=True, use_container_width=True)
        with cd:
            st.subheader("💸 Financeiro")
            st.dataframe(pd.DataFrame({"Item": ["Fatura Atual", "Custos Extras"], "Valor": [dados['valor_total'], dados.get('custos_extras', 0)]}), hide_index=True, use_container_width=True)

    if st.button("Nova Análise"):
        st.session_state['dados_lidos'] = None
        st.rerun()
