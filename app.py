import streamlit as st
import pandas as pd
import fitz  # PyMuPDF
import re
from calculos import realizar_auditoria_gd

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Auditor-Eon Pro", layout="wide")

# CSS DOS SELOS
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

st.title("⚡ Auditor-Eon: Leitura Inteligente")

# --- FUNÇÃO DE LIMPEZA DE NÚMEROS ---
def limpar_numero(texto):
    if not texto:
        return 0.0
    try:
        # Remove R$, espaços e letras
        texto = re.sub(r'[^\d,\.]', '', texto)
        
        # Lógica Brasil: Se tem vírgula, ela é o decimal
        if ',' in texto:
            texto = texto.replace('.', '').replace(',', '.')
        else:
            # Se só tem ponto, assume que é decimal
            pass
            
        valor = float(texto)
        return valor
    except:
        return 0.0

# --- LEITOR COM FILTRO ANTI-ERRO ---
def extrair_dados_pdf(arquivo):
    dados = {
        'nome': 'Cliente Identificado',
        'cidade': 'Não Identificada',
        'distribuidora': 'Concessionária',
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
        st.error(f"Erro no PDF: {e}")
        return dados

    # --- ESTRATÉGIA: PROCURAR TODOS OS NÚMEROS E FILTRAR ---
    
    # 1. TENTA ACHAR CONSUMO (kWh)
    # Procura todos os números perto de kWh
    # Regex explica: Pegue números (ex: 450,00) que tenham "kWh" na frente ou atrás
    padrao_kwh = r'(\d[\d\.,]*)\s*kWh|kWh\s*(\d[\d\.,]*)'
    candidatos_kwh = re.findall(padrao_kwh, texto_completo, re.IGNORECASE)
    
    lista_numeros = []
    for match in candidatos_kwh:
        # O regex retorna tuplas, pegamos o que não for vazio
        val_str = match[0] if match[0] else match[1]
        valor = limpar_numero(val_str)
        # FILTRO DE SEGURANÇA:
        # Ignora zero e ignora números gigantes (Leitura do Medidor costuma ser > 10.000)
        # Ajuste: A maioria das contas é menor que 10.000 kWh. 
        if 0 < valor < 20000: 
            lista_numeros.append(valor)
            
    # Se achou números válidos, o maior geralmente é o consumo e o segundo a injeção (ou vice-versa)
    if lista_numeros:
        # Ordena do maior para o menor
        lista_numeros.sort(reverse=True)
        dados['consumo_kwh'] = lista_numeros[0] # Assume o maior como consumo
        if len(lista_numeros) > 1:
            dados['injetada_kwh'] = lista_numeros[1] # O segundo maior como injeção (tentativa)

    # 2. PROCURA INJETADA ESPECIFICAMENTE (Refinamento)
    match_inj = re.search(r'(?:Injetada|Injeção|Compensada).*?(\d[\d\.,]*)', texto_completo, re.IGNORECASE)
    if match_inj:
        val = limpar_numero(match_inj.group(1))
        if 0 < val < 20000:
            dados['injetada_kwh'] = val

    # 3. VALOR TOTAL (R$)
    match_valor = re.search(r'(?:Total a pagar|Valor Total|Vencimento).*?R\$\s*([\d\.,]+)', texto_completo, re.IGNORECASE)
    if match_valor:
        dados['valor_total'] = limpar_numero(match_valor.group(1))

    # 4. CUSTOS EXTRAS (CIP/Ilum)
    match_cip = re.search(r'(?:Contrib|Ilum|CIP).*?R\$\s*([\d\.,]+)', texto_completo, re.IGNORECASE)
    if match_cip:
        dados['custos_extras'] = limpar_numero(match_cip.group(1))

    return dados

# --- ESTADO DA SESSÃO ---
if 'dados_lidos' not in st.session_state:
    st.session_state['dados_lidos'] = None

# ==============================================================================
# 1. UPLOAD
# ==============================================================================
uploaded_file = st.file_uploader("Upload da Fatura (PDF)", type=["pdf"])

if uploaded_file is not None and st.session_state['dados_lidos'] is None:
    with st.spinner("Analisando Fatura..."):
        dados_extraidos = extrair_dados_pdf(uploaded_file)
        st.session_state['dados_lidos'] = dados_extraidos
        st.success("Leitura Concluída!")
        st.rerun()

# ==============================================================================
# 2. CALIBRAGEM (CORREÇÃO DE DADOS)
# ==============================================================================
if st.session_state['dados_lidos']:
    dados = st.session_state['dados_lidos']
    
    st.divider()
    st.subheader("🛠️ Passo 2: Calibragem")
    st.caption("Confira se os valores lidos estão corretos. Se não, ajuste manualmente.")
    
    c1, c2, c3 = st.columns(3)
    with c1:
        dados['consumo_kwh'] = st.number_input("Consumo Lido (kWh):", value=float(dados['consumo_kwh']), format="%.2f")
    with c2:
        dados['injetada_kwh'] = st.number_input("Injetada Lido (kWh):", value=float(dados['injetada_kwh']), format="%.2f")
    with c3:
        dados['valor_total'] = st.number_input("Valor Conta (R$):", value=float(dados['valor_total']), format="%.2f")

    st.markdown("---")
    
    # BLOCO DE DESTAQUE PARA O INPUT
    col_info, col_input = st.columns([1, 1])
    with col_info:
        st.info("💡 **Dica:** Olhe no aplicativo do seu inversor o valor total gerado neste mês.")
    
    with col_input:
        geracao_inversor = st.number_input(
            "Insira a Geração Total do Inversor (kWh):", 
            min_value=0.0,
            value=float(dados.get('injetada_kwh', 0)), 
            step=10.0
        )

    # BOTÃO FINAL
    if st.button("Gerar Auditoria Completa 🚀", type="primary"):
        res = realizar_auditoria_gd(dados, geracao_inversor)
        
        st.markdown("---")
        st.markdown(f"### 📊 Resultado da Auditoria")
        
        # Selo
        if "Confirmada" in res['selo']:
            st.markdown(f'<div class="selo-verde">{res["selo"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="selo-amarelo">{res["selo"]}</div>', unsafe_allow_html=True)
            
        st.divider()

        # KPIs
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Economia Real", f"R$ {res['economia_reais']:.2f}")
        k2.metric("Economia (%)", f"{res['economia_perc']:.1f}%")
        k3.metric("Autoconsumo", f"{res['consumo_instantaneo']:.0f} kWh")
        k4.metric("Conta Sem Solar", f"R$ {res['conta_sem_solar']:.2f}")

        st.divider()
        
        # Tabelas
        col_esq, col_dir = st.columns(2)
        with col_esq:
            st.subheader("⚡ Energia")
            df_en = pd.DataFrame({
                "Item": ["Consumo da Rede", "Geração Total", "Autoconsumo", "Carga Real Total"],
                "Valor (kWh)": [dados['consumo_kwh'], geracao_inversor, res['consumo_instantaneo'], res['carga_total']]
            })
            st.dataframe(df_en, hide_index=True, use_container_width=True)
            
        with col_dir:
            st.subheader("💸 Financeiro")
            df_custos = pd.DataFrame({
                "Item": ["Fatura Atual", "Custos Extras"],
                "Valor (R$)": [dados['valor_total'], dados.get('custos_extras', 0)]
            })
            st.dataframe(df_custos, hide_index=True, use_container_width=True)

    if st.button("Nova Análise"):
        st.session_state['dados_lidos'] = None
        st.rerun()
        
