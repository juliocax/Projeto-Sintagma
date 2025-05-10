from fuzzywuzzy import fuzz
from fuzzywuzzy import process
import pandas as pd
import datetime
import json
import os
import re

CAMINHO_CATEGORIAS_BASE_JSON = "Categorias.json"
CAMINHO_PRINCIPAL_PROCESSADO_DEFAULT_PREFIXO = "CNPJ_Estabelecimentos"
COLUNA_ESTAB_PRINCIPAL_DEFAULT = 'Column5'
COLUNA_ATIVIDADE_PRINCIPAL_DEFAULT = 'Grupo_Atividade'
COLUNA_DATA = 'date'
COLUNA_TITULO = 'title'
COLUNA_VALOR = 'amount'
COLUNA_CATEGORIA= 'category_nubank_original'
COLUNA_ID = 'id_nubank_original'
COLUNA_CATEGORIA = 'categoria_final'
COLUNA_TITULO_NORMALIZADO = 'title_normalized'
COLUNA_PARCELA_ATUAL = 'parcela_atual'
COLUNA_TOTAL_PARCELAS = 'total_parcelas'
COLUNA_FATURA_ORIGEM = 'fatura_origem'
COLUNA_EDIT_ID = 'edit_id'
SIMILARITY_THRESHOLD = 95

def carregar_categorias_base_do_json(caminho_arquivo=CAMINHO_CATEGORIAS_BASE_JSON):
    if os.path.exists(caminho_arquivo):
        try:
            with open(caminho_arquivo, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
                else:
                    print(f"Erro: Conteúdo de {caminho_arquivo} não é um dicionário. Retornando dicionário vazio.")
                    return {}
        except json.JSONDecodeError as e:
            print(f"Erro ao decodificar JSON em {caminho_arquivo}: {e}. Retornando dicionário vazio.")
            return {}
        except Exception as e:
            print(f"Erro inesperado ao carregar {caminho_arquivo}: {e}. Retornando dicionário vazio.")
            return {}
    return {}

def salvar_categorias_base_para_json(dicionario_categorias, caminho_arquivo=CAMINHO_CATEGORIAS_BASE_JSON):
    try:
        with open(caminho_arquivo, 'w', encoding='utf-8') as f:
            json.dump(dicionario_categorias, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Erro ao salvar categorias base em {caminho_arquivo}: {e}")
        return False

def exibir_mensagem_progresso(streamlit_log_area, mensagem, tipo='info'):
    if streamlit_log_area:
        if hasattr(streamlit_log_area, tipo):
            getattr(streamlit_log_area, tipo)(mensagem)
        else:
            streamlit_log_area.text(f"[{tipo.upper()}] {mensagem}")
    print(f"PROGRESSO APP ({tipo}): {mensagem}")

def normalizar_texto(texto):
    if pd.isna(texto): return ""
    s = str(texto)
    s = re.sub(r"(?i)(\s*-\s*)?\bparcela\s+\d+/\d+\b", "", s)
    s = re.sub(r"(?<!\d{2}:\d{2}\s)(?<!\d{2}[-/]\d{2}[-/]\d{4}\s)\b\d+/\d+\b", "", s, flags=re.IGNORECASE)
    s = s.lower().strip()
    s = re.sub(r'\s+', ' ', s)
    return s

def extrair_info_parcela(titulo_original):
    if pd.isna(titulo_original):
        return None, None
    match_completo = re.search(r"(?i)\bparcela\s+(\d+)/(\d+)\b", str(titulo_original))
    if match_completo:
        return int(match_completo.group(1)), int(match_completo.group(2))
    match_simples = re.search(r"(?<![\w\d/])(\d{1,2})/(\d{1,2})\b(?![\w\d/])", str(titulo_original))
    if match_simples:
        texto_antes = str(titulo_original)[:match_simples.start()].strip()
        if not re.search(r"\d{2}:\d{2}$|\d{2}-\d{2}-\d{4}$|\b\w+id\b$|\bcod\b$|\bref\b$", texto_antes, re.IGNORECASE):
            parc_atual, parc_total = int(match_simples.group(1)), int(match_simples.group(2))
            if parc_total > 0 and parc_atual > 0 and parc_atual <= parc_total:
                return parc_atual, parc_total
    return None, None

def _categorizar_transacao_core(titulo_fatura_normalizado,
                                categorias_base_palavras_chave_norm_para_keywords,
                                categorias_orig_norm_para_orig_map,
                                usar_fuzzy_estabelecimentos,
                                lista_estab_norm_lookup,
                                mapa_estab_atividade,
                                threshold):
    if titulo_fatura_normalizado in categorias_orig_norm_para_orig_map:
        return categorias_orig_norm_para_orig_map[titulo_fatura_normalizado]
    for categoria_original, palavras_chave_normalizadas in categorias_base_palavras_chave_norm_para_keywords.items():
        for palavra_chave_norm in palavras_chave_normalizadas:
            if palavra_chave_norm and palavra_chave_norm in titulo_fatura_normalizado:
                return categoria_original
    if usar_fuzzy_estabelecimentos and lista_estab_norm_lookup:
        if not titulo_fatura_normalizado.strip():
            return 'Sem Categoria (Título Vazio)'
        try:
            melhor_match_info = process.extractOne(titulo_fatura_normalizado, lista_estab_norm_lookup, scorer=fuzz.WRatio, score_cutoff=threshold)
        except Exception:
            return 'Erro Fuzzy Match'
        if melhor_match_info:
            nome_estab_correspondente, pontuacao = melhor_match_info
            if nome_estab_correspondente in mapa_estab_atividade:
                return mapa_estab_atividade[nome_estab_correspondente]
            else:
                return 'Sem Categoria (Fuzzy - Mapa Principal Vazio)'
        else:
            return 'Sem Categoria (Fuzzy - Baixa Similaridade)'
    return 'Sem Categoria/Pix Credito'

def processar_faturas(lista_arquivos_faturas,
                      usar_categorizacao_especifica,
                      caminho_arquivo_estabelecimentos,
                      streamlit_log_area=None,
                      col_estab_principal=COLUNA_ESTAB_PRINCIPAL_DEFAULT,
                      col_ativ_principal=COLUNA_ATIVIDADE_PRINCIPAL_DEFAULT):
    exibir_mensagem_progresso(streamlit_log_area, "Iniciando processamento das faturas...", tipo='info')
    categorias_base_atuais = carregar_categorias_base_do_json()
    if not categorias_base_atuais:
        exibir_mensagem_progresso(streamlit_log_area, "AVISO: Arquivo de categorias base (Categorias.json) não encontrado ou inválido. A categorização por palavras-chave não funcionará.", tipo='warning')
    df_todas_faturas_list = []
    total_transacoes_lidas_validas = 0
    for i, uploaded_file_obj in enumerate(lista_arquivos_faturas):
        nome_arquivo = uploaded_file_obj.name if hasattr(uploaded_file_obj, 'name') else f"Arquivo_{i+1}"
        exibir_mensagem_progresso(streamlit_log_area, f"Lendo arquivo {i+1}/{len(lista_arquivos_faturas)}: {nome_arquivo}", tipo='info')
        try:
            df_fatura_atual = pd.read_csv(uploaded_file_obj, on_bad_lines='warn')
            colunas_obrigatorias = [COLUNA_DATA, COLUNA_TITULO, COLUNA_VALOR]
            if not all(col in df_fatura_atual.columns for col in colunas_obrigatorias):
                exibir_mensagem_progresso(streamlit_log_area, f"AVISO: Arquivo {nome_arquivo} não contém colunas esperadas ({', '.join(colunas_obrigatorias)}). Pulando.", tipo='warning')
                continue
            df_fatura_atual[COLUNA_TITULO] = df_fatura_atual[COLUNA_TITULO].astype(str)
            df_fatura_atual[COLUNA_VALOR] = pd.to_numeric(df_fatura_atual[COLUNA_VALOR], errors='coerce')
            df_fatura_atual[COLUNA_DATA] = pd.to_datetime(df_fatura_atual[COLUNA_DATA], errors='coerce')
            df_fatura_atual.dropna(subset=colunas_obrigatorias + [COLUNA_VALOR], inplace=True)
            if df_fatura_atual.empty:
                exibir_mensagem_progresso(streamlit_log_area, f"AVISO: Arquivo {nome_arquivo} sem transações válidas após limpeza inicial. Pulando.", tipo='warning')
                continue
            total_transacoes_lidas_validas += len(df_fatura_atual)
            df_fatura_atual[COLUNA_TITULO_NORMALIZADO] = df_fatura_atual[COLUNA_TITULO].apply(normalizar_texto)
            parcel_info = df_fatura_atual[COLUNA_TITULO].apply(extrair_info_parcela)
            df_fatura_atual[COLUNA_PARCELA_ATUAL] = parcel_info.apply(lambda x: x[0])
            df_fatura_atual[COLUNA_TOTAL_PARCELAS] = parcel_info.apply(lambda x: x[1])
            df_fatura_atual[COLUNA_FATURA_ORIGEM] = nome_arquivo
            if 'category' in df_fatura_atual.columns:
                df_fatura_atual.rename(columns={'category': COLUNA_CATEGORIA}, inplace=True)
            if 'id' in df_fatura_atual.columns:
                df_fatura_atual.rename(columns={'id': COLUNA_ID}, inplace=True)
            df_todas_faturas_list.append(df_fatura_atual)
        except Exception as e:
            exibir_mensagem_progresso(streamlit_log_area, f"ERRO CRÍTICO ao ler/processar {nome_arquivo}: {e}", tipo='error')
    if not df_todas_faturas_list:
        exibir_mensagem_progresso(streamlit_log_area, "Nenhuma fatura processada com sucesso ou nenhuma transação válida encontrada.", tipo='error')
        return pd.DataFrame()
    df_faturas_consolidadas = pd.concat(df_todas_faturas_list, ignore_index=True)
    exibir_mensagem_progresso(streamlit_log_area, f"{total_transacoes_lidas_validas} transações consolidadas. Preparando categorização...", tipo='info')
    lista_nomes_estab_normalizados_lookup = []
    map_nome_norm_para_atividade_lookup = {}
    if usar_categorizacao_especifica and caminho_arquivo_estabelecimentos:
        exibir_mensagem_progresso(streamlit_log_area, f"Carregando dados de estabelecimentos de: {caminho_arquivo_estabelecimentos}", tipo='info')
        try:
            df_principal_completo = pd.read_csv(caminho_arquivo_estabelecimentos, sep=';', encoding='utf-8-sig', on_bad_lines='warn', low_memory=False)
            if col_estab_principal in df_principal_completo.columns and col_ativ_principal in df_principal_completo.columns:
                df_principal_estab = df_principal_completo[[col_estab_principal, col_ativ_principal]].astype(str).copy()
                df_principal_estab.dropna(subset=[col_estab_principal, col_ativ_principal], inplace=True)
                df_principal_estab['nome_estab_normalized_principal'] = df_principal_estab[col_estab_principal].apply(normalizar_texto)
                df_principal_estab.drop_duplicates(subset=['nome_estab_normalized_principal'], keep='first', inplace=True)
                lista_nomes_estab_normalizados_lookup = df_principal_estab['nome_estab_normalized_principal'].unique().tolist()
                map_nome_norm_para_atividade_lookup = pd.Series(df_principal_estab[col_ativ_principal].values, index=df_principal_estab['nome_estab_normalized_principal']).to_dict()
                exibir_mensagem_progresso(streamlit_log_area, f"{len(lista_nomes_estab_normalizados_lookup)} estabelecimentos únicos carregados para lookup.", tipo='info')
            else:
                exibir_mensagem_progresso(streamlit_log_area, f"AVISO: Colunas '{col_estab_principal}' ou '{col_ativ_principal}' não encontradas no arquivo de estabelecimentos. Categorização por CNPJ desativada.", tipo='warning')
                usar_categorizacao_especifica = False
        except FileNotFoundError:
            exibir_mensagem_progresso(streamlit_log_area, f"ERRO: Arquivo de estabelecimentos '{caminho_arquivo_estabelecimentos}' não encontrado. Categorização por CNPJ desativada.", tipo='error')
            usar_categorizacao_especifica = False
        except Exception as e:
            exibir_mensagem_progresso(streamlit_log_area, f"ERRO ao processar arquivo de estabelecimentos: {e}. Categorização por CNPJ desativada.", tipo='error')
            usar_categorizacao_especifica = False
    categorias_base_palavras_chave_norm_para_keywords = {
        cat_orig: [normalizar_texto(kw) for kw in kws_orig if kw and isinstance(kw, str)] 
        for cat_orig, kws_orig in categorias_base_atuais.items() if isinstance(kws_orig, list) 
    }
    categorias_orig_norm_para_orig_map = {
        normalizar_texto(cat_orig): cat_orig
        for cat_orig in categorias_base_atuais.keys()
    }
    exibir_mensagem_progresso(streamlit_log_area, "Categorizando transações...", tipo='info')
    if not df_faturas_consolidadas.empty:
        df_faturas_consolidadas[COLUNA_CATEGORIA] = df_faturas_consolidadas.apply(
            lambda row: _categorizar_transacao_core(
                row[COLUNA_TITULO_NORMALIZADO],
                categorias_base_palavras_chave_norm_para_keywords,
                categorias_orig_norm_para_orig_map,
                usar_categorizacao_especifica,
                lista_nomes_estab_normalizados_lookup,
                map_nome_norm_para_atividade_lookup,
                SIMILARITY_THRESHOLD
            ),
            axis=1
        )
    else:
        exibir_mensagem_progresso(streamlit_log_area, "Nenhuma transação para categorizar.", tipo='info')
    if COLUNA_TITULO_NORMALIZADO in df_faturas_consolidadas.columns:
        df_faturas_consolidadas.drop(columns=[COLUNA_TITULO_NORMALIZADO], inplace=True)
    exibir_mensagem_progresso(streamlit_log_area, "Processamento concluído!", tipo='success')
    return df_faturas_consolidadas

categorias_base_palavras_chave = carregar_categorias_base_do_json()
