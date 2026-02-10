import pdfplumber
import re
from datetime import datetime

def converter_valor_br(texto_valor):
    """Converte string '1.234,56' para float 1234.56"""
    try:
        # Remove pontos de milhar e troca vírgula decimal por ponto
        limpo = texto_valor.replace('.', '').replace(',', '.')
        return float(limpo)
    except:
        return 0.0

def extrair_dados_fatura(arquivo):
    """
    Scanner Completo da Fatura de Energia.
    Busca: TUSD, TE, Energia Injetada, CIP e Datas.
    Retorna: Tarifa Média Real (R$/kWh) e Totais.
    """
    dados = {
        "mes_referencia": None,
        "consumo_kwh": 0.0,
        "valor_consumo_total": 0.0,  # Soma de TUSD + TE + Bandeiras
        "tarifa_consumo_calc": 0.0,  # Tarifa Real Calculada
        "injetado_kwh": 0.0,
        "valor_credito_total": 0.0,
        "tarifa_credito_calc": 0.0,  # Tarifa de compensação (pode ser menor que a de consumo)
        "cip_cosip": 0.0,            # Iluminação Pública
        "texto_completo": ""
    }

    try:
        with pdfplumber.open(arquivo) as pdf:
            texto = ""
            for page in pdf.pages:
                texto += page.extract_text() + "\n"
            
            dados["texto_completo"] = texto
            
            # Divide o texto em linhas para analisar item a item
            linhas = texto.split('\n')

            for linha in linhas:
                linha_upper = linha.upper()

                # --- 1. CAPTURA DE CONSUMO (TUSD + TE + ENERGIA) ---
                # Padrão: Descrição ... kWh ... Qtd ... Tarif ... Valor
                if ("ENERGIA ELETR" in linha_upper or "CONSUMO" in linha_upper or "TUSD" in linha_upper or "TE " in linha_upper) and "KWH" in linha_upper and "INJETADA" not in linha_upper and "COMPENSADA" not in linha_upper:
                    
                    # Regex para pegar: Quantidade (coluna variável) e Valor Final (última coluna monetária)
                    # Procura numeros no formato XX,XX
                    numeros = re.findall(r'\d+[\.,]\d+', linha)
                    
                    if len(numeros) >= 2:
                        # Geralmente: Qtd é um dos primeiros, Valor é o último
                        qtd = converter_valor_br(numeros[0]) # Assumindo 1º número como Qtd
                        valor = converter_valor_br(numeros[-1]) # Assumindo último como Valor R$
                        
                        # Filtro de segurança para não somar tarifas (que são pequenas, tipo 0,95) como consumo
                        if qtd > 10: 
                            dados["consumo_kwh"] = max(dados["consumo_kwh"], qtd) # Pega o maior valor de consumo achado (geralmente o total)
                            dados["valor_consumo_total"] += valor

                # --- 2. CAPTURA DE ENERGIA INJETADA (GD) ---
                if ("INJETADA" in linha_upper or "COMPENSADA" in linha_upper or "GD I" in linha_upper) and "KWH" in linha_upper:
                    numeros = re.findall(r'\d+[\.,]\d+', linha)
                    if len(numeros) >= 2:
                        qtd = converter_valor_br(numeros[0])
                        valor = converter_valor_br(numeros[-1])
                        
                        dados["injetado_kwh"] += qtd
                        dados["valor_credito_total"] += valor

                # --- 3. CAPTURA DE ILUMINAÇÃO PÚBLICA (CIP/COSIP) ---
                if ("ILUM" in linha_upper or "CIP" in linha_upper or "COSIP" in linha_upper) and ("CONTRIB" in linha_upper or "MUNIC" in linha_upper):
                    numeros = re.findall(r'\d+[\.,]\d+', linha)
                    if numeros:
                        dados["cip_cosip"] = converter_valor_br(numeros[-1])

                # --- 4. DATA DE REFERÊNCIA ---
                if not dados["mes_referencia"]:
                    match_data = re.search(r'\b(JAN|FEV|MAR|ABR|MAI|JUN|JUL|AGO|SET|OUT|NOV|DEZ)[/ ]?20\d{2}\b', linha_upper)
                    if match_data:
                        meses = {"JAN": 1, "FEV": 2, "MAR": 3, "ABR": 4, "MAI": 5, "JUN": 6, "JUL": 7, "AGO": 8, "SET": 9, "OUT": 10, "NOV": 11, "DEZ": 12}
                        mes_str = match_data.group(0)[:3]
                        ano_str = match_data.group(0)[-4:]
                        try:
                            dados["mes_referencia"] = datetime(int(ano_str), meses[mes_str], 1).date()
                        except: pass

            # --- CÁLCULOS FINAIS ---
            # Calcula a tarifa média real (R$ Total / kWh Total)
            # Isso inclui ICMS, PIS, COFINS automaticamente, pois pega o valor final da linha.
            if dados["consumo_kwh"] > 0:
                dados["tarifa_consumo_calc"] = round(dados["valor_consumo_total"] / dados["consumo_kwh"], 4)
            
            # A tarifa de crédito pode ser diferente (se não houver isenção total de TUSD)
            if dados["injetado_kwh"] > 0:
                dados["tarifa_credito_calc"] = round(dados["valor_credito_total"] / dados["injetado_kwh"], 4)

            return dados

    except Exception as e:
        print(f"Erro ao processar PDF: {e}")
        return dados
