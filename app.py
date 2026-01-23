import streamlit as st
import pdfplumber
import google.generativeai as genai
import json
import re

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Auditor IA - EON", page_icon="⚡", layout="wide")

# Estilo Personalizado EON (Preto e Laranja)
st.markdown("""
    <style>
    .main {background-color: #050505; color: #ffffff;}
    .stButton>button {background-color: #EE7348; color: white; border-radius: 8px; border: none; font-weight: bold;}
    .stMetric {background-color: #1a1a1a; padding: 15px; border-radius: 10px; border: 1px solid #333;}
    h1, h2, h3 {color: #EE7348;}
    .stAlert {background-color: #1a1a1a; color: white; border: 1px solid #333;}
    </style>
    """, unsafe_allow_html=True)

# --- BARRA LATERAL (CONFIGURAÇÃO) ---
with st.sidebar:
    # Tenta carregar logo se existir link publico, senao mostra texto
    st.header("⚡ EON SOLAR")
    st.markdown("---")
    
    # Campo para a API Key
    api_key = st.text_input("Cole sua Google API Key aqui:", type="password")
    
    st.info("💡 Não tem a chave? Crie em aistudio.google.com (É grátis)")
    st.divider()
    
    ano_regra = st.selectbox("Ano de Referência (Fio B)", [2025, 2026, 2027, 2028], index=1)
    st.caption("Define o percentual de Fio B a pagar.")

# --- FUNÇÃO 1: LER O PDF ---
def get_pdf_text(uploaded_file):
    text = ""
    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            text += page.extract_text() + "\n"
    return text

# --- FUNÇÃO 2: ANALISAR COM A IA ---
def analisar_conta_com_ia(texto_fatura, chave):
    genai.configure(api_key=chave)
    model = genai.GenerativeModel('gemini-1.5-flash') # Modelo rápido e barato
    
    prompt = f"""
    Você é um Engenheiro de Vendas Sênior da EON Energia Solar.
    Analise o texto desta fatura de energia e extraia os dados técnicos com precisão cirúrgica.
    
    Retorne APENAS um JSON (sem texto antes ou depois, sem ```json) com estes campos:
    
    1. "concessionaria": "Light" ou "Enel" (se não achar, tente deduzir pelo endereço ou CNPJ).
    2. "consumo_kwh": (Int) O consumo faturado total (energia ativa) do mês atual. Se houver histórico, pegue o valor do mês de referência.
    3. "valor_total_fatura": (Float) Valor total a pagar R$.
    4. "cip": (Float) Valor da Iluminação Pública (Contrib Ilum Pub). Se não achar, retorne 0.
    5. "multas": (Float) Soma de multas, juros e mora se houver.
    6. "reativa": (Float) Valor de energia reativa excedente se houver.
    7. "tem_solar": (Boolean) True se encontrar termos como "Energia Injetada", "GD", "Compensada", "Saldo Geração".
    8. "mes_referencia": (String) Mês/Ano da conta (ex: "Jan/2026").

    TEXTO DA FATURA:
    {texto_fatura}
    """
    
    try:
        response = model.generate_content(prompt)
        # Limpeza do JSON
        json_str = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(json_str)
    except Exception as e:
        return {"erro": str(e)}

# --- FUNÇÃO 3: CÁLCULOS FINANCEIROS EON ---
def calcular_viabilidade(dados, ano_input):
    consumo = dados.get('consumo_kwh', 0)
    empresa = dados.get('concessionaria', 'Outra').lower()
    cip_real = dados.get('cip', 0)
    
    if consumo == 0:
        return 0, 0, 0, 0 # Evita erro de divisão
    
    # 1. Definição de Tarifas (Light vs Enel)
    if 'light' in empresa:
        # Tarifa Light (ICMS Escalonado)
        tarifa = {'cheia': 1.22, 'fioB': 0.571} if consumo > 300 else {'cheia': 1.08, 'fioB': 0.520}
        usa_icms_subvencao = True
    else: 
        # Tarifa Enel
        tarifa = {'cheia': 1.15, 'fioB': 0.672} if consumo > 300 else {'cheia': 1.07, 'fioB': 0.600}
        usa_icms_subvencao = False

    # 2. Mapa Fio B (Regra de Transição)
    mapa_fio = {2025: 0.45, 2026: 0.60, 2027: 0.75, 2028: 0.90}
    perc_fio = mapa_fio.get(ano_input, 0.60)

    # 3. Cálculos
    conta_sem_solar = dados.get('valor_total_fatura', 0)
    
    # Se a IA não pegou o valor total (as vezes acontece em scanner ruim), estima
    if conta_sem_solar == 0: 
        conta_sem_solar = (consumo * tarifa['cheia']) + cip_real

    # Simulação Solar
    energia_injetada = consumo * 0.70 # 70% passa pelo medidor
    
    custo_fio_b = energia_injetada * (tarifa['fioB'] * perc_fio)
    custo_minimo = 100 * tarifa['cheia'] # Assume trifásico padrão
    
    custo_energia = max(custo_fio_b, custo_minimo)
    
    icms_extra = 0
    if usa_icms_subvencao:
        icms_extra = (energia_injetada * tarifa['cheia']) * 0.18
        
    conta_com_solar = custo_energia + cip_real + icms_extra
    
    economia = conta_sem_solar - conta_com_solar
    
    # Dimensionamento Sugerido (Kit)
    # Geração média RJ: 115 kWh/mês por kWp
    potencia_necessaria = consumo / 115
    placas_550 = round((potencia_necessaria * 1000) / 550)
    if placas_550 < 4: placas_550 = 4 # Mínimo viável
    
    return conta_sem_solar, conta_com_solar, economia, placas_550

# --- TELA PRINCIPAL ---
st.title("🤖 EON AI Auditor")
st.markdown("### Inteligência Artificial para Análise de Contas")

if not api_key:
    st.warning("👈 Insira a Chave da IA no menu lateral (lado esquerdo) para começar.")
    st.stop()

uploaded_file = st.file_uploader("Arraste a fatura (PDF) aqui", type="pdf")

if uploaded_file:
    with st.spinner("🔍 A IA está lendo a fatura e calculando a viabilidade..."):
        # 1. Leitura
        texto = get_pdf_text(uploaded_file)
        
        # 2. Análise IA
        dados_ia = analisar_conta_com_ia(texto, api_key)
        
        if "erro" in dados_ia:
            st.error("Erro ao processar: " + str(dados_ia['erro']))
            st.write("Detalhe técnico: A IA não retornou um JSON válido. Tente outra conta.")
        else:
            # 3. Cálculo
            sem, com, econ, placas = calcular_viabilidade(dados_ia, ano_regra)
            
            # --- DASHBOARD ---
            st.success("✅ Análise Concluída com Sucesso!")
            
            # BLOCO 1: DADOS DA CONTA
            st.subheader("📋 Raio-X da Fatura")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Concessionária", dados_ia.get('concessionaria', 'ND'))
            c2.metric("Consumo", f"{dados_ia.get('consumo_kwh', 0)} kWh")
            c3.metric("Valor Atual", f"R$ {dados_ia.get('valor_total_fatura', 0):.2f}")
            c4.metric("CIP", f"R$ {dados_ia.get('cip', 0):.2f}")
            
            # Alertas
            alertas = []
            if dados_ia.get('multas', 0) > 0: alertas.append(f"⚠️ Multas: R$ {dados_ia['multas']:.2f}")
            if dados_ia.get('reativa', 0) > 0: alertas.append(f"⚠️ Reativa: R$ {dados_ia['reativa']:.2f}")
            if dados_ia.get('tem_solar'): alertas.append("☀️ Cliente JÁ POSSUI solar")
            
            if alertas:
                for a in alertas: st.error(a)
            else:
                st.info("✅ Fatura saudável (sem multas ou reativa).")

            st.markdown("---")

            # BLOCO 2: SOLUÇÃO SOLAR
            st.subheader("☀️ Solução Recomendada EON")
            
            k1, k2, k3 = st.columns(3)
            k1.metric("Kit Sugerido", f"{placas} Placas", "550W")
            k2.metric("Nova Conta Estimada", f"R$ {com:.2f}", f"-{round((econ/sem)*100) if sem > 0 else 0}%")
            k3.metric("Economia Anual", f"R$ {econ * 12:,.2f}", "Livre")
            
            # Botão WhatsApp
            texto_zap = f"Olá! Sua conta de {dados_ia.get('consumo_kwh')}kWh pode cair para R$ {com:.2f}. Sugerimos um kit de {placas} placas. Economia de R$ {econ*12:,.2f}/ano."
            st.link_button("📲 Enviar Proposta no WhatsApp", f"[https://wa.me/?text=](https://wa.me/?text=){texto_zap}")

            with st.expander("Ver Auditoria Técnica (JSON)"):
                st.json(dados_ia)
