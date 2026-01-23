import streamlit as st
import pdfplumber
import google.generativeai as genai
import json
import re
import pandas as pd
import plotly.express as px

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="EON Auditor Pro", page_icon="⚡", layout="wide")

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

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚡ EON SOLAR")
    api_key = st.text_input("Cole sua Google API Key:", type="password")
    st.caption("Modelo: Gemini 2.5 Flash")
    st.divider()
    ano_regra = st.selectbox("Ano de Referência (GD II)", [2025, 2026, 2027, 2028], index=1)

# --- LEITURA DE PDF ---
def get_pdf_text(uploaded_file):
    text = ""
    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            text += page.extract_text() + "\n"
    return text

# --- IA COM ANÁLISE PROFUNDA ---
def analisar_conta_detalhada(texto_fatura, chave):
    genai.configure(api_key=chave)
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    prompt = f"""
    Aja como um Perito em Faturas de Energia. Analise o texto e extraia os componentes de custo detalhados.
    
    Retorne um JSON com:
    1. "concessionaria": "Light" ou "Enel".
    2. "consumo_kwh": (Int) Consumo total medido.
    3. "valor_total": (Float) Valor final da conta R$.
    4. "tusd": (Float) Valor monetário (R$) total referente à TUSD (Uso do Sistema) ou Distribuição.
    5. "te": (Float) Valor monetário (R$) total referente à TE (Energia).
    6. "bandeiras": (Float) Valor de bandeiras tarifárias (Amarela/Vermelha/Escassez).
    7. "cip": (Float) Contribuição Ilum. Pública.
    8. "impostos_federais": (Float) Valor PIS + COFINS (geralmente detalhado no rodapé).
    9. "icms_total": (Float) Valor total do ICMS.
    10. "multas": (Float) Multas/Juros.
    11. "mes_ref": (String) Mês/Ano.

    Se não achar um valor específico explícito, coloque 0.
    
    TEXTO:
    {texto_fatura}
    """
    
    try:
        response = model.generate_content(prompt)
        match = re.search(r'\{.*\}', response.text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return {"erro": "Falha no JSON da IA"}
    except Exception as e:
        return {"erro": str(e)}

# --- TELA PRINCIPAL ---
st.title("🔎 EON Auditor Pro")
st.markdown("### Decomposição de Custos e Análise Técnica")

if not api_key:
    st.warning("👈 Insira a API Key para começar.")
    st.stop()

uploaded_file = st.file_uploader("Arraste a fatura (PDF)", type="pdf")

if uploaded_file:
    with st.spinner("🔬 Realizando autópsia da conta..."):
        texto = get_pdf_text(uploaded_file)
        dados = analisar_conta_detalhada(texto, api_key)
        
        if "erro" in dados:
            st.error(dados['erro'])
        else:
            # --- CÁLCULOS TÉCNICOS ---
            total = dados.get('valor_total', 0)
            consumo = dados.get('consumo_kwh', 1) # evita div por 0
            
            # Estimativa de Fio B (Regra Prática RJ: ~45% da TUSD ou ~28% da Tarifa Cheia)
            # Como a conta nem sempre separa TUSD Fio A e B, usamos a regra da ANEEL sobre a TUSD
            tusd_total = dados.get('tusd', 0)
            if tusd_total == 0: 
                # Se a IA não achou a TUSD separada, estima 45% da conta (menos CIP)
                tusd_total = (total - dados.get('cip',0)) * 0.45
            
            fio_b_estimado = tusd_total * 0.55 # Aprox 55% da TUSD é Fio B (Remuneração da Distribuidora)
            
            # Custo do kWh Real (Tarifa Média Efetiva)
            tarifa_media = total / consumo if consumo > 0 else 0

            # --- VISUALIZAÇÃO ---
            
            # 1. CABEÇALHO
            c1, c2, c3 = st.columns(3)
            c1.metric("Valor da Conta", f"R$ {total:.2f}")
            c2.metric("Consumo", f"{consumo} kWh")
            c3.metric("Tarifa Real (R$/kWh)", f"R$ {tarifa_media:.2f}")
            
            st.divider()

            # 2. DETALHAMENTO DO CUSTO (GRÁFICO)
            st.subheader("🍰 Para onde vai o dinheiro do cliente?")
            
            # Prepara dados para o gráfico
            custos = {
                "Energia (Geração/TE)": dados.get('te', 0),
                "Fio/Distribuição (TUSD)": tusd_total,
                "Impostos (ICMS/PIS/COFINS)": dados.get('icms_total', 0) + dados.get('impostos_federais', 0),
                "Iluminação Pública (CIP)": dados.get('cip', 0),
                "Bandeiras/Multas": dados.get('bandeiras', 0) + dados.get('multas', 0)
            }
            
            # Se a soma não bater com o total (comum em leitura de OCR), cria um "Outros/Ajustes"
            soma_parcial = sum(custos.values())
            if soma_parcial < total:
                custos["Outros/Não Detalhado"] = total - soma_parcial
            
            df_chart = pd.DataFrame(list(custos.items()), columns=['Componente', 'Valor'])
            
            col_graph, col_detalhes = st.columns([1.5, 1])
            
            with col_graph:
                fig = px.pie(df_chart, values='Valor', names='Componente', hole=0.4, 
                             color_discrete_sequence=['#EE7348', '#FF9F1C', '#9D4EDD', '#00DC5D', '#E74C3C', '#95A5A6'])
                fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", font={'color': "white"})
                st.plotly_chart(fig, use_container_width=True)
            
            with col_detalhes:
                st.markdown("#### Detalhes em R$")
                for k, v in custos.items():
                    if v > 0:
                        st.write(f"**{k}:** R$ {v:.2f}")
                
                st.info(f"💡 **Fio B Estimado:** R$ {fio_b_estimado:.2f} (Este é o valor que continuará sendo cobrado parcialmente na Lei 14.300)")

            st.divider()

            # 3. ANÁLISE GD II (SIMULAÇÃO RÁPIDA)
            st.subheader("☀️ Impacto GD II (Lei 14.300)")
            
            mapa_pgto = {2025: 0.45, 2026: 0.60, 2027: 0.75, 2028: 0.90}
            perc_pagar = mapa_pgto[ano_regra]
            
            fio_b_a_pagar = fio_b_estimado * perc_pagar
            economia_potencial = total - fio_b_a_pagar - dados.get('cip', 0)
            
            k1, k2, k3 = st.columns(3)
            k1.metric("Fio B a Pagar", f"R$ {fio_b_a_pagar:.2f}", f"{perc_pagar*100}% da Regra")
            k2.metric("Nova Conta Estimada", f"R$ {fio_b_a_pagar + dados.get('cip', 0):.2f}", "Fio B + CIP")
            k3.metric("Economia Máxima", f"R$ {economia_potencial:.2f}", "Potencial")
            
            with st.expander("Ver JSON Bruto da IA"):
                st.json(dados)
