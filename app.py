import streamlit as st
import google.generativeai as genai

st.set_page_config(page_title="Diagnóstico EON", page_icon="🔧")

st.title("🔧 Modo de Diagnóstico EON")

api_key = st.text_input("Cole sua API Key para testar:", type="password")

if st.button("Testar Conexão e Listar Modelos"):
    if not api_key:
        st.warning("Cole a chave primeiro.")
    else:
        try:
            # Configura a chave
            genai.configure(api_key=api_key)
            
            st.info("Tentando conectar ao Google...")
            
            # Tenta listar os modelos disponíveis para esta chave
            modelos = list(genai.list_models())
            
            st.success("✅ Conexão BEM SUCEDIDA! A chave está funcionando.")
            st.markdown("### Modelos que sua chave pode acessar:")
            
            nomes_modelos = []
            for m in modelos:
                # Filtra apenas modelos que geram texto (generateContent)
                if 'generateContent' in m.supported_generation_methods:
                    st.write(f"- **{m.name}** ({m.display_name})")
                    nomes_modelos.append(m.name)
            
            st.markdown("---")
            
            # Teste prático de geração
            st.markdown("### 🧪 Teste de Geração Real")
            modelo_teste = ""
            
            # Tenta escolher o melhor modelo disponível na lista
            if 'models/gemini-1.5-flash' in nomes_modelos:
                modelo_teste = 'gemini-1.5-flash'
            elif 'models/gemini-pro' in nomes_modelos:
                modelo_teste = 'gemini-pro'
            else:
                modelo_teste = nomes_modelos[0] if nomes_modelos else ""
            
            if modelo_teste:
                st.write(f"Tentando gerar 'Olá' usando o modelo: `{modelo_teste}`...")
                model = genai.GenerativeModel(modelo_teste)
                response = model.generate_content("Diga apenas 'Olá EON' se estiver me ouvindo.")
                st.success(f"🤖 Resposta da IA: **{response.text}**")
            else:
                st.error("Nenhum modelo de texto encontrado na lista.")
                
        except Exception as e:
            st.error(f"❌ Ocorreu um erro: {e}")
            st.write("Dica: Se o erro for 'API_KEY_INVALID', sua chave está errada. Se for 404, o servidor está desatualizado.")
