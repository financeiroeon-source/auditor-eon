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

# --- BARRA LATERAL PARA CONFIGURAÇÃO ---
with st.sidebar:
    st.header("🤖 Configuração da IA")
    api_key = st.text_input("Cole sua Google API Key aqui:", type="password", help="Pegue sua chave gratuita no Google AI Studio")
    st.markdown("[Criar Chave Gratuita (Google AI Studio)](https://aistudio.google.com/app/apikey)")
    st.divider()
    st.info("Esta versão usa o modelo **Gemini Flash** para ler a fatura como um humano.")

# --- FUNÇÃO QUE CHAMA A IA (O CÉREBRO) ---
def analisar_com_ia(texto_fatura, chave_api):
    try:
        genai.configure(api_key=chave_api)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = f"""
        Você é um Auditor de Energia Especialista (Auditor-Eon).
        Analise o texto extraído de uma fatura de energia elétrica abaixo e extraia os dados em formato JSON estrito.
        
        Regras de Extração:
        1. 'consumo_kwh': O consumo faturado ou energia ativa da rede (kWh).
        2. 'injetada_kwh': A energia injetada, compensada ou GD (kWh). Se não houver menção explicita de injeção/GD, assuma 0.0.
        3. 'valor_total': O valor total a pagar da fatura (R$).
        4. 'custos_extras': Soma de Contribuição Ilum. Pública (CIP), Multas e Juros (R$).
        5. 'nome': Nome do cliente.
        6. 'cidade': Cidade do cliente (se houver).
        7. 'distribuidora': Nome da concessionária (Ex: CPFL, Enel, Cemig).
        8. 'mes_referencia': Mês/Ano da conta.

        TEXTO DA FATURA:
        {texto_fatura}

        Retorne APENAS o JSON, sem markdown (```json).
        """
        
        response = model.generate_content(prompt)
        # Limpeza do resultado para garantir JSON puro
        json_str = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(json_str)
        
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
st.title("⚡ Auditor-Eon: Análise via IA Generativa")

if 'dados_lidos' not in st.session_state:
    st.session_state['dados_lidos'] = None

# 1. UPLOAD
uploaded_file = st.file_uploader("Upload da Fatura (PDF)", type=["pdf"])

if uploaded_file and not api_key:
    st.warning("⚠️ Por favor, insira sua API Key na barra lateral para ativar a IA.")

if uploaded_file and api_key and st.session_state['dados_lidos'] is None:
    with st.spinner("🤖 A IA está lendo e interpretando sua conta..."):
        # 1. Extrai texto
        texto_pdf = ler_pdf(uploaded_file)
        # 2. Envia para o Gemini
        dados_ia = analisar_com_ia(texto_pdf, api_key)
        
        if dados_ia:
            st.session_state['dados_lidos'] = dados_ia
            st.success("Leitura Inteligente Concluída!")
            st.rerun()

# 2. CALIBRAGEM E RESULTADOS
if st.session_state['dados_lidos']:
    dados = st.session_state['dados_lidos']
    
    st.divider()
    st.subheader("🛠️ Passo 2: Conferência (Dados extraídos pela IA)")
    
    # Checkpoint de correção
    c1, c2, c3 = st.columns(3)
    with c1: dados['consumo_kwh'] = st.number_input("Consumo (kWh):", value=float(dados.get('consumo_kwh', 0)))
    with c2: dados['injetada_kwh'] = st.number_input("Injetada (kWh):", value=float(dados.get('injetada_kwh', 0)))
    with c3: dados['valor_total'] = st.number_input("Valor (R$):", value=float(dados.get('valor_total', 0)))

    st.markdown("---")
    
    col_info, col_input = st.columns([1, 1])
    with col_info:
        st.info("💡 **Dica do Auditor:** A IA leu a conta, mas a geração do inversor só você tem acesso (pelo App).")
    
    with col_input:
        geracao_inversor = st.number_input(
            "Geração Total do Inversor (kWh):", 
            min_value=0.0,
            value=float(dados.get('injetada_kwh', 0))
        )

    if st.button("GERAR RELATÓRIO COMPLETO 🚀", type="primary"):
        res = realizar_auditoria_gd(dados, geracao_inversor)
        
        st.markdown("---")
        st.markdown(f"### 📊 Relatório: {dados.get('nome', 'Cliente')}")
        
        # Selo
        if "Confirmada" in res['selo']: st.markdown(f'<div class="selo-verde">{res["selo"]}</div>', unsafe_allow_html=True)
        else: st.markdown(f'<div class="selo-amarelo">{res["selo"]}</div>', unsafe_allow_html=True)
            
        st.divider()
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Economia Real", f"R$ {res['economia_reais']:.2f}")
        k2.metric("Economia (%)", f"{res['economia_perc']:.1f}%")
        k3.metric("Autoconsumo", f"{res['consumo_instantaneo']:.0f} kWh")
        k4.metric("Conta Sem Solar", f"R$ {res['conta_sem_solar']:.2f}")
        
        st.divider()
        c_esq, c_dir = st.columns(2)
        with c_esq:
            st.subheader("⚡ Energia")
            st.dataframe(pd.DataFrame({"Item": ["Consumo Rede", "Geração Total", "Autoconsumo", "Carga Real"], "Valor": [dados['consumo_kwh'], geracao_inversor, res['consumo_instantaneo'], res['carga_total']]}), hide_index=True, use_container_width=True)
        with c_dir:
            st.subheader("💸 Financeiro")
            st.dataframe(pd.DataFrame({"Item": ["Fatura Atual", "Custos Extras"], "Valor": [dados['valor_total'], dados.get('custos_extras', 0)]}), hide_index=True, use_container_width=True)

    if st.button("Nova Análise"):
        st.session_state['dados_lidos'] = None
        st.rerun()
