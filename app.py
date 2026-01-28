import streamlit as st
import google.generativeai as genai
import os

st.set_page_config(page_title="Diagnóstico Google API", page_icon="🔧")

st.title("🔧 Diagnóstico de Conexão Google AI")

# 1. Teste da Chave
st.header("1. Verificando Chave API")
try:
    if "GOOGLE_API_KEY" in st.secrets:
        api_key = st.secrets["GOOGLE_API_KEY"]
        # Mostra apenas os 4 primeiros e 4 últimos dígitos por segurança
        masked_key = f"{api_key[:4]}...{api_key[-4:]}"
        st.success(f"Chave encontrada nos Secrets: {masked_key}")
        genai.configure(api_key=api_key)
    else:
        st.error("❌ Nenhuma chave 'GOOGLE_API_KEY' encontrada nos Secrets.")
        st.stop()
except Exception as e:
    st.error(f"Erro ao ler secrets: {e}")
    st.stop()

# 2. Teste de Versão da Biblioteca
st.header("2. Versão da Biblioteca")
try:
    st.info(f"Versão do google-generativeai instalada: {genai.__version__}")
except:
    st.error("Não foi possível ler a versão da biblioteca.")

# 3. Teste de Conexão e Listagem de Modelos
st.header("3. Testando Conexão com Google...")

if st.button("🔍 Rodar Diagnóstico de Modelos"):
    with st.status("Conectando aos servidores do Google...", expanded=True) as status:
        try:
            # Tenta listar os modelos
            st.write("Solicitando lista de modelos...")
            modelos = list(genai.list_models())
            
            status.update(label="Conexão realizada!", state="complete")
            
            if not modelos:
                st.warning("⚠️ Conexão feita, mas a lista de modelos veio VAZIA.")
                st.markdown("""
                **Causas Prováveis:**
                1. A API "Generative Language API" não está habilitada no Google Cloud.
                2. A chave API tem restrições de IP ou API.
                """)
            else:
                st.success(f"✅ Sucesso! Encontramos {len(modelos)} modelos disponíveis para sua chave.")
                
                # Filtra e mostra os modelos que servem para gerar texto
                modelos_texto = [m for m in modelos if 'generateContent' in m.supported_generation_methods]
                
                st.subheader("Modelos de Texto Disponíveis:")
                for m in modelos_texto:
                    st.code(f"Nome: {m.name} \nDisplay: {m.display_name}")
                    
        except Exception as e:
            status.update(label="Falha na Conexão", state="error")
            st.error(f"❌ Erro Crítico de Conexão: {e}")
            st.markdown("""
            **O que esse erro significa:**
            * **403 Permission Denied:** Sua chave existe, mas o faturamento ou a API não estão ativos no Google Cloud.
            * **404 Not Found:** A biblioteca está tentando acessar um endereço errado (versão muito antiga).
            * **400 Bad Request:** Chave inválida.
            """)