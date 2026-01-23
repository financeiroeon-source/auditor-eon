import streamlit as st
import pandas as pd
import pdfplumber
import re
from calculos import realizar_auditoria_gd

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Auditor-Eon Pro", layout="wide")

# CSS para os Selos
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
""", unsafe_allow_index=True)

st.title("⚡ Auditor-Eon: Sistema de Análise GD")

# --- FUNÇÃO DE LEITURA (OCR) RECONSTRUÍDA ---
def extrair_dados_pdf(arquivo):
    """
    Função que lê o PDF e tenta encontrar os padrões de contas de energia.
    """
    texto_completo = ""
    dados = {
        'nome': 'Cliente Identificado',
        'cidade': 'Não identificada',
        'distribuidora': 'Concessionária',
        'mes_referencia': 'Mês Atual',
        'consumo_kwh': 0.0,
        'injetada_kwh': 0.0,
        'valor_total': 0.0,
        'saldo_anterior': 0.0,
        'custos_extras': 0.0
    }

    try:
        with pdfplumber.open(arquivo) as pdf:
            for page in pdf.pages:
                texto_completo += page.extract_text() or ""
    except Exception as e:
        st.error(f"Erro ao ler PDF: {e}")
        return dados

    # --- REGEX PARA CAPTURAR NÚMEROS (PADRÃO BRASILEIRO) ---
    # Procura por padrões comuns em faturas de energia
    
    # 1. Tenta achar o Valor Total (Ex: "Total a pagar R$ 150,00")
    match_valor = re.search(r'(?:Total a pagar|Valor Total|Total da Fatura).*?R\$\s*([\d\.,]+)', texto_completo, re.IGNORECASE)
    if match_valor:
        val_str = match_valor.group(1).replace('.', '').replace(',', '.')
        dados['valor_total'] = float(val_str)

    # 2. Tenta achar Consumo Ativo (Ex: "Energia Ativa kWh 450")
    # Padrão genérico que busca um número perto da palavra kWh
    match_consumo = re.search(r'(?:Energia Ativa|Consumo|Fornecimento).*?kWh\s+([\d\.,]+)', texto_completo, re.IGNORECASE)
    if match_consumo:
        cons_str = match_consumo.group(1).replace('.', '').replace(',', '.')
        dados['consumo_kwh'] = float(cons_str)

    # 3. Tenta achar Energia Injetada (Ex: "Energia Injetada kWh 380")
    match_injetada = re.search(r'(?:Injetada|Energia Injetada|GD).*?kWh\s+([\d\.,]+)', texto_completo, re.IGNORECASE)
    if match_injetada:
        inj_str = match_injetada.group(1).replace('.', '').replace(',', '.')
        dados['injetada_kwh'] = float(inj_str)

    # 4. Tenta achar Saldo Anterior (Ex: "Saldo Anterior 1200")
    match_saldo = re.search(r'(?:Saldo Anterior|Saldo Atual|Acumulado).*?([\d\.,]+)', texto_completo, re.IGNORECASE)
    if match_saldo:
        saldo_str = match_saldo.group(1).replace('.', '').replace(',', '.')
        dados['saldo_anterior'] = float(saldo_str)
        
    return dados

# --- ESTADO DA SESSÃO ---
if 'dados_lidos' not in st.session_state:
    st.session_state['dados_lidos'] = None

# ==============================================================================
# 1. UPLOAD E LEITURA REAL
# ==============================================================================
uploaded_file = st.file_uploader("Faça o upload da Fatura (PDF)", type=["pdf"])

if uploaded_file is not None and st.session_state['dados_lidos'] is None:
    with st.spinner("Lendo a conta de luz..."):
        # CHAMA A FUNÇÃO DE LEITURA QUE CRIAMOS ACIMA
        dados_extraidos = extrair_dados_pdf(uploaded_file)
        st.session_state['dados_lidos'] = dados_extraidos
        st.success("Leitura concluída!")
        st.rerun()

# ==============================================================================
# 2. CALIBRAGEM E INPUT (O Cérebro da Análise)
# ==============================================================================
if st.session_state['dados_lidos']:
    dados = st.session_state['dados_lidos']
    
    st.divider()
    st.subheader("🛠️ Passo 2: Calibragem do Sistema Solar")
    
    # Se o leitor não achou algum dado, o usuário pode corrigir aqui
    col_check1, col_check2 = st.columns(2)
    with col_check1:
        dados['consumo_kwh'] = st.number_input("Consumo Lido (Rede):", value=dados['consumo_kwh'])
    with col_check2:
        dados['injetada_kwh'] = st.number_input("Injeção Lida (Crédito):", value=dados['injetada_kwh'])
        
    st.markdown("---")
    
    col_info, col_input = st.columns([1, 1])
    with col_info:
        st.info("Agora, insira o dado do Inversor para calcular o Autoconsumo.")
    
    with col_input:
        # INPUT DA GERAÇÃO
        geracao_inversor = st.number_input(
            "Informe a Geração Total (kWh) do Inversor:", 
            min_value=0.0,
            value=float(dados.get('injetada_kwh', 0)), 
            help="Verifique no aplicativo do inversor quanto foi gerado neste mês."
        )

    # BOTÃO FINAL
    if st.button("Gerar Auditoria Completa 🚀", type="primary"):
        
        # Chama as fórmulas do arquivo calculos.py
        res = realizar_auditoria_gd(dados, geracao_inversor)
        
        # --- DASHBOARD FINAL (15 PONTOS) ---
        st.markdown("---")
        st.markdown(f"### 📊 Relatório de Análise: {dados.get('nome')}")
        
        # Linha 1
        c1, c2, c3, c4 = st.columns(4)
        c1.caption("Cliente"); c1.write(f"**{dados.get('nome')}**")
        c2.caption("Cidade"); c2.write(dados.get('cidade'))
        c3.caption("Concessionária"); c3.write(dados.get('distribuidora'))
        c4.caption("Período"); c4.write(dados.get('mes_referencia'))
        
        st.write("") 

        # Linha 2: Selo
        if "Confirmada" in res['selo']:
            st.markdown(f'<div class="selo-verde">{res["selo"]}</div>', unsafe_allow_index=True)
        else:
            st.markdown(f'<div class="selo-amarelo">{res["selo"]}</div>', unsafe_allow_index=True)
            
        st.divider()

        # Linha 3: KPIs
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("💰 Economia Real", f"R$ {res['economia_reais']:.2f}")
        k2.metric("📉 Economia (%)", f"{res['economia_perc']:.1f}%")
        k3.metric("🔋 Consumo Instantâneo", f"{res['consumo_instantaneo']:.0f} kWh")
        k4.metric("🚫 Conta Sem Solar", f"R$ {res['conta_sem_solar']:.2f}")

        st.divider()

        # Linha 4: Tabelas
        col_esq, col_dir = st.columns(2)
        
        with col_esq:
            st.subheader("⚡ Balanço Energético")
            df_energia = pd.DataFrame({
                "Descrição": ["Consumo da Rede", "Geração do Sistema", "Consumo Instantâneo", "Carga Total Real"],
                "Valor (kWh)": [dados['consumo_kwh'], geracao_inversor, res['consumo_instantaneo'], res['carga_total']]
            })
            st.dataframe(df_energia, hide_index=True, use_container_width=True)
            
        with col_dir:
            st.subheader("💸 Detalhamento Financeiro")
            df_custos = pd.DataFrame({
                "Descrição": ["Valor Fatura Atual", "Outros Custos Est."],
                "Valor (R$)": [dados['valor_total'], dados.get('custos_extras', 0)]
            })
            st.dataframe(df_custos, hide_index=True, use_container_width=True)

        # Linha 5: Texto Resumo
        st.info(f"""
        📝 **Resumo Executivo:**
        Economia de **{res['economia_perc']:.1f}%**. 
        O sistema supriu a demanda, com **{res['consumo_instantaneo']:.0f} kWh** consumidos instantaneamente (sem taxas).
        """)

    if st.button("Nova Análise"):
        st.session_state['dados_lidos'] = None
        st.rerun()
