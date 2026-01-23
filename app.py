import streamlit as st
import pdfplumber
import google.generativeai as genai
import json
import re

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Auditor IA - EON", page_icon="⚡", layout="wide")

# Estilo EON
st.markdown("""
    <style>
    .main {background-color: #050505; color: #ffffff;}
    .stButton>button {background-color: #EE7348; color: white; border-radius: 8px; border: none; font-weight: bold;}
    .stMetric {background-color: #1a1a1a; padding: 15px; border-radius: 10px; border: 1px solid #333;}
    h1, h2, h3 {color: #EE7348;}
    </style>
    """, unsafe_allow_html=True)

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚡ EON SOLAR")
    api_key = st.text_input("Cole sua Google API Key aqui:", type="password")
    st.info("💡 Crie sua chave em: aistudio.google.com")
    st.divider()
    ano_regra = st.selectbox("Ano de Referência (Fio B)", [2025, 2026, 2027, 2028], index=1)

# --- FUNÇÃO 1: LER PDF ---
def get_pdf_text(uploaded_file):
    text = ""
    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            text += page.extract_text() + "\n"
    return text

# --- FUNÇÃO 2: IA (MODELO CLÁSSICO - GEMINI PRO) ---
def analisar_conta_com_ia(texto_fatura, chave):
    genai.configure(api_key=chave)
    
    # MUDANÇA AQUI: Usando o modelo PRO que é compatível com todas as versões
    model = genai.GenerativeModel('gemini-pro')
    
    prompt = f"""
    Aja como um software extrator de dados. Analise o texto desta fatura de energia.
    Extraia os dados em formato JSON puro.
    
    Campos necessários:
    1. "concessionaria": "Light" ou "Enel".
    2. "consumo_kwh": (Int) Consumo total faturado.
    3. "valor_total_fatura": (Float) Valor R$.
    4. "cip": (Float) Ilum. Pub.
    5. "multas": (Float) Soma de multas/juros.
    6. "reativa": (Float) Excedente reativo.
    7. "tem_solar": (Boolean) Se tem injeção/GD.
    8. "mes_referencia": (String) Mês/Ano.

    TEXTO:
    {texto_fatura}
    """
    
    try:
        response = model.generate_content(prompt)
        texto_resposta = response.text
        
        # Filtra apenas o JSON
        match = re.search(r'\{.*\}', texto_resposta, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        else:
            return {"erro": "IA não retornou JSON válido. Tente novamente."}
            
    except Exception as e:
        return {"erro": str(e)}

# --- FUNÇÃO 3: CÁLCULOS ---
def calcular_viabilidade(dados, ano_input):
    consumo = dados.get('consumo_kwh', 0)
    empresa = dados.get('concessionaria', 'Outra').lower()
    cip_real = dados.get('cip', 0)
    
    if consumo == 0: return 0, 0, 0, 0
    
    # Tarifas
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

    energia_injetada = consumo * 0.70
    custo_fio_b = energia_injetada * (tarifa['fioB'] * perc_fio)
    custo_minimo = 100 * tarifa['cheia']
    
    custo_energia = max(custo_fio_b, custo_minimo)
    
    icms_extra = 0
    if usa_icms_subvencao:
        icms_extra = (energia_injetada * tarifa['cheia']) * 0.18
        
    conta_com_solar = custo_energia + cip_real + icms_extra
    economia = conta_sem_solar - conta_com_solar
    
    potencia = consumo / 115
    placas = round((potencia * 1000) / 550)
    if placas < 4: placas = 4
    
    return conta_sem_solar, conta_com_solar, economia, placas

# --- TELA ---
st.title("🤖 EON AI Auditor")

if not api_key:
    st.warning("👈 Insira a Chave da IA no menu lateral para começar.")
    st.stop()

uploaded_file = st.file_uploader("Arraste a fatura (PDF) aqui", type="pdf")

if uploaded_file:
    with st.spinner("🔍 Auditando a conta..."):
        texto = get_pdf_text(uploaded_file)
        dados_ia = analisar_conta_com_ia(texto, api_key)
        
        if "erro" in dados_ia:
            st.error("Erro técnico: " + str(dados_ia['erro']))
            st.info("Dica: Verifique se sua chave API está correta.")
        else:
            sem, com, econ, placas = calcular_viabilidade(dados_ia, ano_regra)
            
            st.success("✅ Análise Concluída!")
            st.subheader("📋 Raio-X da Fatura")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Concessionária", dados_ia.get('concessionaria', 'ND'))
            c2.metric("Consumo", f"{dados_ia.get('consumo_kwh')} kWh")
            c3.metric("Valor Atual", f"R$ {dados_ia.get('valor_total_fatura'):.2f}")
            c4.metric("CIP", f"R$ {dados_ia.get('cip'):.2f}")
            
            st.markdown("---")
            st.subheader("☀️ Solução Recomendada")
            k1, k2, k3 = st.columns(3)
            k1.metric("Kit", f"{placas} Placas", "550W")
            k2.metric("Nova Conta", f"R$ {com:.2f}", f"-{round((econ/sem)*100) if sem > 0 else 0}%")
            k3.metric("Economia Anual", f"R$ {econ * 12:,.2f}", "Livre")
            
            st.link_button("📲 WhatsApp", f"https://wa.me/?text=Proposta EON: Economia de R$ {econ*12:.2f}/ano")
            
            with st.expander("Ver JSON"): st.json(dados_ia)
