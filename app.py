import streamlit as st
import pdfplumber
import google.generativeai as genai
import json
import re

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Auditor IA - EON", page_icon="⚡", layout="wide")

# Estilo EON (Dark Mode)
st.markdown("""
    <style>
    .main {background-color: #050505; color: #ffffff;}
    .stButton>button {background-color: #EE7348; color: white; border-radius: 8px; border: none; font-weight: bold;}
    .stMetric {background-color: #1a1a1a; padding: 15px; border-radius: 10px; border: 1px solid #333;}
    h1, h2, h3 {color: #EE7348;}
    .stAlert {background-color: #1a1a1a; color: white; border: 1px solid #333;}
    </style>
    """, unsafe_allow_html=True)

# --- SIDEBAR (CONFIGURAÇÕES) ---
with st.sidebar:
    st.header("⚡ EON SOLAR")
    st.markdown("---")
    
    # Campo de Senha (API Key)
    api_key = st.text_input("Cole sua Google API Key aqui:", type="password")
    st.caption("Modelo Ativo: Gemini 2.5 Flash 🚀")
    
    st.divider()
    ano_regra = st.selectbox("Ano de Referência (Fio B)", [2025, 2026, 2027, 2028], index=1)
    st.info("ℹ️ Define o % de Fio B na simulação.")

# --- FUNÇÃO 1: LER O PDF ---
def get_pdf_text(uploaded_file):
    text = ""
    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            text += page.extract_text() + "\n"
    return text

# --- FUNÇÃO 2: CÉREBRO DA IA (ATUALIZADO) ---
def analisar_conta_com_ia(texto_fatura, chave):
    genai.configure(api_key=chave)
    
    # AQUI ESTAVA O ERRO: Atualizado para o modelo que seu diagnóstico confirmou
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    prompt = f"""
    Aja como um Engenheiro de Vendas da EON Energia Solar.
    Analise o texto desta fatura de energia elétrica e extraia os dados técnicos.
    
    Retorne APENAS um JSON (sem texto adicional) com as chaves:
    1. "concessionaria": "Light" ou "Enel" (se não achar, deduza pelo contexto).
    2. "consumo_kwh": (Int) Consumo total faturado no mês.
    3. "valor_total_fatura": (Float) Valor total a pagar R$.
    4. "cip": (Float) Contribuição de Iluminação Pública.
    5. "multas": (Float) Soma de multas, juros e mora.
    6. "reativa": (Float) Valor de energia reativa excedente.
    7. "tem_solar": (Boolean) True se tiver termos como "Energia Injetada", "GD", "Saldo".
    8. "mes_referencia": (String) Mês/Ano da conta.

    TEXTO DA FATURA:
    {texto_fatura}
    """
    
    try:
        response = model.generate_content(prompt)
        texto_resposta = response.text
        
        # Filtro de Segurança para pegar só o JSON
        match = re.search(r'\{.*\}', texto_resposta, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        else:
            return {"erro": "A IA respondeu, mas não em JSON válido."}
            
    except Exception as e:
        return {"erro": str(e)}

# --- FUNÇÃO 3: CALCULADORA FINANCEIRA ---
def calcular_viabilidade(dados, ano_input):
    consumo = dados.get('consumo_kwh', 0)
    empresa = dados.get('concessionaria', 'Outra').lower()
    cip_real = dados.get('cip', 0)
    
    if consumo == 0: return 0, 0, 0, 0
    
    # Tarifas e Regras RJ
    if 'light' in empresa:
        tarifa = {'cheia': 1.22, 'fioB': 0.571} if consumo > 300 else {'cheia': 1.08, 'fioB': 0.520}
        usa_icms_subvencao = True
    else: 
        tarifa = {'cheia': 1.15, 'fioB': 0.672} if consumo > 300 else {'cheia': 1.07, 'fioB': 0.600}
        usa_icms_subvencao = False

    mapa_fio = {2025: 0.45, 2026: 0.60, 2027: 0.75, 2028: 0.90}
    perc_fio = mapa_fio.get(ano_input, 0.60)

    # Cálculos
    conta_sem_solar = dados.get('valor_total_fatura', 0)
    if conta_sem_solar == 0: conta_sem_solar = (consumo * tarifa['cheia']) + cip_real

    energia_injetada = consumo * 0.70 # 70% injetada
    custo_fio_b = energia_injetada * (tarifa['fioB'] * perc_fio)
    custo_minimo = 100 * tarifa['cheia'] # Trifásico Padrão
    
    custo_energia = max(custo_fio_b, custo_minimo)
    
    icms_extra = 0
    if usa_icms_subvencao:
        icms_extra = (energia_injetada * tarifa['cheia']) * 0.18
        
    conta_com_solar = custo_energia + cip_real + icms_extra
    economia = conta_sem_solar - conta_com_solar
    
    # Dimensionamento (Kit)
    potencia = consumo / 115
    placas = round((potencia * 1000) / 550)
    if placas < 4: placas = 4
    
    return conta_sem_solar, conta_com_solar, economia, placas

# --- TELA PRINCIPAL ---
st.title("🤖 EON AI Auditor")
st.caption("Sistema Inteligente de Análise de Faturas")

if not api_key:
    st.warning("👈 Insira sua Chave API no menu lateral para iniciar.")
    st.stop()

uploaded_file = st.file_uploader("Arraste a conta de luz (PDF) aqui", type="pdf")

if uploaded_file:
    with st.spinner("🔍 Lendo fatura com Gemini 2.5..."):
        # 1. Leitura
        texto = get_pdf_text(uploaded_file)
        
        # 2. IA
        dados_ia = analisar_conta_com_ia(texto, api_key)
        
        if "erro" in dados_ia:
            st.error(f"Erro na análise: {dados_ia['erro']}")
        else:
            # 3. Cálculo
            sem, com, econ, placas = calcular_viabilidade(dados_ia, ano_regra)
            
            # --- DASHBOARD ---
            st.success("✅ Análise Realizada com Sucesso!")
            
            # BLOCO 1: DADOS
            st.subheader("📋 Dados da Conta")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Concessionária", dados_ia.get('concessionaria', 'ND'))
            c2.metric("Consumo", f"{dados_ia.get('consumo_kwh')} kWh")
            c3.metric("Valor Fatura", f"R$ {dados_ia.get('valor_total_fatura'):.2f}")
            c4.metric("CIP", f"R$ {dados_ia.get('cip'):.2f}")
            
            # Alertas
            alertas = []
            if dados_ia.get('multas', 0) > 0: alertas.append(f"⚠️ Multas detectadas: R$ {dados_ia['multas']:.2f}")
            if dados_ia.get('reativa', 0) > 0: alertas.append(f"⚠️ Energia Reativa: R$ {dados_ia['reativa']:.2f}")
            if dados_ia.get('tem_solar'): alertas.append("☀️ Cliente JÁ POSSUI sistema solar.")
            
            if alertas:
                for a in alertas: st.error(a)
            else:
                st.info("✅ Fatura saudável (Sem multas ou desperdício reativo).")

            st.markdown("---")
            
            # BLOCO 2: PROPOSTA
            st.subheader("☀️ Proposta Comercial")
            k1, k2, k3 = st.columns(3)
            k1.metric("Kit Sugerido", f"{placas} Placas", "550W")
            k2.metric("Nova Conta", f"R$ {com:.2f}", f"-{round((econ/sem)*100) if sem > 0 else 0}%")
            k3.metric("Economia Anual", f"R$ {econ * 12:,.2f}", "Livre")
            
            texto_zap = f"Olá! Analisei sua conta de {dados_ia.get('mes_referencia')}. Consumo de {dados_ia.get('consumo_kwh')}kWh. Com a EON, você economiza R$ {econ*12:,.2f} por ano!"
            st.link_button("📲 Gerar WhatsApp", f"https://wa.me/?text={texto_zap}")
            
            with st.expander("Ver Dados Brutos (JSON)"):
                st.json(dados_ia)
