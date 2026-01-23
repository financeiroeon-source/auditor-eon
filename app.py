import streamlit as st
import pandas as pd
import fitz  # PyMuPDF: O leitor rápido
import re
from calculos import realizar_auditoria_gd

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Auditor-Eon Pro", layout="wide")

# CSS CORRIGIDO (unsafe_allow_html=True)
st.markdown("""
    <style>
    .selo-verde { 
        padding: 15px; border-radius: 8px; background-color: #d4edda; 
        color: #155724; border: 1px solid #c3e6cb; text-align: center; font-weight: bold; font-size: 18px; 
    }
    .selo-amarelo { 
        padding: 15px; border-radius: 8px; background-color: #fff3cd; 
        color: #856404; border: 1px solid #ffeeba; text-align: center; font-weight: bold; font-size: 18px; 
    }
    </style>
""", unsafe_allow_html=True)

st.title("⚡ Auditor-Eon: Sistema Otimizado")

# --- FUNÇÃO DE LIMPEZA DE TEXTO ---
def limpar_numero(texto):
    if not texto:
        return 0.0
    try:
        texto = texto.lower().replace('r$', '').strip()
        if ',' in texto and '.' in texto:
            texto = texto.replace('.', '').replace(',', '.')
        elif ',' in texto:
            texto = texto.replace(',', '.')
        return float(texto)
    except:
        return 0.0

# --- FUNÇÃO DE LEITURA (PyMuPDF) ---
def extrair_dados_pdf(arquivo):
    dados = {
        'nome': 'Não Identificado',
        'cidade': 'Não Identificada',
        'distribuidora': 'Concessionária Padrão',
        'mes_referencia': 'Mês Atual',
        'consumo_kwh': 0.0,
        'injetada_kwh': 0.0,
        'valor_total': 0.0,
        'custos_extras': 0.0
    }
    
    texto_completo = ""
    try:
        with fitz.open(stream=arquivo.read(), filetype="pdf") as doc:
            for page in doc:
                texto_completo += page.get_text("text") + "\n"
    except Exception as e:
        st.error(f"Erro na leitura: {e}")
        return dados

    # Regex Otimizada
    match_valor = re.search(r'(?:Total a pagar|Valor Total|Vencimento).*?R\$\s*([\d\.,]+)', texto_completo, re.IGNORECASE)
    if match_valor:
        dados['valor_total'] = limpar_numero(match_valor.group(1))

    match_consumo = re.search(r'(?:Consumo|Ativa|Fornecimento).*?(\d[\d\.,]*)\s*kWh', texto_completo, re.IGNORECASE)
    if not match_consumo:
        match_consumo = re.search(r'kWh\s.*?(\d[\d\.,]*)', texto_completo, re.IGNORECASE)
    if match_consumo:
        dados['consumo_kwh'] = limpar_numero(match_consumo.group(1))

    match_injetada = re.search(r'(?:Injetada|Injeção|Compensada).*?(\d[\d\.,]*)\s*kWh', texto_completo, re.IGNORECASE)
    if match_injetada:
        dados['injetada_kwh'] = limpar_numero(match_injetada.group(1))

    match_cip = re.search(r'(?:Contrib|Ilum|CIP).*?R\$\s*([\d\.,]+)', texto_completo, re.IGNORECASE)
    if match_cip:
        dados['custos_extras'] = limpar_numero(match_cip.group(1))
        
    return dados

# --- APLICAÇÃO ---
if 'dados_lidos' not in st.session_state:
    st.session_state['dados_lidos'] = None

uploaded_file = st.file_uploader("Upload da Fatura (PDF)", type=["pdf"])

if uploaded_file is not None and st.session_state['dados_lidos'] is None:
    with st.spinner("Lendo PDF..."):
        dados_extraidos = extrair_dados_pdf(uploaded_file)
        st.session_state['dados_lidos'] = dados_extraidos
        st.success("Leitura Concluída!")
        st.rerun()

if st.session_state['dados_lidos']:
    dados = st.session_state['dados_lidos']
    
    st.divider()
    st.subheader("🛠️ Passo 2: Calibragem")
    
    c1, c2, c3 = st.columns(3)
    with c1:
        dados['consumo_kwh'] = st.number_input("Consumo Lido (kWh):", value=float(dados['consumo_kwh']))
    with c2:
        dados['injetada_kwh'] = st.number_input("Injetada Lido (kWh):", value=float(dados['injetada_kwh']))
    with c3:
        dados['valor_total'] = st.number_input("Valor Conta (R$):", value=float(dados['valor_total']))

    st.markdown("---")
    
    col_info, col_input = st.columns([1, 1])
    with col_info:
        st.info("Insira a Geração Total do Inversor:")
    
    with col_input:
        geracao_inversor = st.number_input(
            "Geração Total (kWh):", 
            min_value=0.0,
            value=float(dados.get('injetada_kwh', 0))
        )

    if st.button("Gerar Auditoria Completa 🚀", type="primary"):
        res = realizar_auditoria_gd(dados, geracao_inversor)
        
        st.markdown("---")
        st.markdown(f"### 📊 Resultado")
        
        if "Confirmada" in res['selo']:
            st.markdown(f'<div class="selo-verde">{res["selo"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="selo-amarelo">{res["selo"]}</div>', unsafe_allow_html=True)
            
        st.divider()

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Economia Real", f"R$ {res['economia_reais']:.2f}")
        k2.metric("Economia (%)", f"{res['economia_perc']:.1f}%")
        k3.metric("Autoconsumo", f"{res['consumo_instantaneo']:.0f} kWh")
        k4.metric("Conta Sem Solar", f"R$ {res['conta_sem_solar']:.2f}")

        st.divider()
        
        col_esq, col_dir = st.columns(2)
        with col_esq:
            st.subheader("⚡ Energia")
            df_en = pd.DataFrame({
                "Item": ["Consumo Rede", "Geração Total", "Autoconsumo", "Carga Real"],
                "Valor": [dados['consumo_kwh'], geracao_inversor, res['consumo_instantaneo'], res['carga_total']]
            })
            st.dataframe(df_en, hide_index=True, use_container_width=True)
            
        with col_dir:
            st.subheader("💸 Financeiro")
            df_custos = pd.DataFrame({
                "Item": ["Fatura Atual", "Custos Extras"],
                "Valor": [dados['valor_total'], dados.get('custos_extras', 0)]
            })
            st.dataframe(df_custos, hide_index=True, use_container_width=True)

    if st.button("Nova Análise"):
        st.session_state['dados_lidos'] = None
        st.rerun()
