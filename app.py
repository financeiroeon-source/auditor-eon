import streamlit as st
import pandas as pd

# ==============================================================================
# 1. MOTOR DE CÁLCULO (ENGINE) - Agora dentro do mesmo arquivo para facilitar
# ==============================================================================
class AuditorEonEngine:
    def __init__(self, dados_ocr, geracao_inversor):
        self.dados = dados_ocr
        self.geracao = float(geracao_inversor)
        self.resultados = {}
        
    def processar_analise(self):
        # 1. Recuperar Variáveis Básicas (com segurança contra zeros)
        consumo_rede = self.dados.get('consumo_kwh', 0) 
        energia_injetada = self.dados.get('injetada_kwh', 0)
        valor_fatura_atual = self.dados.get('valor_total', 0)
        
        # Tenta pegar tarifa unitária ou calcula média
        if 'tarifa_unitaria' in self.dados:
            tarifa_cheia = self.dados['tarifa_unitaria']
        else:
            tarifa_cheia = valor_fatura_atual / (consumo_rede if consumo_rede > 0 else 1)

        # 2. Cálculo do Consumo Instantâneo (O "Pulo do Gato")
        consumo_instantaneo = max(0, self.geracao - energia_injetada)
        
        # 3. Cálculo da Carga Real Total
        carga_real_total = consumo_rede + consumo_instantaneo
        
        # 4. Simulação "Conta Sem Solar"
        custos_extras = self.dados.get('custos_extras', 0)
        conta_sem_solar = (carga_real_total * tarifa_cheia) + custos_extras
        
        # 5. Economia
        economia_reais = conta_sem_solar - valor_fatura_atual
        economia_perc = (economia_reais / conta_sem_solar * 100) if conta_sem_solar > 0 else 0
        
        # 6. Saldo de Créditos
        energia_compensada = self.dados.get('compensada_kwh', min(consumo_rede, energia_injetada))
        saldo_anterior = self.dados.get('saldo_anterior', 0)
        novo_saldo = saldo_anterior + (energia_injetada - energia_compensada)
        
        # 7. Selo de Verificação
        if self.geracao >= energia_injetada:
            selo_status = "VERDE"
            selo_msg = "Integridade Matemática Confirmada"
        else:
            selo_status = "AMARELO"
            selo_msg = "Atenção: Geração informada menor que a Injetada"

        # 8. Texto do Resumo Dinâmico
        resumo_texto = f"O cliente teve uma economia de {economia_perc:.1f}%. "
        if consumo_instantaneo > 0:
            resumo_texto += f"O destaque foi o consumo instantâneo de {consumo_instantaneo:.0f} kWh, livre de taxas. "
        if custos_extras > 50:
            resumo_texto += f"Custos extras (multas/outros) de R$ {custos_extras:.2f} impactaram o resultado."

        # Retorna o dicionário pronto para o Dashboard
        self.resultados = {
            "cliente": self.dados.get('nome', 'Cliente'),
            "cidade": self.dados.get('cidade', 'Não ident.'),
            "concessionaria": self.dados.get('distribuidora', 'ND'),
            "periodo": self.dados.get('mes_referencia', 'ND'),
            "consumo_rede": consumo_rede,
            "geracao_sistema": self.geracao,
            "consumo_instantaneo": consumo_instantaneo,
            "conta_sem_solar": conta_sem_solar,
            "economia_reais": economia_reais,
            "economia_perc": economia_perc,
            "saldo_creditos": novo_saldo,
            "custos_fio_b": self.dados.get('fio_b', 0), 
            "outros_custos": custos_extras,
            "selo": {"status": selo_status, "msg": selo_msg},
            "resumo": resumo_texto
        }
        return self.resultados

# ==============================================================================
# 2. INTERFACE (FRONTEND STREAMLIT)
# ==============================================================================
st.set_page_config(page_title="Auditor-Eon Pro", layout="wide")
st.title("⚡ Auditor-Eon: Análise GD Profissional")

# Inicializa sessão
if 'dados_ocr' not in st.session_state:
    st.session_state['dados_ocr'] = None

# --- PASSO 1: UPLOAD ---
uploaded_file = st.file_uploader("Faça o upload da Fatura (PDF ou Imagem)", type=["pdf", "png", "jpg"])

if uploaded_file is not None and st.session_state['dados_ocr'] is None:
    with st.spinner("Processando Inteligência Artificial na fatura..."):
        
        # -----------------------------------------------------------
        # [SEU CÓDIGO DE OCR ENTRA AQUI]
        # Aqui simulamos o resultado do seu OCR para funcionar o teste.
        # Substitua o dicionário abaixo pela chamada da sua função real.
        # -----------------------------------------------------------
        import time
        time.sleep(1.5) # Simulando tempo de leitura
        
        # MOCKUP (DADOS SIMULADOS - APAGUE ISSO QUANDO COLOCAR SEU OCR)
        dados_lidos = {
            'nome': 'CLIENTE TESTE S.A.',
            'cidade': 'Campinas/SP',
            'distribuidora': 'CPFL Paulista',
            'mes_referencia': 'JAN/2024',
            'consumo_kwh': 450.0,
            'injetada_kwh': 380.0,
            'compensada_kwh': 380.0,
            'valor_total': 120.50,
            'saldo_anterior': 1000.0,
            'custos_extras': 15.00, # Ex: CIP
            'tarifa_unitaria': 0.92 # Ex: R$ 0,92/kWh
        }
        
        st.session_state['dados_ocr'] = dados_lidos
        st.success("Leitura concluída com sucesso!")
        st.experimental_rerun()

# --- PASSO 2: INPUT E DASHBOARD ---
if st.session_state['dados_ocr']:
    dados = st.session_state['dados_ocr']
    
    st.divider()
    st.subheader("🛠️ Calibragem do Sistema Solar")
    
    col1, col2 = st.columns([1, 2])
    with col1:
        st.info(f"""
        **Dados Extraídos:**
        - Injetada: {dados.get('injetada_kwh')} kWh
        - Consumo Rede: {dados.get('consumo_kwh')} kWh
        """)
    
    with col2:
        # INPUT OBRIGATÓRIO DA GERAÇÃO
        geracao_user = st.number_input(
            "Informe a Geração Total do Inversor (kWh)", 
            min_value=0.0,
            value=float(dados.get('injetada_kwh', 0)), 
            help="Olhe no app do inversor o valor produzido neste período."
        )

    if st.button("Gerar Auditoria Completa 🚀", type="primary"):
        
        # CHAMA A CLASSE QUE ESTÁ NO TOPO DESTE ARQUIVO
        engine = AuditorEonEngine(dados, geracao_user)
        res = engine.processar_analise()
        
        # --- RENDERIZA O DASHBOARD DE 15 PONTOS ---
        st.markdown("---")
        st.header(f"Relatório: {res['cliente']}")
        
        # Linha 1: Dados
        c1, c2, c3 = st.columns(3)
        c1.text(f"📍 {res['cidade']}")
        c2.text(f"🏢 {res['concessionaria']}")
        c3.text(f"📅 {res['periodo']}")
        
        # Linha 2: Selo
        st.write("")
        if res['selo']['status'] == "VERDE":
            st.success(f"✅ SELO AUDITOR: {res['selo']['msg']}")
        else:
            st.warning(f"⚠️ SELO AUDITOR: {res['selo']['msg']}")

        # Linha 3: KPIs
        k1, k2, k3 = st.columns(3)
        k1.metric("Economia Real", f"R$ {res['economia_reais']:.2f}", f"{res['economia_perc']:.1f}%")
        k2.metric("Conta Sem Solar", f"R$ {res['conta_sem_solar']:.2f}", delta_color="off")
        k3.metric("Consumo Instantâneo", f"{res['consumo_instantaneo']:.0f} kWh", help="Autoconsumo: Energia usada direto do sol.")

        # Linha 4: Tabelas
        col_esq, col_dir = st.columns(2)
        with col_esq:
            st.caption("⚡ Balanço Energético (kWh)")
            df_en = pd.DataFrame({
                "Fluxo": ["Consumo Rede", "Geração Total", "Consumo Instantâneo", "Novo Saldo"],
                "Valor": [res['consumo_rede'], res['geracao_sistema'], res['consumo_instantaneo'], res['saldo_creditos']]
            })
            st.dataframe(df_en, hide_index=True, use_container_width=True)

        with col_dir:
            st.caption("💸 Detalhe Financeiro (R$)")
            df_fin = pd.DataFrame({
                "Item": ["Total a Pagar", "Conta Sem Solar", "Outros Custos"],
                "Valor": [dados['valor_total'], res['conta_sem_solar'], res['outros_custos']]
            })
            st.dataframe(df_fin, hide_index=True, use_container_width=True)
            
        # Linha 5: Resumo
        st.info(f"📝 **Parecer Técnico:** {res['resumo']}")

    # Botão de reiniciar
    if st.button("Nova Análise"):
        st.session_state['dados_ocr'] = None
        st.experimental_rerun()
