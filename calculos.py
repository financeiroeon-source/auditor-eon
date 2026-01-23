def realizar_auditoria_gd(dados_ocr, geracao_inversor):
    # Coleta de dados brutos
    cons_rede = float(dados_ocr.get('consumo_kwh', 0))
    injetada = float(dados_ocr.get('injetada_kwh', 0))
    valor_pago = float(dados_ocr.get('valor_total', 0))
    compensada = float(dados_ocr.get('compensada_kwh', 0))
    
    # 1. Cálculo do Consumo Instantâneo (Item 7)
    # Tudo que gerou menos o que sobrou (injetou)
    cons_instantaneo = max(0, geracao_inversor - injetada)
    
    # 2. Carga Real (O que a casa realmente consumiu)
    carga_total = cons_rede + cons_instantaneo
    
    # 3. Simulação Sem Solar (Item 8)
    # Estimamos a tarifa média dividindo o valor pago pelo que foi consumido da rede
    tarifa_estimada = valor_pago / (cons_rede if cons_rede > 0 else 1)
    conta_sem_solar = carga_total * tarifa_estimada
    
    # 4. Economia (Itens 9 e 10)
    economia_reais = conta_sem_solar - valor_pago
    economia_perc = (economia_reais / conta_sem_solar) * 100 if conta_sem_solar > 0 else 0
    
    # 5. Selo de Verificação (Item 14)
    if geracao_inversor >= injetada:
        selo = "✅ Integridade Matemática Confirmada"
    else:
        selo = "⚠️ Alerta: Geração menor que Injeção. Verifique os dados."

    return {
        "consumo_instantaneo": cons_instantaneo,
        "conta_sem_solar": conta_sem_solar,
        "economia_reais": economia_reais,
        "economia_perc": economia_perc,
        "selo": selo,
        "carga_total": carga_total
    }
