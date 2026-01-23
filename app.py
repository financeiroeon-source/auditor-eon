import streamlit as st
import pandas as pd
from analise_gd import AuditorEonEngine # Importa o arquivo que criamos no Passo 1

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Auditor-Eon", layout="wide")

st.title("⚡ Auditor-Eon: Análise de Faturas GD")

# 1. UPLOAD DO ARQUIVO
uploaded_file = st.file_uploader("Faça o upload da Fatura (PDF ou Imagem)", type=["pdf", "png", "jpg"])

# Variável para guardar os dados do OCR na sessão (para não perder quando atualizar a tela)
if 'dados_ocr' not in st.session_state:
    st.session_state['dados_ocr'] = None

# 2. PROCESSAMENTO DO OCR (Seu código atual entra aqui)
if uploaded_file is not None and st.session_state['dados_ocr'] is None:
    with st.spinner("Lendo a conta..."):
        # ==============================================================================
        # [AQUI VAI A SUA FUNÇÃO DE OCR QUE JÁ EXISTIA]
        # Exemplo simulado (substitua pela sua chamada real):
        # dados_lidos = sua_funcao_ocr(uploaded_file)
        # ==============================================================================
        
        # --- APENAS PARA EXEMPLO (Substitua isso pelo retorno do seu OCR) ---
        dados_lidos = {
            'nome': 'João Silva',
            'cidade': 'Campinas',
            'distribuidora': 'CPFL',
            'mes_referencia': 'Jan/2024',
            'consumo_kwh': 450.0,      # Consumo Rede
            'injetada_kwh': 380.0,     # Energia Injetada
            'valor_total': 150.50,     # Valor da conta R$
            'saldo_anterior': 100.0,
            'custos_extras': 15.00     # Multas/CIP
        }
        # --------------------------------------------------------------------
        
        # Salva no estado da sessão
        st.session_state['dados_ocr'] = dados_lidos
        st.success("Fatura processada! Agora, informe a geração do inversor.")

# 3. INTERFACE DE INPUT E RESULTADOS
if st.session_state['dados_ocr']:
    dados = st.session_state['dados_ocr']
    
    st.divider()
    st.subheader("🛠️ Passo 2: Calibragem do Sistema")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.markdown(f"""
        **Dados lidos da conta:**
        - Consumo Rede: `{dados.get('consumo_kwh')} kWh`
        - Injetada na Rede: `{dados.get('injetada_kwh')} kWh`
        """)
    
    with col2:
        # AQUI É O ONDE O USUÁRIO ENTRA COM O DADO QUE FALTAVA
        geracao_user = st.number_input(
            "Qual foi a Geração Total (kWh) no inversor?", 
            min_value=0.0,
            value=float(dados.get('injetada_kwh', 0)), # Sugestão inicial
            help="Olhe no aplicativo do inversor (SolarEdge, Fronius, Growatt, etc)."
        )

    # Botão para gerar o relatório final
    if st.button("Gerar Auditoria Completa 🚀", type="primary"):
        
        # --- CHAMA O CÉREBRO (O ARQUIVO ANALISE_GD.PY) ---
        engine = AuditorEonEngine(dados, geracao_user)
        res = engine.processar_analise()
        
        # --- EXIBE OS 15 PONTOS DO DASHBOARD ---
        st.markdown("---")
        st.header(f"Relatório de Análise: {res['cliente']}")
        
        # Linha 1: Dados Cadastrais
        c1, c2, c3 = st.columns(3)
        c1.write(f"**Cidade:** {res['cidade']}")
        c2.write(f"**Concessionária:** {res['concessionaria']}")
        c3.write(f"**Período:** {res['periodo']}")
        
        st.divider()

        # Linha 2: O Selo de Verificação (Item 14)
        if res['selo']['status'] == "VERDE":
            st.success(f"✅ {res['selo']['msg']}")
        else:
            st.warning(f"⚠️ {res['selo']['msg']}")

        # Linha 3: Big Numbers (Economia e Consumo Instantâneo)
        k1, k2, k3 = st.columns(3)
        k1.metric("Economia Real", f"R$ {res['economia_reais']:.2f}", f"{res['economia_perc']:.1f}%")
        k2.metric("Conta Sem Solar", f"R$ {res['conta_sem_solar']:.2f}")
        k3.metric("Consumo Instantâneo", f"{res['consumo_instantaneo']:.0f} kWh", help="Energia consumida direto do sol")

        # Linha 4: Tabelas Detalhadas
        col_esq, col_dir = st.columns(2)
        
        with col_esq:
            st.caption("Balanço Energético (kWh)")
            df_energia = pd.DataFrame({
                "Descrição": ["Consumo da Rede (Item 5)", "Geração Sistema (Item 6)", "Consumo Instantâneo (Item 7)", "Novo Saldo Créditos (Item 11)"],
                "Valor": [res['consumo_rede'], res['geracao_sistema'], res['consumo_instantaneo'], res['saldo_creditos']]
            })
            st.dataframe(df_energia, hide_index=True, use_container_width=True)
            
        with col_dir:
            st.caption("Custos e Taxas (R$)")
            df_custos = pd.DataFrame({
                "Descrição": ["Total Fatura Atual", "Estimativa Fio B/ICMS (Item 12)", "Outros Custos (Item 13)"],
                "Valor": [dados['valor_total'], res['custos_fio_b'], res['outros_custos']]
            })
            st.dataframe(df_custos, hide_index=True, use_container_width=True)

        # Linha 5: Resumo Executivo (Item 15)
        st.info(f"📝 **Resumo do Auditor:** {res['selo']['msg']} \n\n {res.get('resumo', 'Resumo gerado automaticamente.')}")
        
    # Botão de Reset (para analisar outra conta)
    if st.button("Nova Análise"):
        st.session_state['dados_ocr'] = None
        st.experimental_rerun()
