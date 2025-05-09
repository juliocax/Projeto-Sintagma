# dashboard_faturas.py
from dateutil.relativedelta import relativedelta
import plotly.graph_objects as go
from datetime import datetime, timedelta
import plotly.express as px
import streamlit as st
import pandas as pd
import numpy as np
import re
import json
import os

from categorizador import (
    processar_faturas,
    carregar_categorias_base_do_json,
    salvar_categorias_base_para_json,
    CAMINHO_CATEGORIAS_BASE_JSON,
    COLUNA_DATA, COLUNA_TITULO, COLUNA_VALOR, COLUNA_CATEGORIA,
    COLUNA_PARCELA_ATUAL, COLUNA_TOTAL_PARCELAS, COLUNA_FATURA_ORIGEM,
    COLUNA_EDIT_ID, CAMINHO_PRINCIPAL_PROCESSADO_DEFAULT_PREFIXO,
    normalizar_texto
)

st.set_page_config(layout="wide", page_title="Análise de Faturas Pessoal")

nome_arquivo_imagem = "Logo0.png"

try:
    col1, col2 = st.columns([2, 2])
    with col1:
        st.image(nome_arquivo_imagem, use_container_width=True)
    with col2:
        st.title("Syn(tagmᵃ) Visualizador de uso do Cartão de Crédito")


except FileNotFoundError:
    st.error(f"Erro: A imagem '{nome_arquivo_imagem}' não foi encontrada. Verifique o caminho e o nome do arquivo.")
except Exception as e:
    st.error(f"Ocorreu um erro ao carregar a imagem: {e}")

st.markdown("Este painel interativo permite analisar seus gastos de cartão de crédito, identificar padrões e gerenciar suas finanças de forma mais eficaz.")
st.markdown("---")

CATEGORIAS_CREDITO_AJUSTE = [
    'Pagamento de Fatura', 'Estorno', 'Ajustes Financeiros Nubank',
    'Ajuste Parcelamento Fatura', 'Encerramento de dívida', 'Crédito Diversos'
]
CATEGORIAS_ENCARGOS_FINANCEIROS_NAO_CONSUMO = [
    'Juros de dívida encerrada', 'IOF de atraso',
    'Multa de atraso', 'Juros e Taxas Diversas', 'Taxas'
]
CATEGORIA_ENCARGOS_PARCELAMENTO_FATURA = "Encargos de Parcelamento Fatura"
CATEGORIAS_AJUSTE_SALDO_DEVEDOR = [
    'Saldo em atraso',
    'Crédito de atraso'
]
CATEGORIAS_NAO_CONSUMO_GERAL = list(set(
    CATEGORIAS_CREDITO_AJUSTE +
    CATEGORIAS_ENCARGOS_FINANCEIROS_NAO_CONSUMO +
    [CATEGORIA_ENCARGOS_PARCELAMENTO_FATURA] +
    CATEGORIAS_AJUSTE_SALDO_DEVEDOR
))
CATEGORIAS_ESSENCIAIS_PARA_EDICAO = sorted(list(set(
    CATEGORIAS_NAO_CONSUMO_GERAL +
    ["Sem Categoria", "Erro Fuzzy Match", "Sem Categoria (Fuzzy - Mapa Principal)",
     "Sem Categoria (Lookup Principal Vazio)", "Sem Categoria (Título Vazio)", "Sem Categoria/Pix Credito"]
)))
CATEGORIA_PAGAMENTO_FATURA = "Pagamento de Fatura"


def extrair_ciclo_do_nome_arquivo(nome_arquivo):
    if not isinstance(nome_arquivo, str): return None
    match = re.search(r'(\d{4}-\d{2})', nome_arquivo)
    if match: return match.group(1)
    else: log_mensagem_app(f"Não foi possível extrair o ciclo YYYY-MM do nome: {nome_arquivo}", "warning"); return "Sem Ciclo Definido"

def log_mensagem_app(mensagem, tipo='info'):
    if 'log_messages' not in st.session_state or st.session_state.log_messages == ["Aqui aparecerão as mensagens de informação do processo."]:
        st.session_state.log_messages = []
    prefixo_emoji = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌"}
    st.session_state.log_messages.append(f"{prefixo_emoji.get(tipo, '')} {mensagem}")
    MAX_LOG_MESSAGES = 20
    if len(st.session_state.log_messages) > MAX_LOG_MESSAGES:
        st.session_state.log_messages = st.session_state.log_messages[-MAX_LOG_MESSAGES:]

def inicializar_session_state():
    defaults = {
        'df_processado': pd.DataFrame(),
        'tipo_categorizacao_selecionada': "Genérica (Base Editável)",
        'estado_cnpj_selecionado': "Paraíba", 'municipio_cnpj_selecionado': "João Pessoa",
        'filtros_sidebar': {'periodos_ciclo_arquivo': ["Todos"], 'categorias_despesa': ["Todos"]},
        'nomes_arquivos_faturas_ja_processados': set(),
        'arquivo_sessao_uploader_key': 0,
        'log_messages': ["Aqui aparecerão as mensagens de informação do processo."],
        'edit_search_term': "", 'edit_category_filter': "Todas", 'edit_current_page': 1,
        'categorias_base_memoria': carregar_categorias_base_do_json(),
        'ciclos_consulta_selecionados': []
    }
    for key, value in defaults.items():
        if key not in st.session_state: st.session_state[key] = value
    
    # Ensure nested keys in filtros_sidebar also exist
    if 'filtros_sidebar' in st.session_state:
        st.session_state.filtros_sidebar.setdefault('periodos_ciclo_arquivo', ["Todos"])
        st.session_state.filtros_sidebar.setdefault('categorias_despesa', ["Todos"])

    if 'categorias_editaveis' not in st.session_state or not st.session_state.categorias_editaveis:
        base_memoria = st.session_state.categorias_base_memoria if isinstance(st.session_state.categorias_base_memoria, dict) else {}
        lista_cats = sorted(list(base_memoria.keys()))
        for cat_essencial in CATEGORIAS_ESSENCIAIS_PARA_EDICAO:
            if cat_essencial not in lista_cats: lista_cats.append(cat_essencial)
        st.session_state.categorias_editaveis = sorted(list(set(lista_cats)))

def gerar_dados_sessao_para_salvar():
    df_para_salvar = st.session_state.df_processado.copy()
    cols_to_drop = ['ciclo_fatura', 'mes_ano', 'ano', 'mes', 'dia_da_semana', 'dia_do_mes'] # Add any other derived columns
    for col in cols_to_drop:
        if col in df_para_salvar.columns: df_para_salvar = df_para_salvar.drop(columns=[col])
    estado_para_salvar = {
        'df_processado_json': df_para_salvar.to_json(orient='split', date_format='iso') if not df_para_salvar.empty else None,
        'tipo_categorizacao_selecionada': st.session_state.tipo_categorizacao_selecionada,
        'estado_cnpj_selecionado': st.session_state.estado_cnpj_selecionado,
        'municipio_cnpj_selecionado': st.session_state.municipio_cnpj_selecionado,
        'filtros_sidebar': st.session_state.filtros_sidebar,
        'nomes_arquivos_faturas_ja_processados': list(st.session_state.nomes_arquivos_faturas_ja_processados),
        'edit_search_term': st.session_state.edit_search_term,
        'edit_category_filter': st.session_state.edit_category_filter,
        'edit_current_page': st.session_state.edit_current_page,
        'categorias_base_memoria_json': st.session_state.categorias_base_memoria,
        'ciclos_consulta_selecionados': st.session_state.get('ciclos_consulta_selecionados', []),
        'timestamp_salvo': datetime.now().isoformat(),
    }
    return json.dumps(estado_para_salvar, indent=4, ensure_ascii=False)

def carregar_dados_sessao_do_arquivo(uploaded_file_content):
    try:
        estado_carregado = json.loads(uploaded_file_content)
        df_json = estado_carregado.get('df_processado_json')
        if df_json:
            st.session_state.df_processado = pd.read_json(df_json, orient='split', convert_dates=[COLUNA_DATA])
            if not st.session_state.df_processado.empty:
                if COLUNA_DATA in st.session_state.df_processado.columns:
                    st.session_state.df_processado[COLUNA_DATA] = pd.to_datetime(st.session_state.df_processado[COLUNA_DATA], errors='coerce')
                if COLUNA_EDIT_ID not in st.session_state.df_processado.columns:
                    st.session_state.df_processado.reset_index(drop=True, inplace=True); st.session_state.df_processado[COLUNA_EDIT_ID] = st.session_state.df_processado.index
        else: st.session_state.df_processado = pd.DataFrame()
        st.session_state.tipo_categorizacao_selecionada = estado_carregado.get('tipo_categorizacao_selecionada', "Genérica (Base Editável)")
        st.session_state.estado_cnpj_selecionado = estado_carregado.get('estado_cnpj_selecionado', "Paraíba")
        st.session_state.municipio_cnpj_selecionado = estado_carregado.get('municipio_cnpj_selecionado', "João Pessoa")
        
        filtros_carregados = estado_carregado.get('filtros_sidebar', {})
        st.session_state.filtros_sidebar = {
            'periodos_ciclo_arquivo': filtros_carregados.get('periodos_ciclo_arquivo', ["Todos"]),
            'categorias_despesa': filtros_carregados.get('categorias_despesa', ["Todos"])
        }
        
        st.session_state.nomes_arquivos_faturas_ja_processados = set(estado_carregado.get('nomes_arquivos_faturas_ja_processados', []))
        st.session_state.edit_search_term = estado_carregado.get('edit_search_term', ""); st.session_state.edit_category_filter = estado_carregado.get('edit_category_filter', "Todas"); st.session_state.edit_current_page = estado_carregado.get('edit_current_page', 1)
        st.session_state.ciclos_consulta_selecionados = estado_carregado.get('ciclos_consulta_selecionados', [])
        
        categorias_base_salvas = estado_carregado.get('categorias_base_memoria_json')
        if categorias_base_salvas and isinstance(categorias_base_salvas, dict): st.session_state.categorias_base_memoria = categorias_base_salvas
        else: st.session_state.categorias_base_memoria = carregar_categorias_base_do_json()
        
        base_memoria = st.session_state.categorias_base_memoria if isinstance(st.session_state.categorias_base_memoria, dict) else {}; lista_cats = sorted(list(base_memoria.keys()))
        for cat_essencial in CATEGORIAS_ESSENCIAIS_PARA_EDICAO:
            if cat_essencial not in lista_cats: lista_cats.append(cat_essencial)
        st.session_state.categorias_editaveis = sorted(list(set(lista_cats)))
        
        st.sidebar.success(f"Progresso carregado!"); log_mensagem_app(f"Sessão carregada (salva em {estado_carregado.get('timestamp_salvo', 'data desconhecida')}).", "success"); st.session_state.arquivo_sessao_uploader_key += 1; st.rerun()
    except Exception as e: st.sidebar.error(f"Erro ao carregar sessão: {e}"); log_mensagem_app(f"Falha ao carregar sessão: {e}", "error")

inicializar_session_state()

st.sidebar.header("⚙️ Controles do Dashboard")
st.sidebar.subheader("1. Arquivos de Fatura")
uploaded_files = st.sidebar.file_uploader("Selecione CSVs de fatura:", type=["csv"], accept_multiple_files=True, key="file_uploader_faturas_v15")
st.sidebar.subheader("2. Tipo de Categorização")
tipo_cat_selecionada_key = "radio_tipo_cat_v15"
st.session_state.tipo_categorizacao_selecionada = st.sidebar.radio("Método:", ["Genérica (Base Editável)", "Específica (Base Editável + CNPJ Gov)"], index=0 if st.session_state.tipo_categorizacao_selecionada.startswith("Genérica") else 1, key=tipo_cat_selecionada_key)
usar_cat_especifica_bool = st.session_state.tipo_categorizacao_selecionada.startswith("Específica")
caminho_arquivo_estab_final = None
if usar_cat_especifica_bool:
    st.sidebar.subheader("3. Base de Dados CNPJ")
    opcoes_locais_cnpj = {"Paraíba": {"Joao_Pessoa": "João Pessoa"}}; lista_estados_disponiveis = list(opcoes_locais_cnpj.keys())
    if st.session_state.estado_cnpj_selecionado not in lista_estados_disponiveis: st.session_state.estado_cnpj_selecionado = lista_estados_disponiveis[0] if lista_estados_disponiveis else None
    st.session_state.estado_cnpj_selecionado = st.sidebar.selectbox("Estado:", lista_estados_disponiveis, index=lista_estados_disponiveis.index(st.session_state.estado_cnpj_selecionado) if st.session_state.estado_cnpj_selecionado in lista_estados_disponiveis else 0, key="select_estado_cnpj_v15")
    municipios_do_estado_map = opcoes_locais_cnpj.get(st.session_state.estado_cnpj_selecionado, {}); lista_municipios_display = list(municipios_do_estado_map.values())
    idx_municipio_selecionado = 0; municipio_selecionado_display = st.session_state.municipio_cnpj_selecionado
    if municipio_selecionado_display in lista_municipios_display: idx_municipio_selecionado = lista_municipios_display.index(municipio_selecionado_display)
    elif lista_municipios_display: municipio_selecionado_display = lista_municipios_display[0]
    st.session_state.municipio_cnpj_selecionado = st.sidebar.selectbox("Município:", lista_municipios_display, index=idx_municipio_selecionado, key="select_municipio_cnpj_v15", disabled=not bool(lista_municipios_display))
    if st.session_state.estado_cnpj_selecionado and st.session_state.municipio_cnpj_selecionado:
        uf_map = {"Paraíba": "PB"}; uf_sigla = uf_map.get(st.session_state.estado_cnpj_selecionado, st.session_state.estado_cnpj_selecionado.upper()[:2])
        nome_arquivo_municipio = next((k for k, v in municipios_do_estado_map.items() if v == st.session_state.municipio_cnpj_selecionado), None)
        if nome_arquivo_municipio:
            caminho_arquivo_estab_final = f"{CAMINHO_PRINCIPAL_PROCESSADO_DEFAULT_PREFIXO}_{uf_sigla}_{nome_arquivo_municipio}.csv"
            if os.path.exists(caminho_arquivo_estab_final): st.sidebar.caption(f"Usará base: {os.path.basename(caminho_arquivo_estab_final)}")
            else: st.sidebar.warning(f"Arquivo CNPJ não encontrado: {os.path.basename(caminho_arquivo_estab_final)}"); caminho_arquivo_estab_final = None
        else: st.sidebar.warning("Não foi possível determinar o arquivo da base CNPJ."); caminho_arquivo_estab_final = None
else: st.sidebar.caption("Categorização genérica selecionada. Base CNPJ não será usada.")
st.sidebar.subheader("4. Ações")
col_btn1, col_btn2 = st.sidebar.columns(2)
processar_btn_clicked = col_btn1.button("🚀 Processar", type="primary", use_container_width=True, disabled=not uploaded_files or (usar_cat_especifica_bool and not caminho_arquivo_estab_final))
limpar_dados_btn_clicked = col_btn2.button("🧹 Limpar Dados", use_container_width=True)
st.sidebar.subheader("Mensagens do Processo")
log_placeholder = st.sidebar.empty()
with log_placeholder.container():
    for msg in reversed(st.session_state.get('log_messages', [])):
        st.caption(msg)
st.sidebar.subheader("5. Sessão")
dados_sessao_json_str = gerar_dados_sessao_para_salvar()
st.sidebar.download_button(label="💾 Baixar Progresso (.json)", data=dados_sessao_json_str, file_name=f"sessao_faturas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", mime="application/json", use_container_width=True, disabled=st.session_state.df_processado.empty, key="download_sessao_btn_v10")
arquivo_sessao_carregado = st.sidebar.file_uploader("📂 Carregar Progresso (.json):", type=["json"], key=f"file_uploader_sessao_key_{st.session_state.arquivo_sessao_uploader_key}_v10")
if arquivo_sessao_carregado is not None:
    conteudo_arquivo_sessao = arquivo_sessao_carregado.getvalue().decode("utf-8"); carregar_dados_sessao_do_arquivo(conteudo_arquivo_sessao)

if limpar_dados_btn_clicked:
    st.session_state.df_processado = pd.DataFrame()
    st.session_state.filtros_sidebar = {'periodos_ciclo_arquivo': ["Todos"], 'categorias_despesa': ["Todos"]}
    st.session_state.nomes_arquivos_faturas_ja_processados = set()
    st.session_state.edit_search_term = ""
    st.session_state.edit_category_filter = "Todas"
    st.session_state.edit_current_page = 1
    st.session_state.arquivo_sessao_uploader_key += 1
    st.session_state.log_messages = ["Dados e filtros do dashboard limpos."]
    st.session_state.categorias_base_memoria = carregar_categorias_base_do_json()
    st.session_state.ciclos_consulta_selecionados = []
    base_memoria = st.session_state.categorias_base_memoria if isinstance(st.session_state.categorias_base_memoria, dict) else {}; lista_cats = sorted(list(base_memoria.keys()))
    for cat_essencial in CATEGORIAS_ESSENCIAIS_PARA_EDICAO:
        if cat_essencial not in lista_cats: lista_cats.append(cat_essencial)
    st.session_state.categorias_editaveis = sorted(list(set(lista_cats)))
    st.rerun()

if processar_btn_clicked and uploaded_files:
    log_mensagem_app("Iniciando processamento...", "info")
    arquivos_para_processar_agora = []; novos_nomes_arquivos = set()
    if uploaded_files:
        for f_up in uploaded_files:
            novos_nomes_arquivos.add(f_up.name)
            if f_up.name not in st.session_state.nomes_arquivos_faturas_ja_processados: arquivos_para_processar_agora.append(f_up)
    df_novas_faturas = pd.DataFrame()
    if arquivos_para_processar_agora:
        log_mensagem_app(f"Processando {len(arquivos_para_processar_agora)} novo(s) arquivo(s)...", "info")
        df_novas_faturas = processar_faturas(arquivos_para_processar_agora, usar_cat_especifica_bool, caminho_arquivo_estab_final, log_placeholder)
    elif not st.session_state.df_processado.empty and novos_nomes_arquivos.issubset(st.session_state.nomes_arquivos_faturas_ja_processados):
        log_mensagem_app("Nenhum arquivo novo para processar. Exibindo dados atuais.", "info")
    elif st.session_state.df_processado.empty and not arquivos_para_processar_agora and uploaded_files:
        log_mensagem_app(f"Arquivos parecem já processados. Reprocessando todos {len(uploaded_files)}.", "warning")
        st.session_state.nomes_arquivos_faturas_ja_processados = set()
        df_novas_faturas = processar_faturas(uploaded_files, usar_cat_especifica_bool, caminho_arquivo_estab_final, log_placeholder)

    if not df_novas_faturas.empty:
        df_novas_faturas[COLUNA_DATA] = pd.to_datetime(df_novas_faturas[COLUNA_DATA], errors='coerce')
        df_novas_faturas.dropna(subset=[COLUNA_DATA], inplace=True)
        if COLUNA_FATURA_ORIGEM in df_novas_faturas.columns:
            df_novas_faturas['ciclo_fatura'] = df_novas_faturas[COLUNA_FATURA_ORIGEM].apply(extrair_ciclo_do_nome_arquivo)
        else:
            df_novas_faturas['ciclo_fatura'] = "Sem Origem Definida"
            log_mensagem_app(f"Coluna '{COLUNA_FATURA_ORIGEM}' não encontrada nos novos dados.", "warning")

        df_existente = st.session_state.df_processado.copy() if not st.session_state.df_processado.empty else pd.DataFrame()
        df_combinado = pd.concat([df_existente, df_novas_faturas], ignore_index=True)
        subset_duplicatas = [COLUNA_TITULO, COLUNA_DATA, COLUNA_VALOR, COLUNA_FATURA_ORIGEM]
        if all(col in df_combinado.columns for col in subset_duplicatas): # Ensure all columns exist before dropping
            df_combinado.drop_duplicates(subset=subset_duplicatas, keep='first', inplace=True)
        elif COLUNA_FATURA_ORIGEM not in df_combinado.columns and all(col in df_combinado.columns for col in [COLUNA_TITULO, COLUNA_DATA, COLUNA_VALOR]):
             df_combinado.drop_duplicates(subset=[COLUNA_TITULO, COLUNA_DATA, COLUNA_VALOR], keep='first', inplace=True)


        df_combinado.reset_index(drop=True, inplace=True)
        df_combinado[COLUNA_EDIT_ID] = df_combinado.index
        st.session_state.df_processado = df_combinado.copy()
        if arquivos_para_processar_agora:
             for f_proc in arquivos_para_processar_agora: st.session_state.nomes_arquivos_faturas_ja_processados.add(f_proc.name)
        st.rerun()
    elif uploaded_files and df_novas_faturas.empty and arquivos_para_processar_agora:
        log_mensagem_app("Processamento dos novos arquivos resultou em dados vazios.", "error")


if not st.session_state.df_processado.empty:

    df_dashboard_master = st.session_state.df_processado.copy()

    if COLUNA_DATA in df_dashboard_master.columns:
        df_dashboard_master[COLUNA_DATA] = pd.to_datetime(df_dashboard_master[COLUNA_DATA], errors='coerce')
        df_dashboard_master.dropna(subset=[COLUNA_DATA], inplace=True)
        if not df_dashboard_master.empty:
            if 'mes_ano' not in df_dashboard_master.columns or df_dashboard_master['mes_ano'].isnull().all():
                df_dashboard_master['mes_ano'] = df_dashboard_master[COLUNA_DATA].dt.to_period('M').astype(str)
            if 'ano' not in df_dashboard_master.columns: df_dashboard_master['ano'] = df_dashboard_master[COLUNA_DATA].dt.year
            if 'mes' not in df_dashboard_master.columns: df_dashboard_master['mes'] = df_dashboard_master[COLUNA_DATA].dt.month
            if 'dia_da_semana' not in df_dashboard_master.columns: df_dashboard_master['dia_da_semana'] = df_dashboard_master[COLUNA_DATA].dt.day_name()
            if 'dia_do_mes' not in df_dashboard_master.columns: df_dashboard_master['dia_do_mes'] = df_dashboard_master[COLUNA_DATA].dt.day

    if COLUNA_FATURA_ORIGEM in df_dashboard_master.columns:
        if 'ciclo_fatura' not in df_dashboard_master.columns or df_dashboard_master['ciclo_fatura'].isnull().all():
            df_dashboard_master['ciclo_fatura'] = df_dashboard_master[COLUNA_FATURA_ORIGEM].apply(extrair_ciclo_do_nome_arquivo)
    elif 'ciclo_fatura' not in df_dashboard_master.columns:
        df_dashboard_master['ciclo_fatura'] = "Sem Origem Definida"
    # Update session state only once after all potential modifications to df_dashboard_master
    # st.session_state.df_processado = df_dashboard_master.copy() # This was potentially problematic, moved to end of this block

    with st.expander("✏️ Revisar e Editar Categorias", expanded=False):
        col_edit_filt1, col_edit_filt2 = st.columns(2); st.session_state.edit_search_term = col_edit_filt1.text_input("Buscar Título (edição):", value=st.session_state.edit_search_term, key="search_edit_v15")
        current_unique_cats = sorted(df_dashboard_master[COLUNA_CATEGORIA].unique().tolist()); categorias_disponiveis_filtro_edicao = ["Todas"] + [cat for cat in current_unique_cats if pd.notna(cat)]
        if st.session_state.edit_category_filter not in categorias_disponiveis_filtro_edicao: st.session_state.edit_category_filter = "Todas"
        st.session_state.edit_category_filter = col_edit_filt2.selectbox("Filtrar Categoria (edição):", options=categorias_disponiveis_filtro_edicao, index=categorias_disponiveis_filtro_edicao.index(st.session_state.edit_category_filter), key="cat_filt_edit_v15")
        df_edit_display = df_dashboard_master.copy()
        if st.session_state.edit_search_term: df_edit_display = df_edit_display[df_edit_display[COLUNA_TITULO].str.contains(st.session_state.edit_search_term, case=False, na=False)]
        if st.session_state.edit_category_filter != "Todas": df_edit_display = df_edit_display[df_edit_display[COLUNA_CATEGORIA] == st.session_state.edit_category_filter]
        items_per_page_edit = st.slider("Itens p/ página (edição):", 5, 50, 10, key="items_edit_v15")
        if not df_edit_display.empty:
            total_pages_edit = max(1, (len(df_edit_display) - 1) // items_per_page_edit + 1)
            if st.session_state.edit_current_page > total_pages_edit: st.session_state.edit_current_page = total_pages_edit
            st.session_state.edit_current_page = st.number_input("Página (edição):", min_value=1, max_value=total_pages_edit, value=st.session_state.edit_current_page, step=1, key="page_edit_v15")
            start_idx_edit = (st.session_state.edit_current_page - 1) * items_per_page_edit; end_idx_edit = st.session_state.edit_current_page * items_per_page_edit
            df_page_edit = df_edit_display.iloc[start_idx_edit:end_idx_edit]
            for _, row_to_edit in df_page_edit.iterrows():
                edit_id = row_to_edit[COLUNA_EDIT_ID]; current_cat = row_to_edit[COLUNA_CATEGORIA]; titulo_original_transacao = row_to_edit[COLUNA_TITULO]
                cols_display_edit = st.columns([0.4, 0.15, 0.15, 0.3])
                data_formatada = pd.to_datetime(row_to_edit[COLUNA_DATA]).strftime('%d/%m/%y') if pd.notna(row_to_edit[COLUNA_DATA]) else "Data Inválida"
                cols_display_edit[0].markdown(f"**{data_formatada}** - {row_to_edit[COLUNA_TITULO]}"); cols_display_edit[1].markdown(f"R$ {row_to_edit[COLUNA_VALOR]:.2f}"); cols_display_edit[2].markdown(f"*Orig: {row_to_edit.get(COLUNA_FATURA_ORIGEM, 'N/A')}*")
                cat_options_edit = st.session_state.categorias_editaveis[:]; default_index_cat_edit = 0
                if pd.notna(current_cat) and current_cat not in cat_options_edit: cat_options_edit.append(current_cat); cat_options_edit.sort()
                if pd.notna(current_cat) and current_cat in cat_options_edit: default_index_cat_edit = cat_options_edit.index(current_cat)
                elif "Sem Categoria" in cat_options_edit: default_index_cat_edit = cat_options_edit.index("Sem Categoria")

                selectbox_key = f"sel_cat_edit_v14_{edit_id}"; new_cat_sel_widget = cols_display_edit[3].selectbox("Categoria:", cat_options_edit, index=default_index_cat_edit, key=selectbox_key, label_visibility="collapsed")
                categoria_final_escolhida = new_cat_sel_widget

                if categoria_final_escolhida != current_cat:
                    idx_to_update_global = st.session_state.df_processado[st.session_state.df_processado[COLUNA_EDIT_ID] == edit_id].index
                    if not idx_to_update_global.empty:
                        st.session_state.df_processado.loc[idx_to_update_global[0], COLUNA_CATEGORIA] = categoria_final_escolhida
                        # df_dashboard_master is a copy, so it needs update too if used before rerun
                        # Or rely on rerun to repopulate df_dashboard_master from st.session_state.df_processado
                        
                        titulo_norm_para_json = normalizar_texto(titulo_original_transacao)
                        if pd.notna(current_cat) and current_cat in st.session_state.categorias_base_memoria:
                            if titulo_norm_para_json in st.session_state.categorias_base_memoria[current_cat]:
                                st.session_state.categorias_base_memoria[current_cat].remove(titulo_norm_para_json)
                                if not st.session_state.categorias_base_memoria[current_cat] and current_cat not in CATEGORIAS_ESSENCIAIS_PARA_EDICAO: del st.session_state.categorias_base_memoria[current_cat];
                                if current_cat in st.session_state.categorias_editaveis and current_cat not in CATEGORIAS_ESSENCIAIS_PARA_EDICAO and current_cat not in st.session_state.df_processado[COLUNA_CATEGORIA].unique(): st.session_state.categorias_editaveis.remove(current_cat)
                        if categoria_final_escolhida not in st.session_state.categorias_base_memoria: st.session_state.categorias_base_memoria[categoria_final_escolhida] = []
                        if titulo_norm_para_json not in st.session_state.categorias_base_memoria[categoria_final_escolhida]: st.session_state.categorias_base_memoria[categoria_final_escolhida].append(titulo_norm_para_json)
                        if salvar_categorias_base_para_json(st.session_state.categorias_base_memoria): log_mensagem_app(f"Base atualizada: '{str(titulo_original_transacao)[:30]}...' -> '{categoria_final_escolhida}'.", "success")
                        else: log_mensagem_app(f"ERRO ao salvar base.", "error")
                        st.rerun() # This rerun will cause df_dashboard_master to be rebuilt from the updated st.session_state.df_processado
                st.markdown("---")
        else:
            st.info("Nenhum item corresponde aos filtros de edição atuais.")
    
    st.session_state.df_processado = df_dashboard_master.copy() # Update session state after potential modifications like date column additions

    # --- Filtros Principais do Dashboard ---
    df_dashboard_filtrado_base = df_dashboard_master.copy()
    st.sidebar.subheader("Filtros do Dashboard")
    coluna_periodo_selecionada = 'ciclo_fatura'
    label_periodo_selecionado = "Ciclo da Fatura"
    
    df_para_relatorios = df_dashboard_filtrado_base.copy()

    if coluna_periodo_selecionada not in df_dashboard_filtrado_base.columns or df_dashboard_filtrado_base[coluna_periodo_selecionada].isnull().all():
        st.sidebar.warning("Coluna 'ciclo_fatura' não disponível para filtro.")
    else:
        all_periodos_options = sorted(df_dashboard_filtrado_base[coluna_periodo_selecionada].dropna().unique(), reverse=True)
        all_periodos_for_multiselect = ["Todos"] + all_periodos_options
        
        # --- Refined default logic for periodos_ciclo_arquivo filter ---
        st.session_state.filtros_sidebar.setdefault('periodos_ciclo_arquivo', ["Todos"])
        current_selection_periodos = st.session_state.filtros_sidebar['periodos_ciclo_arquivo']
        # Validate current selection against available options
        valid_default_periodos_sidebar = [p for p in current_selection_periodos if p in all_periodos_for_multiselect]

        # If validation results in an empty list, but the original selection was not empty (i.e., it became invalid)
        # then reset to ["Todos"] if "Todos" is an option. Otherwise, respect the empty selection.
        if not valid_default_periodos_sidebar and current_selection_periodos: # Original selection was non-empty but became invalid
            if "Todos" in all_periodos_for_multiselect:
                valid_default_periodos_sidebar = ["Todos"]
            # else: it remains empty if "Todos" is somehow not an option (should not happen here)
        # If current_selection_periodos was already empty, valid_default_periodos_sidebar will also be empty, preserving the empty selection.

        selected_periodos = st.sidebar.multiselect(
            f"Ciclo(s) da Fatura (Arquivo):",
            all_periodos_for_multiselect,
            default=valid_default_periodos_sidebar,
            key="multi_periodo_ciclo_v2_sidebar_refined" # Changed key to ensure fresh state if needed
        )
        st.session_state.filtros_sidebar['periodos_ciclo_arquivo'] = selected_periodos
        # --- End refined logic ---

        if selected_periodos and "Todos" not in selected_periodos:
            df_para_relatorios = df_para_relatorios[df_para_relatorios[coluna_periodo_selecionada].isin(selected_periodos)]
        elif not selected_periodos and "Todos" not in selected_periodos : # Empty selection means filter out all
             df_para_relatorios = pd.DataFrame(columns=df_dashboard_filtrado_base.columns)
        # If ["Todos"] is selected or if selected_periodos is ["Todos"], no filtering by period is done on df_para_relatorios here.

    df_despesas_relatorio_pre_cat_filter = df_para_relatorios[
        ~df_para_relatorios[COLUNA_CATEGORIA].isin(CATEGORIAS_NAO_CONSUMO_GERAL) &
        (df_para_relatorios[COLUNA_VALOR] > 0)
    ].copy()

    current_unique_cats_despesa_options = sorted(df_despesas_relatorio_pre_cat_filter[COLUNA_CATEGORIA].astype(str).unique().tolist())
    all_cat_despesa_for_multiselect = ["Todos"] + [cat for cat in current_unique_cats_despesa_options if pd.notna(cat) and cat != 'nan']

    # --- Refined default logic for categorias_despesa filter ---
    st.session_state.filtros_sidebar.setdefault('categorias_despesa', ["Todos"])
    current_selection_categorias = st.session_state.filtros_sidebar['categorias_despesa']
    valid_default_cats_despesa_sidebar = [c for c in current_selection_categorias if c in all_cat_despesa_for_multiselect]

    if not valid_default_cats_despesa_sidebar and current_selection_categorias: # Original selection was non-empty but became invalid
        if "Todos" in all_cat_despesa_for_multiselect:
            valid_default_cats_despesa_sidebar = ["Todos"]
    
    selected_cats_despesa = st.sidebar.multiselect(
        "Categoria(s) Despesa Consumo:",
        all_cat_despesa_for_multiselect,
        default=valid_default_cats_despesa_sidebar,
        key="multi_cat_dash_v15_sidebar_refined" # Changed key
    )
    st.session_state.filtros_sidebar['categorias_despesa'] = selected_cats_despesa
    # --- End refined logic ---
    
    df_despesas_relatorio = df_despesas_relatorio_pre_cat_filter.copy() # Start with period-filtered data
    if selected_cats_despesa and "Todos" not in selected_cats_despesa:
        df_despesas_relatorio = df_despesas_relatorio[df_despesas_relatorio[COLUNA_CATEGORIA].isin(selected_cats_despesa)]
    elif not selected_cats_despesa and "Todos" not in selected_cats_despesa:
        df_despesas_relatorio = pd.DataFrame(columns=df_despesas_relatorio.columns)
    # If ["Todos"] is selected for categories, df_despesas_relatorio remains as df_despesas_relatorio_pre_cat_filter

    df_encargos_kpi = df_para_relatorios[df_para_relatorios[COLUNA_CATEGORIA].isin(CATEGORIAS_ENCARGOS_FINANCEIROS_NAO_CONSUMO) & ~df_para_relatorios[COLUNA_CATEGORIA].isin(CATEGORIAS_AJUSTE_SALDO_DEVEDOR) & (df_para_relatorios[COLUNA_VALOR] > 0)]

    st.header(f"Resumo Financeiro")
    total_gasto_kpi_val, media_diaria_kpi_val = 0.0, 0.0
    if not df_despesas_relatorio.empty:
        total_gasto_kpi_val = df_despesas_relatorio[COLUNA_VALOR].sum()
        num_dias_com_gastos = df_despesas_relatorio[COLUNA_DATA].dt.date.nunique()
        if num_dias_com_gastos > 0 :
            soma_diaria_df = df_despesas_relatorio.groupby(df_despesas_relatorio[COLUNA_DATA].dt.date)[COLUNA_VALOR].sum()
            media_diaria_kpi_val = soma_diaria_df.mean()

    total_encargos_kpi_val = df_encargos_kpi[COLUNA_VALOR].sum() if not df_encargos_kpi.empty else 0.0

    kpi_c1, kpi_c2, kpi_c3 = st.columns(3)
    kpi_c1.metric("Total Gasto (Consumo)", f"R$ {total_gasto_kpi_val:,.2f}")
    kpi_c2.metric("Média Gasto Diário (Consumo)", f"R$ {media_diaria_kpi_val:,.2f}")
    kpi_c3.metric("Total Encargos Financeiros", f"R$ {total_encargos_kpi_val:,.2f}", help=f"Juros, multas, IOF, etc. ({', '.join(CATEGORIAS_ENCARGOS_FINANCEIROS_NAO_CONSUMO)})")

    st.markdown("---")

    df_despesas_historico_plot_g1 = df_dashboard_master[
        ~df_dashboard_master[COLUNA_CATEGORIA].isin(CATEGORIAS_NAO_CONSUMO_GERAL) &
        (df_dashboard_master[COLUNA_VALOR] > 0) &
        pd.notna(df_dashboard_master['mes_ano'])
    ].copy()

    if not df_despesas_historico_plot_g1.empty:
        gastos_mensais_evolucao_g1 = df_despesas_historico_plot_g1.groupby('mes_ano')[COLUNA_VALOR].sum().reset_index().sort_values('mes_ano')
        if not gastos_mensais_evolucao_g1.empty:
            fig_evolucao_g1 = px.line(gastos_mensais_evolucao_g1, x='mes_ano', y=COLUNA_VALOR, title="Evolução dos Gastos de Consumo Mensais", markers=True, labels={COLUNA_VALOR: "Gasto Consumo (R$)", 'mes_ano': "Mês/Ano da Transação"})
            st.plotly_chart(fig_evolucao_g1, use_container_width=True)

    plot_col_dist_mensal1, plot_col_dist_mensal2 = st.columns(2)

    if not df_despesas_historico_plot_g1.empty and 'mes_ano' in df_despesas_historico_plot_g1.columns and COLUNA_DATA in df_despesas_historico_plot_g1.columns:
        df_freq_calc = df_despesas_historico_plot_g1.copy()
        if not df_freq_calc.empty:
            dias_com_gastos_por_mes = df_freq_calc.groupby('mes_ano')[COLUNA_DATA].nunique().reset_index()
            dias_com_gastos_por_mes.rename(columns={COLUNA_DATA: 'dias_com_transacao'}, inplace=True)
            if not dias_com_gastos_por_mes.empty:
                dias_com_gastos_por_mes['temp_date_for_daysinmonth'] = pd.to_datetime(dias_com_gastos_por_mes['mes_ano'].astype(str) + '-01', errors='coerce')
                dias_com_gastos_por_mes.dropna(subset=['temp_date_for_daysinmonth'], inplace=True)
                if not dias_com_gastos_por_mes.empty:
                    dias_com_gastos_por_mes['total_dias_no_mes'] = dias_com_gastos_por_mes['temp_date_for_daysinmonth'].dt.daysinmonth
                    dias_com_gastos_por_mes['frequencia_uso_percent'] = np.where(
                        dias_com_gastos_por_mes['total_dias_no_mes'] > 0,
                        (dias_com_gastos_por_mes['dias_com_transacao'] / dias_com_gastos_por_mes['total_dias_no_mes']) * 100, 0
                    )
                    dias_com_gastos_por_mes.sort_values('mes_ano', inplace=True)
                    if not dias_com_gastos_por_mes.empty and 'frequencia_uso_percent' in dias_com_gastos_por_mes.columns:
                        fig_freq_uso = px.bar(dias_com_gastos_por_mes, x='mes_ano', y='frequencia_uso_percent',
                                               title="Frequência de Uso Mensal (Consumo)",
                                               labels={'frequencia_uso_percent': "Frequência de Uso (%)", 'mes_ano': "Mês/Ano"},
                                               text_auto=".1f")
                        fig_freq_uso.update_yaxes(ticksuffix="%")
                        plot_col_dist_mensal1.plotly_chart(fig_freq_uso, use_container_width=True)

    df_encargos_historico_detalhes = df_dashboard_master[
        df_dashboard_master[COLUNA_CATEGORIA].isin(CATEGORIAS_ENCARGOS_FINANCEIROS_NAO_CONSUMO) &
        ~df_dashboard_master[COLUNA_CATEGORIA].isin(CATEGORIAS_AJUSTE_SALDO_DEVEDOR) &
        (df_dashboard_master[COLUNA_VALOR] > 0) &
        pd.notna(df_dashboard_master['mes_ano'])
    ].copy()
    if not df_encargos_historico_detalhes.empty and 'mes_ano' in df_encargos_historico_detalhes.columns:
        encargos_mensais_plot_agg = df_encargos_historico_detalhes.groupby('mes_ano')[COLUNA_VALOR].sum().reset_index()
        if not encargos_mensais_plot_agg.empty:
            encargos_mensais_plot_agg.sort_values('mes_ano', inplace=True)
            total_encargos_historico = encargos_mensais_plot_agg[COLUNA_VALOR].sum()
            fig_custos_fin_mensais = px.bar(encargos_mensais_plot_agg, x='mes_ano', y=COLUNA_VALOR,
                                             title=f"Custos Financeiros Mensais (Total: R$ {total_encargos_historico:,.2f})",
                                             labels={COLUNA_VALOR: "Total Encargos (R$)", 'mes_ano': "Mês/Ano"},
                                             text_auto=".2f")
            plot_col_dist_mensal2.plotly_chart(fig_custos_fin_mensais, use_container_width=True)

            with plot_col_dist_mensal2.expander("Ver Detalhes dos Custos Financeiros Mensais"):
                if not df_encargos_historico_detalhes.empty:
                    df_tabela_detalhes_encargos = df_encargos_historico_detalhes[
                        [COLUNA_DATA, 'mes_ano', COLUNA_TITULO, COLUNA_CATEGORIA, COLUNA_VALOR]
                    ].copy()
                    df_tabela_detalhes_encargos.sort_values(by=['mes_ano', COLUNA_DATA], inplace=True)
                    df_tabela_detalhes_encargos['Data Formatada'] = df_tabela_detalhes_encargos[COLUNA_DATA].dt.strftime('%d/%m/%Y')
                    df_tabela_detalhes_encargos_display = df_tabela_detalhes_encargos[
                        ['Data Formatada', 'mes_ano', COLUNA_TITULO, COLUNA_CATEGORIA, COLUNA_VALOR]
                    ].rename(columns={
                        'Data Formatada': 'Data Transação', 'mes_ano': 'Mês/Ano (Referência)',
                        COLUNA_TITULO: 'Descrição', COLUNA_CATEGORIA: 'Categoria', COLUNA_VALOR: 'Valor (R$)'
                    })
                    st.dataframe(
                        df_tabela_detalhes_encargos_display.style.format({'Valor (R$)': "R$ {:,.2f}"}),
                        use_container_width=True, hide_index=True
                    )

    if not df_despesas_relatorio.empty:
        top_n_cat_g2 = st.slider("Top N Categorias de Consumo (Período Filtrado):", 3, 20, 10, key="slider_top_n_cat_g2_v6")
        gastos_por_categoria_plot_g2 = df_despesas_relatorio.groupby(COLUNA_CATEGORIA)[COLUNA_VALOR].sum().reset_index().sort_values(by=COLUNA_VALOR, ascending=False).head(top_n_cat_g2)
        if not gastos_por_categoria_plot_g2.empty:
            fig_dist_categoria_plot_g2 = px.bar(gastos_por_categoria_plot_g2, x=COLUNA_CATEGORIA, y=COLUNA_VALOR, title=f"Top {top_n_cat_g2} Gastos de Consumo por Categoria", text_auto=".2f", labels={COLUNA_VALOR: "Gasto Consumo (R$)"})
            fig_dist_categoria_plot_g2.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig_dist_categoria_plot_g2, use_container_width=True)

    if not df_despesas_relatorio.empty:
        plot_col1_g3, plot_col2_g3 = st.columns(2)
        mapa_dias_pt_g3 = {"Monday":"Seg", "Tuesday":"Ter", "Wednesday":"Qua", "Thursday":"Qui", "Friday":"Sex", "Saturday":"Sáb", "Sunday":"Dom"}
        ordem_dias_plot_g3 = list(mapa_dias_pt_g3.values())
        if 'dia_da_semana' in df_despesas_relatorio.columns:
            df_dia_semana_plot_g3 = df_despesas_relatorio.copy()
            df_dia_semana_plot_g3['dia_da_semana_pt'] = df_dia_semana_plot_g3['dia_da_semana'].map(mapa_dias_pt_g3)
            df_dia_semana_plot_g3 = df_dia_semana_plot_g3.groupby('dia_da_semana_pt')[COLUNA_VALOR].sum().reindex(ordem_dias_plot_g3).reset_index().dropna(subset=[COLUNA_VALOR])
            if not df_dia_semana_plot_g3.empty:
                fig_dia_semana_plot_g3 = px.bar(df_dia_semana_plot_g3, x='dia_da_semana_pt', y=COLUNA_VALOR, title=f"Gastos de Consumo por Dia da Semana", labels={COLUNA_VALOR: "Gasto Consumo (R$)", 'dia_da_semana_pt':"Dia"})
                plot_col1_g3.plotly_chart(fig_dia_semana_plot_g3, use_container_width=True)

        if 'dia_do_mes' in df_despesas_relatorio.columns:
            df_dia_mes_plot_g3 = df_despesas_relatorio.groupby('dia_do_mes')[COLUNA_VALOR].sum().reset_index().dropna(subset=[COLUNA_VALOR])
            if not df_dia_mes_plot_g3.empty:
                fig_dia_mes_plot_g3 = px.bar(df_dia_mes_plot_g3, x='dia_do_mes', y=COLUNA_VALOR, title=f"Gastos de Consumo por Dia do Mês", labels={COLUNA_VALOR: "Gasto Consumo (R$)", 'dia_do_mes':"Dia do Mês"}, text_auto=".2f")
                fig_dia_mes_plot_g3.update_layout(xaxis=dict(type='category'))
                plot_col2_g3.plotly_chart(fig_dia_mes_plot_g3, use_container_width=True)

    if not df_despesas_relatorio.empty:
        top_n_estab_g4 = st.slider("Top N Estabelecimentos:", 5, 50, 15, key="slider_top_estab_g4_v6")
        gastos_estab_plot_g4 = df_despesas_relatorio.groupby(COLUNA_TITULO)[COLUNA_VALOR].sum().reset_index().sort_values(by=COLUNA_VALOR, ascending=False).head(top_n_estab_g4)
        if not gastos_estab_plot_g4.empty:
            fig_estab_plot_g4 = px.bar(gastos_estab_plot_g4, x=COLUNA_TITULO, y=COLUNA_VALOR, title=f"Top {top_n_estab_g4} Estabelecimentos", text_auto=".2f", labels={COLUNA_VALOR: "Gasto Consumo (R$)"})
            fig_estab_plot_g4.update_layout(xaxis_tickangle=-60, height=500)
            st.plotly_chart(fig_estab_plot_g4, use_container_width=True)

    if not df_despesas_historico_plot_g1.empty:
        top_n_media_cat_g5 = st.slider("Top N Categorias por Média Mensal:", 3, 20, 10, key="slider_top_n_media_cat_g5_v6")
        media_cat_mes_hist_plot_g5 = df_despesas_historico_plot_g1.groupby(['mes_ano', COLUNA_CATEGORIA])[COLUNA_VALOR].sum().unstack(fill_value=0).mean(axis=0).reset_index()
        media_cat_mes_hist_plot_g5.columns = [COLUNA_CATEGORIA, 'media_mensal_gasto']
        media_cat_mes_hist_plot_g5 = media_cat_mes_hist_plot_g5.sort_values(by='media_mensal_gasto', ascending=False).head(top_n_media_cat_g5)
        if not media_cat_mes_hist_plot_g5.empty:
            fig_media_cat_plot_g5 = px.bar(media_cat_mes_hist_plot_g5, x=COLUNA_CATEGORIA, y='media_mensal_gasto', title=f"Top {top_n_media_cat_g5} Categorias por Média Mensal de Gasto", text_auto=".2f", labels={'media_mensal_gasto':"Média Consumo (R$)"})
            fig_media_cat_plot_g5.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig_media_cat_plot_g5, use_container_width=True)

    st.markdown("---")
    st.header("Consulta Detalhada por Fatura")

    if 'ciclo_fatura' in df_dashboard_master.columns and df_dashboard_master['ciclo_fatura'].notna().any():
        lista_ciclos_disponiveis_consulta = sorted(df_dashboard_master['ciclo_fatura'].dropna().unique(), reverse=True)

        # --- Refined default logic for consulta_ciclo_multiselect ---
        st.session_state.setdefault('ciclos_consulta_selecionados', []) # Ensure it exists, default to empty list
        current_selection_ciclos_consulta = st.session_state.get('ciclos_consulta_selecionados', [])
        # Validate against available options. An empty list is a valid default here.
        valid_default_ciclos_consulta = [c for c in current_selection_ciclos_consulta if c in lista_ciclos_disponiveis_consulta]
        # No reset to "Todos" logic here, as an empty selection is perfectly fine.

        ciclos_selecionados_agora = st.multiselect(
            "Selecione o(s) Ciclo(s) da Fatura para ver os detalhes:",
            options=lista_ciclos_disponiveis_consulta,
            default=valid_default_ciclos_consulta, # This will be empty if previous selection is invalid or was empty
            key="consulta_ciclo_multiselect_v2_refined" # Changed key
        )
        st.session_state.ciclos_consulta_selecionados = ciclos_selecionados_agora
        # --- End refined logic ---

        if ciclos_selecionados_agora:
            df_consulta_fatura = df_dashboard_master[
                df_dashboard_master['ciclo_fatura'].isin(ciclos_selecionados_agora)
            ].copy()

            if not df_consulta_fatura.empty:
                colunas_exibir = {
                    COLUNA_DATA: 'Data', COLUNA_TITULO: 'Descrição',
                    COLUNA_CATEGORIA: 'Categoria', COLUNA_VALOR: 'Valor (R$)',
                    COLUNA_PARCELA_ATUAL: 'Parc. Atual', COLUNA_TOTAL_PARCELAS: 'Parc. Total',
                    'ciclo_fatura': 'Ciclo Fatura'
                }
                df_consulta_exibir = df_consulta_fatura[[key for key in colunas_exibir if key in df_consulta_fatura.columns]].rename(columns=colunas_exibir)

                if 'Data' in df_consulta_exibir.columns: # Ensure 'Data' column exists before formatting
                    df_consulta_exibir['Data'] = pd.to_datetime(df_consulta_exibir['Data']).dt.strftime('%d/%m/%Y')
                
                format_dict = {'Valor (R$)': "R$ {:,.2f}"}
                
                # Ensure 'Ciclo Fatura' and 'Data' exist before sorting
                sort_by_cols = []
                if 'Ciclo Fatura' in df_consulta_exibir.columns: sort_by_cols.append('Ciclo Fatura')
                if 'Data' in df_consulta_exibir.columns: sort_by_cols.append('Data')
                
                if sort_by_cols:
                    df_consulta_exibir.sort_values(by=sort_by_cols, ascending=[True, True], inplace=True)


                st.dataframe(
                    df_consulta_exibir.style.format(format_dict, na_rep='-'), # Added na_rep
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("Nenhum dado encontrado para os ciclos selecionados na consulta detalhada.")
        else:
            st.info("Selecione um ou mais ciclos na lista acima para ver os detalhes das transações.")

    else:
        st.info("Não há dados de ciclos de fatura disponíveis para consulta.")

    st.markdown("---"); st.header("🤝 Contribua para Melhorar a Categorização"); st.markdown("""A categorização automática pode não ser perfeita para todos os estabelecimentos. Suas edições manuais são salvas localmente no arquivo `Categorias.json` e ajudam a refinar o sistema para você.
    Se desejar, você pode compartilhar seu arquivo de categorias para ajudar a aprimorar a base de conhecimento geral do categorizador para todos os usuários!""")
    if st.button("Quero Contribuir com Minhas Categorizações!", key="btn_contribuir_v6"):
        categorias_base_para_contribuir_str = json.dumps(st.session_state.categorias_base_memoria, indent=4, ensure_ascii=False)
        st.download_button(label="1. Baixar meu Arquivo de Categorias (.json)", data=categorias_base_para_contribuir_str, file_name=f"minhas_categorias_base_{datetime.now().strftime('%Y%m%d')}.json", mime="application/json", key="download_contrib_categorias_v6")
        st.markdown("""2. Após baixar, envie para: **jcaxavier2@gmail.com** com o assunto "Contribuição - Categorias Dashboard Faturas".
        Sua contribuição é anônima em relação aos seus dados de fatura, pois apenas o mapeamento de NOMES DE ESTABELECIMENTOS para CATEGORIAS é compartilhado (armazenado no `Categorias.json`). Nenhuma informação pessoal ou valor de transação é incluído neste arquivo.""")
        mailto_link = f"mailto:jcaxavier2@gmail.com?subject=Contribuição%20-%20Categorias%20Dashboard%20Faturas&body=Olá,%0A%0ASegue%20meu%20arquivo%20de%20categorias%20(Categorias.json)%20em%20anexo.%0A%0ASe%20possível,%20informe%20o%20contexto%20de%20uso%20(ex:%20uso%20pessoal,%20teste,%20região%20predominante%20das%20compras%20se%20relevante%20para%20estabelecimentos%20locais).%0A%0AObrigado!"
        st.markdown(f"<a href='{mailto_link}'>Ou clique aqui para abrir seu e-mail e anexar o arquivo</a>", unsafe_allow_html=True)

else:
    if not uploaded_files:
        if 'log_messages' not in st.session_state or st.session_state.log_messages == ["Aqui aparecerão as mensagens de informação do processo."]:
            st.info("⬆️ FAÇA O UPLOAD DAS FATURAS EM CSV na barra lateral.")
    elif uploaded_files:
        st.info("📂 Arquivos selecionados. Clique em '🚀 Processar' na barra lateral para visualizar os dados.")