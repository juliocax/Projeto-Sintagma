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
import io

from categorizador import (
    processar_faturas,
    carregar_categorias_base_do_json,
    salvar_categorias_base_para_json,
    CAMINHO_CATEGORIAS_BASE_JSON,
    COLUNA_DATA, COLUNA_TITULO, COLUNA_VALOR, COLUNA_CATEGORIA, COLUNA_ID,
    COLUNA_PARCELA_ATUAL, COLUNA_TOTAL_PARCELAS, COLUNA_FATURA_ORIGEM,
    COLUNA_EDIT_ID, CAMINHO_PRINCIPAL_PROCESSADO_DEFAULT_PREFIXO,
    normalizar_texto
)

st.set_page_config(layout="wide", page_title="Análise de Faturas Pessoal")

NOME_ARQUIVO_IMAGEM = "Logo0.png"
MAX_LOG_MESSAGES = 20

CATEGORIAS_CREDITO_AJUSTE = [
    'Pagamento de Fatura', 'Estorno', 'Ajustes Financeiros Nubank',
    'Ajuste Parcelamento Fatura', 'Encerramento de dívida', 'Crédito Diversos',
    'Estorno de juros da dívida encerrada'
]
CATEGORIAS_ENCARGOS_FINANCEIROS = [
    'Juros de dívida encerrada', 'IOF de atraso',
    'Multa de atraso', 'Juros e Taxas Diversas', 'Taxa',
    'Juros de atraso'
]
CATEGORIA_ENCARGOS_PARCELAMENTO_FATURA = "Encargos de Parcelamento Fatura"
CATEGORIAS_AJUSTE_SALDO_DEVEDOR = [
    'Saldo em atraso',
    'Crédito de atraso'
]

CATEGORIAS_FINANCEIRAS_FIXAS = sorted(list(set(
    CATEGORIAS_CREDITO_AJUSTE +
    CATEGORIAS_ENCARGOS_FINANCEIROS +
    [CATEGORIA_ENCARGOS_PARCELAMENTO_FATURA] +
    CATEGORIAS_AJUSTE_SALDO_DEVEDOR +
    ["Taxas"]
)))

CATEGORIAS_SISTEMA_ERRO_SEM_CATEGORIA = [
    "Sem Categoria/Pix Credito"
]


CATEGORIAS_ESSENCIAIS_PARA_DROPDOWNS = sorted(list(set(
    CATEGORIAS_FINANCEIRAS_FIXAS +
    CATEGORIAS_SISTEMA_ERRO_SEM_CATEGORIA
)))


def extrair_ciclo_do_nome_arquivo(nome_arquivo: str) -> str:
    if not isinstance(nome_arquivo, str):
        return "Sem Ciclo Definido"
    match = re.search(r'(\d{4}-\d{2})', nome_arquivo)
    if match:
        return match.group(1)
    log_mensagem_app(f"Não foi possível extrair o ciclo YYYY-MM do nome: {nome_arquivo}", "warning")
    return "Sem Ciclo Definido"

def log_mensagem_app(mensagem: str, tipo: str = 'info'):
    if 'log_messages' not in st.session_state or st.session_state.log_messages == ["Aqui aparecerão as mensagens de informação do processo."]:
        st.session_state.log_messages = []
    
    prefixo_emoji = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌"}
    st.session_state.log_messages.append(f"{prefixo_emoji.get(tipo, '')} {mensagem}")
    
    if len(st.session_state.log_messages) > MAX_LOG_MESSAGES:
        st.session_state.log_messages = st.session_state.log_messages[-MAX_LOG_MESSAGES:]

def _atualizar_lista_categorias_editaveis():
    base_memoria = st.session_state.get('categorias_base_memoria', {})
    if not isinstance(base_memoria, dict):
        log_mensagem_app("categorias_base_memoria não era um dicionário. Reicializando.", "warning")
        base_memoria = carregar_categorias_base_do_json() 
        if not isinstance(base_memoria, dict):
             base_memoria = {}
        st.session_state.categorias_base_memoria = base_memoria

    lista_cats_memoria = list(base_memoria.keys())
    
    st.session_state.categorias_editaveis = sorted(list(set(lista_cats_memoria + CATEGORIAS_ESSENCIAIS_PARA_DROPDOWNS)))


def inicializar_session_state():
    defaults = {
        'df_processado': pd.DataFrame(),
        'tipo_categorizacao_selecionada': "Genérica (Base Editável)",
        'estado_cnpj_selecionado': "Paraíba",
        'municipio_cnpj_selecionado': "João Pessoa",
        'filtros_sidebar': {'periodos_ciclo_arquivo': ["Todos"], 'categorias_despesa': ["Todos"]},
        'nomes_arquivos_faturas_ja_processados': set(),
        'arquivo_sessao_uploader_key': 0,
        'log_messages': ["Aqui aparecerão as mensagens de informação do processo."],
        'edit_search_term': "",
        'edit_category_filter': "Todas",
        'edit_current_page': 1,
        'categorias_base_memoria': carregar_categorias_base_do_json(),
        'ciclos_consulta_selecionados': []
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)

    st.session_state.filtros_sidebar.setdefault('periodos_ciclo_arquivo', ["Todos"])
    st.session_state.filtros_sidebar.setdefault('categorias_despesa', ["Todos"])
    
    _atualizar_lista_categorias_editaveis() 

def gerar_dados_sessao_para_salvar() -> str:
    df_para_salvar = st.session_state.df_processado.copy()
    
    cols_derivadas = ['ciclo_fatura', 'mes_ano', 'ano', 'mes', 'dia_da_semana', 'dia_do_mes']
    cols_to_drop = [col for col in cols_derivadas if col in df_para_salvar.columns]
    if cols_to_drop:
        df_para_salvar = df_para_salvar.drop(columns=cols_to_drop)
        
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

def carregar_dados_sessao_do_arquivo(uploaded_file_content: str):
    try:
        estado_carregado = json.loads(uploaded_file_content)
        df_json = estado_carregado.get('df_processado_json')
        if df_json:
            st.session_state.df_processado = pd.read_json(io.StringIO(df_json), orient='split', convert_dates=[COLUNA_DATA])
            if not st.session_state.df_processado.empty:
                if COLUNA_DATA in st.session_state.df_processado.columns:
                    st.session_state.df_processado[COLUNA_DATA] = pd.to_datetime(st.session_state.df_processado[COLUNA_DATA], errors='coerce')
                if COLUNA_EDIT_ID not in st.session_state.df_processado.columns:
                    st.session_state.df_processado.reset_index(drop=True, inplace=True)
                    st.session_state.df_processado[COLUNA_EDIT_ID] = st.session_state.df_processado.index
        else:
            st.session_state.df_processado = pd.DataFrame()

        st.session_state.tipo_categorizacao_selecionada = estado_carregado.get('tipo_categorizacao_selecionada', "Genérica (Base Editável)")
        st.session_state.estado_cnpj_selecionado = estado_carregado.get('estado_cnpj_selecionado', "Paraíba")
        st.session_state.municipio_cnpj_selecionado = estado_carregado.get('municipio_cnpj_selecionado', "João Pessoa")

        filtros_carregados = estado_carregado.get('filtros_sidebar', {})
        st.session_state.filtros_sidebar = {
            'periodos_ciclo_arquivo': filtros_carregados.get('periodos_ciclo_arquivo', ["Todos"]),
            'categorias_despesa': filtros_carregados.get('categorias_despesa', ["Todos"])
        }
    
        st.session_state.nomes_arquivos_faturas_ja_processados = set(estado_carregado.get('nomes_arquivos_faturas_ja_processados', []))
        st.session_state.edit_search_term = estado_carregado.get('edit_search_term', "")
        st.session_state.edit_category_filter = estado_carregado.get('edit_category_filter', "Todas")
        st.session_state.edit_current_page = estado_carregado.get('edit_current_page', 1)
        st.session_state.ciclos_consulta_selecionados = estado_carregado.get('ciclos_consulta_selecionados', [])
    
        categorias_base_salvas = estado_carregado.get('categorias_base_memoria_json')
        if categorias_base_salvas and isinstance(categorias_base_salvas, dict):
            st.session_state.categorias_base_memoria = categorias_base_salvas
        else:
            st.session_state.categorias_base_memoria = carregar_categorias_base_do_json()
    
        _atualizar_lista_categorias_editaveis() 
    
        st.sidebar.success("Progresso carregado!")
        log_mensagem_app(f"Sessão carregada (salva em {estado_carregado.get('timestamp_salvo', 'data desconhecida')}).", "success")
        st.session_state.arquivo_sessao_uploader_key += 1 
        st.rerun()
    except Exception as e:
        st.sidebar.error(f"Erro ao carregar sessão: {e}")
        log_mensagem_app(f"Falha ao carregar sessão: {e}", "error")

def preparar_dataframe_dashboard(df: pd.DataFrame) -> pd.DataFrame:
    df_out = df.copy()
    if not df_out.empty and COLUNA_DATA in df_out.columns:
        df_out[COLUNA_DATA] = pd.to_datetime(df_out[COLUNA_DATA], errors='coerce')
        df_out.dropna(subset=[COLUNA_DATA], inplace=True)

        if not df_out.empty:
            date_col_series = df_out[COLUNA_DATA].dt
            
            df_out['mes_ano'] = date_col_series.to_period('M').astype(str)
            df_out['ano'] = date_col_series.year
            df_out['mes'] = date_col_series.month
            df_out['dia_da_semana'] = date_col_series.day_name()
            df_out['dia_do_mes'] = date_col_series.day

    if COLUNA_FATURA_ORIGEM in df_out.columns:
        df_out['ciclo_fatura'] = df_out[COLUNA_FATURA_ORIGEM].apply(extrair_ciclo_do_nome_arquivo)
    elif 'ciclo_fatura' not in df_out.columns: 
        df_out['ciclo_fatura'] = "Sem Origem Definida" 
        
    return df_out

inicializar_session_state()

try:
    col1_header, col2_header = st.columns([2, 2]) 
    with col1_header:
        st.image(NOME_ARQUIVO_IMAGEM, use_container_width=True) 
    with col2_header:
        st.title("Syn(tagmᵃ) Visualizador de uso do Cartão de Crédito")
except FileNotFoundError:
    st.error(f"Erro: A imagem '{NOME_ARQUIVO_IMAGEM}' não foi encontrada. Verifique o caminho e o nome do arquivo.")
except Exception as e:
    st.error(f"Ocorreu um erro ao carregar a imagem: {e}")

st.markdown("Este painel interativo permite analisar seus gastos de cartão de crédito, identificar padrões e gerenciar suas finanças de forma mais eficaz.")
st.markdown("---")


st.sidebar.header("⚙️ Controles do Dashboard")
st.sidebar.subheader("1. Arquivos de Fatura")
uploaded_files = st.sidebar.file_uploader(
    "Selecione CSVs de fatura:",
    type=["csv"],
    accept_multiple_files=True,
    key="file_uploader_faturas_v16"
)

st.sidebar.subheader("2. Tipo de Categorização")
tipo_cat_selecionada_key = "radio_tipo_cat_v16" 
st.session_state.tipo_categorizacao_selecionada = st.sidebar.radio(
    "Método:",
    ["Genérica (Base Editável)", "Específica (Base Editável + CNPJ Gov)"],
    index=0 if st.session_state.tipo_categorizacao_selecionada.startswith("Genérica") else 1,
    key=tipo_cat_selecionada_key
)
usar_cat_especifica_bool = st.session_state.tipo_categorizacao_selecionada.startswith("Específica")
caminho_arquivo_estab_final = None 

if usar_cat_especifica_bool:
    st.sidebar.subheader("3. Base de Dados CNPJ")
    opcoes_locais_cnpj = {
        "Paraíba": {"Joao_Pessoa": "João Pessoa"}
    }
    lista_estados_disponiveis = list(opcoes_locais_cnpj.keys())
    
    if st.session_state.estado_cnpj_selecionado not in lista_estados_disponiveis and lista_estados_disponiveis:
        st.session_state.estado_cnpj_selecionado = lista_estados_disponiveis[0]
        
    st.session_state.estado_cnpj_selecionado = st.sidebar.selectbox(
        "Estado:",
        lista_estados_disponiveis,
        index=lista_estados_disponiveis.index(st.session_state.estado_cnpj_selecionado) if st.session_state.estado_cnpj_selecionado in lista_estados_disponiveis else 0,
        key="select_estado_cnpj_v16"
    )
    
    municipios_do_estado_map = opcoes_locais_cnpj.get(st.session_state.estado_cnpj_selecionado, {})
    lista_municipios_display = list(municipios_do_estado_map.values()) 

    idx_municipio_selecionado = 0
    municipio_selecionado_display = st.session_state.municipio_cnpj_selecionado 
    if municipio_selecionado_display in lista_municipios_display:
        idx_municipio_selecionado = lista_municipios_display.index(municipio_selecionado_display)
    elif lista_municipios_display: 
        municipio_selecionado_display = lista_municipios_display[0] 
        
    st.session_state.municipio_cnpj_selecionado = st.sidebar.selectbox(
        "Município:",
        lista_municipios_display,
        index=idx_municipio_selecionado,
        key="select_municipio_cnpj_v16",
        disabled=not bool(lista_municipios_display) 
    )
    
    if st.session_state.estado_cnpj_selecionado and st.session_state.municipio_cnpj_selecionado:
        uf_map = {"Paraíba": "PB", "Sao_Paulo": "SP"} 
        uf_sigla = uf_map.get(st.session_state.estado_cnpj_selecionado, st.session_state.estado_cnpj_selecionado.upper()[:2])
        
        nome_arquivo_municipio_key = next((k for k, v in municipios_do_estado_map.items() if v == st.session_state.municipio_cnpj_selecionado), None)
        
        if nome_arquivo_municipio_key:
            caminho_arquivo_estab_final = f"{CAMINHO_PRINCIPAL_PROCESSADO_DEFAULT_PREFIXO}{uf_sigla}{nome_arquivo_municipio_key}.csv"
            if os.path.exists(caminho_arquivo_estab_final):
                st.sidebar.caption(f"Usará base: {os.path.basename(caminho_arquivo_estab_final)}")
            else:
                st.sidebar.warning(f"Arquivo CNPJ não encontrado: {os.path.basename(caminho_arquivo_estab_final)}")
                caminho_arquivo_estab_final = None 
        else:
            st.sidebar.warning("Não foi possível determinar o arquivo da base CNPJ.")
            caminho_arquivo_estab_final = None
else:
    st.sidebar.caption("Categorização genérica selecionada. Base CNPJ não será usada.")

st.sidebar.subheader("4. Ações")
col_btn1, col_btn2 = st.sidebar.columns(2)
processar_btn_clicked = col_btn1.button(
    "🚀 Processar",
    type="primary",
    use_container_width=True,
    disabled=not uploaded_files or (usar_cat_especifica_bool and not caminho_arquivo_estab_final)
)
limpar_dados_btn_clicked = col_btn2.button("🧹 Limpar Dados", use_container_width=True)

st.sidebar.subheader("Mensagens do Processo")
log_placeholder = st.sidebar.empty()
with log_placeholder.container():
    for msg in reversed(st.session_state.get('log_messages', [])): 
        st.caption(msg)

st.sidebar.subheader("5. Sessão")
dados_sessao_json_str = gerar_dados_sessao_para_salvar()
st.sidebar.download_button(
    label="💾 Baixar Progresso (.json)",
    data=dados_sessao_json_str,
    file_name=f"sessao_faturas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
    mime="application/json",
    use_container_width=True,
    disabled=st.session_state.df_processado.empty,
    key="download_sessao_btn_v11" 
)
arquivo_sessao_carregado = st.sidebar.file_uploader(
    "📂 Carregar Progresso (.json):",
    type=["json"],
    key=f"file_uploader_sessao_key_{st.session_state.arquivo_sessao_uploader_key}_v11" 
)

if arquivo_sessao_carregado is not None:
    conteudo_arquivo_sessao = arquivo_sessao_carregado.getvalue().decode("utf-8")
    carregar_dados_sessao_do_arquivo(conteudo_arquivo_sessao)

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
    _atualizar_lista_categorias_editaveis()
    st.rerun()

if processar_btn_clicked and uploaded_files:
    log_mensagem_app("Iniciando processamento...", "info")
    
    novos_nomes_arquivos = {f_up.name for f_up in uploaded_files}
    arquivos_para_processar_agora = [
        f_up for f_up in uploaded_files 
        if f_up.name not in st.session_state.nomes_arquivos_faturas_ja_processados
    ]

    df_novas_faturas = pd.DataFrame()
    if arquivos_para_processar_agora:
        log_mensagem_app(f"Processando {len(arquivos_para_processar_agora)} novo(s) arquivo(s)...", "info")
        df_novas_faturas = processar_faturas(
            arquivos_para_processar_agora,
            usar_cat_especifica_bool,
            caminho_arquivo_estab_final,
            log_placeholder
        )

    elif not st.session_state.df_processado.empty and novos_nomes_arquivos.issubset(st.session_state.nomes_arquivos_faturas_ja_processados):
        log_mensagem_app("Todos os arquivos já processados anteriormente. Recategorizando com configurações atuais...", "info")
        
        st.session_state.nomes_arquivos_faturas_ja_processados = set() 
        df_novas_faturas = processar_faturas(
            uploaded_files, 
            usar_cat_especifica_bool,
            caminho_arquivo_estab_final,
            log_placeholder
        )
        if not df_novas_faturas.empty:
             st.session_state.df_processado = pd.DataFrame() 

    elif st.session_state.df_processado.empty and not arquivos_para_processar_agora and uploaded_files:
        log_mensagem_app(f"Arquivos parecem já constar como processados, mas não há dados. Reprocessando todos os {len(uploaded_files)} arquivos selecionados.", "warning")
        st.session_state.nomes_arquivos_faturas_ja_processados = set()
        df_novas_faturas = processar_faturas(
            uploaded_files,
            usar_cat_especifica_bool,
            caminho_arquivo_estab_final,
            log_placeholder
        )


    if not df_novas_faturas.empty:
        df_novas_faturas[COLUNA_DATA] = pd.to_datetime(df_novas_faturas[COLUNA_DATA], errors='coerce')
        df_novas_faturas.dropna(subset=[COLUNA_DATA], inplace=True)
        
        if COLUNA_FATURA_ORIGEM not in df_novas_faturas.columns:
            log_mensagem_app(f"ALERTA: Coluna '{COLUNA_FATURA_ORIGEM}' não encontrada nos novos dados processados. Isso pode afetar a identificação de duplicatas e o rastreamento da origem.", "error")
        
        df_existente = st.session_state.df_processado.copy() if not st.session_state.df_processado.empty else pd.DataFrame()
        
        if novos_nomes_arquivos.issubset(st.session_state.nomes_arquivos_faturas_ja_processados) and not arquivos_para_processar_agora:
             df_combinado = df_novas_faturas.copy()
        else:
            df_combinado = pd.concat([df_existente, df_novas_faturas], ignore_index=True)
        
        subset_duplicatas = [COLUNA_TITULO, COLUNA_DATA, COLUNA_VALOR]
        if COLUNA_ID in df_combinado.columns: 
            subset_duplicatas = [COLUNA_ID]
            if df_combinado[COLUNA_ID].isnull().any():
                 log_mensagem_app("Usando ID Nubank para remover duplicatas. IDs ausentes (NaN) podem não ser tratados idealmente.", "warning")
        elif COLUNA_FATURA_ORIGEM in df_combinado.columns:
            subset_duplicatas.append(COLUNA_FATURA_ORIGEM)
        
        subset_duplicatas_existentes = [col for col in subset_duplicatas if col in df_combinado.columns]
        if subset_duplicatas_existentes:
             df_combinado.drop_duplicates(subset=subset_duplicatas_existentes, keep='first', inplace=True)

        df_combinado.reset_index(drop=True, inplace=True)
        df_combinado[COLUNA_EDIT_ID] = df_combinado.index 
        
        st.session_state.df_processado = df_combinado.copy()
        
        nomes_faturas_processadas_novas = set()
        if COLUNA_FATURA_ORIGEM in df_novas_faturas.columns:
             nomes_faturas_processadas_novas = set(df_novas_faturas[COLUNA_FATURA_ORIGEM].unique())
        
        if not arquivos_para_processar_agora and uploaded_files:
            for f_up in uploaded_files:
                 st.session_state.nomes_arquivos_faturas_ja_processados.add(f_up.name)
        else: 
            for f_proc_obj in arquivos_para_processar_agora:
                if f_proc_obj.name in nomes_faturas_processadas_novas or not nomes_faturas_processadas_novas:
                    st.session_state.nomes_arquivos_faturas_ja_processados.add(f_proc_obj.name)
        st.rerun()
    elif uploaded_files and df_novas_faturas.empty and arquivos_para_processar_agora:
        log_mensagem_app("Processamento dos novos arquivos resultou em dados vazios. Verifique o formato dos CSVs ou as mensagens de erro anteriores.", "error")


if not st.session_state.df_processado.empty:
    df_dashboard_master = preparar_dataframe_dashboard(st.session_state.df_processado)

    with st.expander("✏️ Revisar e Editar Categorias de Consumo", expanded=False):
        col_edit_filt1, col_edit_filt2 = st.columns(2)
        st.session_state.edit_search_term = col_edit_filt1.text_input(
            "Buscar Título (edição de consumo):",
            value=st.session_state.edit_search_term,
            key="search_edit_v16" 
        )
        
        df_para_edicao_consumo = df_dashboard_master[
            ~df_dashboard_master[COLUNA_CATEGORIA].isin(CATEGORIAS_FINANCEIRAS_FIXAS)
        ].copy()

        current_unique_cats_para_edicao = sorted(df_para_edicao_consumo[COLUNA_CATEGORIA].dropna().unique().tolist())
        categorias_disponiveis_filtro_edicao = ["Todas"] + current_unique_cats_para_edicao
        
        if st.session_state.edit_category_filter not in categorias_disponiveis_filtro_edicao:
            st.session_state.edit_category_filter = "Todas"
            
        st.session_state.edit_category_filter = col_edit_filt2.selectbox(
            "Filtrar Categoria (edição de consumo):",
            options=categorias_disponiveis_filtro_edicao,
            index=categorias_disponiveis_filtro_edicao.index(st.session_state.edit_category_filter),
            key="cat_filt_edit_v16"
        )
        
        df_edit_display = df_para_edicao_consumo.copy()
        if st.session_state.edit_search_term:
            df_edit_display = df_edit_display[df_edit_display[COLUNA_TITULO].str.contains(st.session_state.edit_search_term, case=False, na=False)]
        if st.session_state.edit_category_filter != "Todas":
            df_edit_display = df_edit_display[df_edit_display[COLUNA_CATEGORIA] == st.session_state.edit_category_filter]
        
        items_per_page_edit = st.slider("Itens p/ página (edição):", 5, 50, 10, key="items_edit_v16")
        
        if not df_edit_display.empty:
            total_pages_edit = max(1, (len(df_edit_display) - 1) // items_per_page_edit + 1)
            if st.session_state.edit_current_page > total_pages_edit:
                st.session_state.edit_current_page = total_pages_edit
                
            st.session_state.edit_current_page = st.number_input(
                "Página (edição):",
                min_value=1, max_value=total_pages_edit,
                value=st.session_state.edit_current_page, step=1,
                key="page_edit_v16"
            )
            start_idx_edit = (st.session_state.edit_current_page - 1) * items_per_page_edit
            end_idx_edit = start_idx_edit + items_per_page_edit
            df_page_edit = df_edit_display.iloc[start_idx_edit:end_idx_edit]
            
            cat_options_edit_consumo_base = [
                cat for cat in st.session_state.categorias_editaveis 
                if cat not in CATEGORIAS_FINANCEIRAS_FIXAS
            ]
            OPCAO_CRIAR_NOVA = " < Criar Nova Categoria > "

            for _, row_to_edit in df_page_edit.iterrows():
                edit_id = row_to_edit[COLUNA_EDIT_ID]
                current_cat = row_to_edit[COLUNA_CATEGORIA]
                titulo_original_transacao = row_to_edit[COLUNA_TITULO]
                
                cols_display_edit = st.columns([0.4, 0.15, 0.15, 0.3])
                data_formatada = pd.to_datetime(row_to_edit[COLUNA_DATA]).strftime('%d/%m/%y') if pd.notna(row_to_edit[COLUNA_DATA]) else "Data Inválida"
                cols_display_edit[0].markdown(f"**{data_formatada}** - {row_to_edit[COLUNA_TITULO]}")
                cols_display_edit[1].markdown(f"R$ {row_to_edit[COLUNA_VALOR]:.2f}")
                cols_display_edit[2].markdown(f"*Orig: {row_to_edit.get(COLUNA_FATURA_ORIGEM, 'N/A')}*")
                
                temp_cat_options_edit_para_linha = cat_options_edit_consumo_base[:]
                if pd.notna(current_cat) and current_cat not in temp_cat_options_edit_para_linha:
                    temp_cat_options_edit_para_linha.append(current_cat)
                    temp_cat_options_edit_para_linha.sort()
                
                opcoes_finais_selectbox = temp_cat_options_edit_para_linha + [OPCAO_CRIAR_NOVA]
                
                default_index_cat_edit = 0
                if pd.notna(current_cat) and current_cat in opcoes_finais_selectbox:
                    default_index_cat_edit = opcoes_finais_selectbox.index(current_cat)
                elif "Sem Categoria/Pix Credito" in opcoes_finais_selectbox: 
                    default_index_cat_edit = opcoes_finais_selectbox.index("Sem Categoria/Pix Credito")

                selectbox_key = f"sel_cat_edit_v_new_feat_{edit_id}"
                categoria_escolhida_no_selectbox = cols_display_edit[3].selectbox(
                    "Categoria:", opcoes_finais_selectbox,
                    index=default_index_cat_edit, key=selectbox_key,
                    label_visibility="collapsed"
                )

                nova_categoria_a_aplicar = None

                if categoria_escolhida_no_selectbox == OPCAO_CRIAR_NOVA:
                    input_nova_categoria_key = f"input_new_cat_v_new_feat_{edit_id}"
                    btn_salvar_nova_cat_key = f"btn_save_new_cat_v_new_feat_{edit_id}"
                    
                    with cols_display_edit[3].container():
                        nome_nova_categoria_input = st.text_input(
                            "Nome da Nova Categoria:",
                            key=input_nova_categoria_key,
                            placeholder="Ex: Padaria ABC"
                        )
                        if st.button("Salvar Nova", key=btn_salvar_nova_cat_key, type="primary"):
                            nome_nova_categoria_strip = nome_nova_categoria_input.strip()
                            if nome_nova_categoria_strip:
                                if nome_nova_categoria_strip in CATEGORIAS_FINANCEIRAS_FIXAS:
                                    st.error(f"'{nome_nova_categoria_strip}' é uma categoria financeira fixa e não pode ser criada para consumo.")
                                elif nome_nova_categoria_strip in st.session_state.categorias_editaveis:
                                    st.warning(f"Categoria '{nome_nova_categoria_strip}' já existe. Será aplicada à transação.")
                                    nova_categoria_a_aplicar = nome_nova_categoria_strip
                                else:
                                    st.session_state.categorias_base_memoria[nome_nova_categoria_strip] = []
                                    _atualizar_lista_categorias_editaveis()
                                    
                                    if salvar_categorias_base_para_json(st.session_state.categorias_base_memoria):
                                        log_mensagem_app(f"Nova categoria '{nome_nova_categoria_strip}' criada e salva no JSON.", "success")
                                        nova_categoria_a_aplicar = nome_nova_categoria_strip
                                    else:
                                        log_mensagem_app(f"ERRO ao salvar nova categoria '{nome_nova_categoria_strip}' no JSON.", "error")
                            else:
                                st.warning("Nome da nova categoria não pode ser vazio.")
                else:
                    nova_categoria_a_aplicar = categoria_escolhida_no_selectbox

                if nova_categoria_a_aplicar and nova_categoria_a_aplicar != current_cat:
                    idx_global_df = st.session_state.df_processado[st.session_state.df_processado[COLUNA_EDIT_ID] == edit_id].index
                    if not idx_global_df.empty:
                        st.session_state.df_processado.loc[idx_global_df[0], COLUNA_CATEGORIA] = nova_categoria_a_aplicar
                        
                        titulo_norm_para_json = normalizar_texto(titulo_original_transacao)
                        
                        if pd.notna(current_cat) and current_cat in st.session_state.categorias_base_memoria:
                            if isinstance(st.session_state.categorias_base_memoria[current_cat], list):
                                if titulo_norm_para_json in st.session_state.categorias_base_memoria[current_cat]:
                                    st.session_state.categorias_base_memoria[current_cat].remove(titulo_norm_para_json)
                                if not st.session_state.categorias_base_memoria[current_cat] and \
                                   current_cat not in CATEGORIAS_ESSENCIAIS_PARA_DROPDOWNS:
                                    del st.session_state.categorias_base_memoria[current_cat]
                        
                        if nova_categoria_a_aplicar not in CATEGORIAS_FINANCEIRAS_FIXAS:
                            if nova_categoria_a_aplicar not in st.session_state.categorias_base_memoria:
                                st.session_state.categorias_base_memoria[nova_categoria_a_aplicar] = []
                            
                            if not isinstance(st.session_state.categorias_base_memoria.get(nova_categoria_a_aplicar), list):
                                st.session_state.categorias_base_memoria[nova_categoria_a_aplicar] = []

                            if titulo_norm_para_json not in st.session_state.categorias_base_memoria[nova_categoria_a_aplicar]:
                                st.session_state.categorias_base_memoria[nova_categoria_a_aplicar].append(titulo_norm_para_json)
                        
                        _atualizar_lista_categorias_editaveis()
                        
                        if salvar_categorias_base_para_json(st.session_state.categorias_base_memoria):
                            log_mensagem_app(f"Transação '{str(titulo_original_transacao)[:30]}...' atualizada para '{nova_categoria_a_aplicar}'. Base de categorias salva.", "success")
                        else:
                            log_mensagem_app(f"ERRO ao salvar base de categorias após atualizar '{str(titulo_original_transacao)[:30]}...'.", "error")
                        st.rerun()
                st.markdown("---")
        else:
            if df_dashboard_master[~df_dashboard_master[COLUNA_CATEGORIA].isin(CATEGORIAS_FINANCEIRAS_FIXAS)].empty:
                 st.info("Não há transações de consumo para editar. Todas as transações atuais pertencem a categorias financeiras/fixas.")
            else:
                 st.info("Nenhum item de consumo corresponde aos filtros de edição atuais.")

    df_para_relatorios = df_dashboard_master.copy()
    
    st.sidebar.subheader("Filtros do Dashboard")
    
    if 'ciclo_fatura' not in df_para_relatorios.columns or df_para_relatorios['ciclo_fatura'].isnull().all():
        st.sidebar.warning("Coluna 'ciclo_fatura' não disponível para filtro.")
    else:
        all_periodos_options = sorted(df_para_relatorios['ciclo_fatura'].dropna().unique(), reverse=True)
        all_periodos_for_multiselect = ["Todos"] + all_periodos_options
        
        current_selection_periodos = st.session_state.filtros_sidebar['periodos_ciclo_arquivo']
        valid_default_periodos = [p for p in current_selection_periodos if p in all_periodos_for_multiselect]
        if not valid_default_periodos and "Todos" in all_periodos_for_multiselect:
            valid_default_periodos = ["Todos"]

        selected_periodos = st.sidebar.multiselect(
            "Ciclo(s) da Fatura (Arquivo):",
            all_periodos_for_multiselect,
            default=valid_default_periodos,
            key="multi_periodo_ciclo_v3_sidebar_refined"
        )
        st.session_state.filtros_sidebar['periodos_ciclo_arquivo'] = selected_periodos

        if selected_periodos and "Todos" not in selected_periodos:
            df_para_relatorios = df_para_relatorios[df_para_relatorios['ciclo_fatura'].isin(selected_periodos)]
        elif not selected_periodos and "Todos" not in selected_periodos :
             df_para_relatorios = pd.DataFrame(columns=df_dashboard_master.columns)

    df_despesas_pre_cat_filter = df_para_relatorios[
        ~df_para_relatorios[COLUNA_CATEGORIA].isin(CATEGORIAS_FINANCEIRAS_FIXAS) &
        (df_para_relatorios[COLUNA_VALOR] > 0)
    ].copy()

    unique_cats_despesa_options = sorted(df_despesas_pre_cat_filter[COLUNA_CATEGORIA].astype(str).dropna().unique().tolist())
    all_cat_despesa_for_multiselect = ["Todos"] + [cat for cat in unique_cats_despesa_options if cat != 'nan']

    current_selection_categorias = st.session_state.filtros_sidebar['categorias_despesa']
    valid_default_cats_despesa = [c for c in current_selection_categorias if c in all_cat_despesa_for_multiselect]
    if not valid_default_cats_despesa and "Todos" in all_cat_despesa_for_multiselect:
        valid_default_cats_despesa = ["Todos"]

    selected_cats_despesa = st.sidebar.multiselect(
        "Categoria(s) Despesa Consumo:",
        all_cat_despesa_for_multiselect,
        default=valid_default_cats_despesa,
        key="multi_cat_dash_v16_sidebar_refined"
    )
    st.session_state.filtros_sidebar['categorias_despesa'] = selected_cats_despesa

    df_despesas_relatorio = df_despesas_pre_cat_filter.copy()
    if selected_cats_despesa and "Todos" not in selected_cats_despesa:
        df_despesas_relatorio = df_despesas_relatorio[df_despesas_relatorio[COLUNA_CATEGORIA].isin(selected_cats_despesa)]
    elif not selected_cats_despesa and "Todos" not in selected_cats_despesa:
        df_despesas_relatorio = pd.DataFrame(columns=df_despesas_pre_cat_filter.columns)

    df_encargos_kpi = df_para_relatorios[
        df_para_relatorios[COLUNA_CATEGORIA].isin(CATEGORIAS_ENCARGOS_FINANCEIROS) &
        (df_para_relatorios[COLUNA_VALOR] > 0)
    ]

    st.header("Resumo Financeiro")
    total_gasto_consumo_kpi = 0.0
    media_diaria_consumo_kpi = 0.0
    if not df_despesas_relatorio.empty:
        total_gasto_consumo_kpi = df_despesas_relatorio[COLUNA_VALOR].sum()
        if COLUNA_DATA in df_despesas_relatorio.columns and not df_despesas_relatorio[COLUNA_DATA].isnull().all():
            num_dias_com_gastos = df_despesas_relatorio[COLUNA_DATA].dt.date.nunique()
            if num_dias_com_gastos > 0:
                soma_diaria_df = df_despesas_relatorio.groupby(df_despesas_relatorio[COLUNA_DATA].dt.date)[COLUNA_VALOR].sum()
                media_diaria_consumo_kpi = soma_diaria_df.mean()

    total_encargos_kpi = df_encargos_kpi[COLUNA_VALOR].sum() if not df_encargos_kpi.empty else 0.0

    kpi_col1, kpi_col2, kpi_col3 = st.columns(3)
    kpi_col1.metric("Total Gasto (Consumo)", f"R$ {total_gasto_consumo_kpi:,.2f}")
    kpi_col2.metric("Média Gasto Diário (Consumo)", f"R$ {media_diaria_consumo_kpi:,.2f}")
    kpi_col3.metric("Total Encargos Financeiros", f"R$ {total_encargos_kpi:,.2f}", help=f"Juros, multas, IOF, etc. ({', '.join(CATEGORIAS_ENCARGOS_FINANCEIROS)})")
    st.markdown("---")

    df_historico_consumo_plot = df_dashboard_master[
        ~df_dashboard_master[COLUNA_CATEGORIA].isin(CATEGORIAS_FINANCEIRAS_FIXAS) &
        (df_dashboard_master[COLUNA_VALOR] > 0) &
        pd.notna(df_dashboard_master['mes_ano'])
    ].copy()

    if not df_historico_consumo_plot.empty:
        gastos_mensais_evolucao = df_historico_consumo_plot.groupby('mes_ano')[COLUNA_VALOR].sum().reset_index().sort_values('mes_ano')
        if not gastos_mensais_evolucao.empty:
            fig_evolucao_consumo = px.line(
                gastos_mensais_evolucao, x='mes_ano', y=COLUNA_VALOR,
                title="Evolução dos Gastos de Consumo Mensais (Histórico Completo)", markers=True,
                labels={COLUNA_VALOR: "Gasto Consumo (R$)", 'mes_ano': "Mês/Ano da Transação"}
            )
            st.plotly_chart(fig_evolucao_consumo, use_container_width=True)

    plot_col_freq_uso, plot_col_custos_fin = st.columns(2)

    if not df_historico_consumo_plot.empty and 'mes_ano' in df_historico_consumo_plot.columns and COLUNA_DATA in df_historico_consumo_plot.columns:
        df_freq_calc = df_historico_consumo_plot.copy()
        if not df_freq_calc.empty and not df_freq_calc[COLUNA_DATA].isnull().all():
            dias_com_gastos_por_mes = df_freq_calc.groupby('mes_ano')[COLUNA_DATA].nunique().reset_index()
            dias_com_gastos_por_mes.rename(columns={COLUNA_DATA: 'dias_com_transacao'}, inplace=True)
            
            if not dias_com_gastos_por_mes.empty:
                dias_com_gastos_por_mes['temp_date_for_daysinmonth'] = pd.to_datetime(dias_com_gastos_por_mes['mes_ano'].astype(str) + '-01', errors='coerce')
                dias_com_gastos_por_mes.dropna(subset=['temp_date_for_daysinmonth'], inplace=True)
                
                if not dias_com_gastos_por_mes.empty:
                    dias_com_gastos_por_mes['total_dias_no_mes'] = dias_com_gastos_por_mes['temp_date_for_daysinmonth'].dt.days_in_month
                    dias_com_gastos_por_mes['frequencia_uso_percent'] = np.where(
                        dias_com_gastos_por_mes['total_dias_no_mes'] > 0,
                        (dias_com_gastos_por_mes['dias_com_transacao'] / dias_com_gastos_por_mes['total_dias_no_mes']) * 100, 0
                    )
                    dias_com_gastos_por_mes.sort_values('mes_ano', inplace=True)
                    
                    if not dias_com_gastos_por_mes.empty and 'frequencia_uso_percent' in dias_com_gastos_por_mes.columns:
                        fig_freq_uso = px.bar(
                            dias_com_gastos_por_mes, x='mes_ano', y='frequencia_uso_percent',
                            title="Frequência de Uso Mensal (Consumo - Histórico Completo)",
                            labels={'frequencia_uso_percent': "Frequência de Uso (%)", 'mes_ano': "Mês/Ano"},
                            text_auto=".1f"
                        )
                        fig_freq_uso.update_yaxes(ticksuffix="%")
                        plot_col_freq_uso.plotly_chart(fig_freq_uso, use_container_width=True)

    df_encargos_historico_detalhes = df_dashboard_master[
        df_dashboard_master[COLUNA_CATEGORIA].isin(CATEGORIAS_ENCARGOS_FINANCEIROS) &
        (df_dashboard_master[COLUNA_VALOR] > 0) &
        pd.notna(df_dashboard_master['mes_ano'])
    ].copy()

    if not df_encargos_historico_detalhes.empty and 'mes_ano' in df_encargos_historico_detalhes.columns:
        encargos_mensais_plot_agg = df_encargos_historico_detalhes.groupby('mes_ano')[COLUNA_VALOR].sum().reset_index()
        if not encargos_mensais_plot_agg.empty:
            encargos_mensais_plot_agg.sort_values('mes_ano', inplace=True)
            total_encargos_historico = encargos_mensais_plot_agg[COLUNA_VALOR].sum()
            fig_custos_fin_mensais = px.bar(
                encargos_mensais_plot_agg, x='mes_ano', y=COLUNA_VALOR,
                title=f"Custos Financeiros Mensais (Total Histórico: R$ {total_encargos_historico:,.2f})",
                labels={COLUNA_VALOR: "Total Encargos (R$)", 'mes_ano': "Mês/Ano"},
                text_auto=".2f"
            )
            plot_col_custos_fin.plotly_chart(fig_custos_fin_mensais, use_container_width=True)

            with plot_col_custos_fin.expander("Ver Detalhes dos Custos Financeiros (Histórico Completo)"):
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
        top_n_cat_consumo = st.slider("Top N Categorias de Consumo (Período Filtrado):", 3, 20, 10, key="slider_top_n_cat_g2_v7")
        gastos_por_categoria_plot = df_despesas_relatorio.groupby(COLUNA_CATEGORIA)[COLUNA_VALOR].sum().reset_index().sort_values(by=COLUNA_VALOR, ascending=False).head(top_n_cat_consumo)
        if not gastos_por_categoria_plot.empty:
            fig_dist_categoria_consumo = px.bar(
                gastos_por_categoria_plot, x=COLUNA_CATEGORIA, y=COLUNA_VALOR,
                title=f"Top {top_n_cat_consumo} Gastos de Consumo por Categoria (Período Filtrado)", text_auto=".2f",
                labels={COLUNA_VALOR: "Gasto Consumo (R$)", COLUNA_CATEGORIA: "Categoria"}
            )
            fig_dist_categoria_consumo.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig_dist_categoria_consumo, use_container_width=True)

    if not df_despesas_relatorio.empty:
        plot_col_dia_semana, plot_col_dia_mes = st.columns(2)
        mapa_dias_pt = {"Monday":"Seg", "Tuesday":"Ter", "Wednesday":"Qua", "Thursday":"Qui", "Friday":"Sex", "Saturday":"Sáb", "Sunday":"Dom"}
        ordem_dias_plot = list(mapa_dias_pt.values())
        
        if 'dia_da_semana' in df_despesas_relatorio.columns and not df_despesas_relatorio['dia_da_semana'].isnull().all():
            df_dia_semana_plot = df_despesas_relatorio.copy()
            df_dia_semana_plot['dia_da_semana_pt'] = df_dia_semana_plot['dia_da_semana'].map(mapa_dias_pt)
            df_dia_semana_plot = df_dia_semana_plot.groupby('dia_da_semana_pt')[COLUNA_VALOR].sum().reindex(ordem_dias_plot).reset_index().dropna(subset=[COLUNA_VALOR])
            if not df_dia_semana_plot.empty:
                fig_dia_semana_plot = px.bar(
                    df_dia_semana_plot, x='dia_da_semana_pt', y=COLUNA_VALOR,
                    title="Gastos de Consumo por Dia da Semana (Período Filtrado)",
                    labels={COLUNA_VALOR: "Gasto Consumo (R$)", 'dia_da_semana_pt':"Dia da Semana"}
                )
                plot_col_dia_semana.plotly_chart(fig_dia_semana_plot, use_container_width=True)

        if 'dia_do_mes' in df_despesas_relatorio.columns and not df_despesas_relatorio['dia_do_mes'].isnull().all():
            df_dia_mes_plot = df_despesas_relatorio.groupby('dia_do_mes')[COLUNA_VALOR].sum().reset_index().dropna(subset=[COLUNA_VALOR])
            if not df_dia_mes_plot.empty:
                fig_dia_mes_plot = px.bar(
                    df_dia_mes_plot, x='dia_do_mes', y=COLUNA_VALOR,
                    title="Gastos de Consumo por Dia do Mês (Período Filtrado)",
                    labels={COLUNA_VALOR: "Gasto Consumo (R$)", 'dia_do_mes':"Dia do Mês"},
                    text_auto=".2f"
                )
                fig_dia_mes_plot.update_layout(xaxis=dict(type='category'))
                plot_col_dia_mes.plotly_chart(fig_dia_mes_plot, use_container_width=True)

    if not df_despesas_relatorio.empty:
        top_n_estabelecimentos = st.slider("Top N Estabelecimentos (Consumo - Período Filtrado):", 5, 50, 15, key="slider_top_estab_g4_v7")
        gastos_estabelecimentos_plot = df_despesas_relatorio.groupby(COLUNA_TITULO)[COLUNA_VALOR].sum().reset_index().sort_values(by=COLUNA_VALOR, ascending=False).head(top_n_estabelecimentos)
        if not gastos_estabelecimentos_plot.empty:
            fig_estabelecimentos_plot = px.bar(
                gastos_estabelecimentos_plot, x=COLUNA_TITULO, y=COLUNA_VALOR,
                title=f"Top {top_n_estabelecimentos} Estabelecimentos (Consumo - Período Filtrado)", text_auto=".2f",
                labels={COLUNA_VALOR: "Gasto Consumo (R$)", COLUNA_TITULO: "Estabelecimento"}
            )
            fig_estabelecimentos_plot.update_layout(xaxis_tickangle=-60, height=500)
            st.plotly_chart(fig_estabelecimentos_plot, use_container_width=True)

    if not df_historico_consumo_plot.empty: 
        top_n_media_cat_consumo = st.slider("Top N Categorias por Média Mensal (Consumo - Histórico Completo):", 3, 20, 10, key="slider_top_n_media_cat_g5_v7")
        if 'mes_ano' in df_historico_consumo_plot.columns and COLUNA_CATEGORIA in df_historico_consumo_plot.columns:
            media_cat_mes_historico_plot = df_historico_consumo_plot.groupby(['mes_ano', COLUNA_CATEGORIA])[COLUNA_VALOR].sum().unstack(fill_value=0).mean(axis=0).reset_index()
            media_cat_mes_historico_plot.columns = [COLUNA_CATEGORIA, 'media_mensal_gasto']
            media_cat_mes_historico_plot = media_cat_mes_historico_plot.sort_values(by='media_mensal_gasto', ascending=False).head(top_n_media_cat_consumo)
            if not media_cat_mes_historico_plot.empty:
                fig_media_cat_plot = px.bar(
                    media_cat_mes_historico_plot, x=COLUNA_CATEGORIA, y='media_mensal_gasto',
                    title=f"Top {top_n_media_cat_consumo} Categorias por Média Mensal de Gasto (Consumo - Histórico)",
                    text_auto=".2f", labels={'media_mensal_gasto':"Média Mensal Consumo (R$)", COLUNA_CATEGORIA: "Categoria"}
                )
                fig_media_cat_plot.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig_media_cat_plot, use_container_width=True)

    st.markdown("---")
    st.header("Consulta Detalhada por Fatura")

    if 'ciclo_fatura' in df_dashboard_master.columns and df_dashboard_master['ciclo_fatura'].notna().any():
        lista_ciclos_disponiveis_consulta = sorted(df_dashboard_master['ciclo_fatura'].dropna().unique(), reverse=True)

        current_selection_ciclos_consulta = st.session_state.get('ciclos_consulta_selecionados', [])
        valid_default_ciclos_consulta = [c for c in current_selection_ciclos_consulta if c in lista_ciclos_disponiveis_consulta]

        ciclos_selecionados_agora = st.multiselect(
            "Selecione o(s) Ciclo(s) da Fatura para ver os detalhes:",
            options=lista_ciclos_disponiveis_consulta,
            default=valid_default_ciclos_consulta,
            key="consulta_ciclo_multiselect_v3_refined"
        )
        st.session_state.ciclos_consulta_selecionados = ciclos_selecionados_agora

        if ciclos_selecionados_agora:
            df_consulta_fatura_base = df_dashboard_master[
                df_dashboard_master['ciclo_fatura'].isin(ciclos_selecionados_agora)
            ].copy()

            if not df_consulta_fatura_base.empty:
                colunas_exibir_map = {
                    COLUNA_DATA: 'Data', COLUNA_TITULO: 'Descrição',
                    COLUNA_CATEGORIA: 'Categoria', COLUNA_VALOR: 'Valor (R$)',
                    COLUNA_PARCELA_ATUAL: 'Parc. Atual', COLUNA_TOTAL_PARCELAS: 'Parc. Total',
                    'ciclo_fatura': 'Ciclo Fatura'
                }
                colunas_presentes_para_exibir = [key for key in colunas_exibir_map if key in df_consulta_fatura_base.columns]
                
                sort_by_raw_cols = []
                if 'ciclo_fatura' in colunas_presentes_para_exibir: sort_by_raw_cols.append('ciclo_fatura')
                if COLUNA_DATA in colunas_presentes_para_exibir: sort_by_raw_cols.append(COLUNA_DATA)
                
                if sort_by_raw_cols:
                    df_consulta_fatura_sorted = df_consulta_fatura_base.sort_values(by=sort_by_raw_cols, ascending=[True, True])
                else:
                    df_consulta_fatura_sorted = df_consulta_fatura_base
                
                df_consulta_exibir = df_consulta_fatura_sorted[colunas_presentes_para_exibir].rename(columns=colunas_exibir_map)

                if 'Data' in df_consulta_exibir.columns: 
                    df_consulta_exibir['Data'] = pd.to_datetime(df_consulta_exibir['Data']).dt.strftime('%d/%m/%Y')
            
                format_dict = {'Valor (R$)': "R$ {:,.2f}"}
                if 'Parc. Atual' in df_consulta_exibir.columns: format_dict['Parc. Atual'] = "{:.0f}"
                if 'Parc. Total' in df_consulta_exibir.columns: format_dict['Parc. Total'] = "{:.0f}"


                st.dataframe(
                    df_consulta_exibir.style.format(format_dict, na_rep='-'), 
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("Nenhum dado encontrado para os ciclos selecionados na consulta detalhada.")
        else:
            st.info("Selecione um ou mais ciclos na lista acima para ver os detalhes das transações.")
    else:
        st.info("Não há dados de ciclos de fatura disponíveis para consulta. Processe arquivos de fatura primeiro.")

    st.markdown("---")
    st.header("🤝 Contribua para Melhorar a Categorização")
    st.markdown("""A categorização automática pode não ser perfeita para todos os estabelecimentos. Suas edições manuais são salvas localmente no arquivo `Categorias.json` e ajudam a refinar o sistema para você.
    Se desejar, você pode compartilhar seu arquivo de categorias para ajudar a aprimorar a base de conhecimento geral do categorizador para todos os usuários!""")
    if st.button("Quero Contribuir com Minhas Categorizações!", key="btn_contribuir_v7"):
        categorias_base_para_contribuir_str = json.dumps(st.session_state.categorias_base_memoria, indent=4, ensure_ascii=False)
        st.download_button(
            label="1. Baixar meu Arquivo de Categorias (.json)",
            data=categorias_base_para_contribuir_str,
            file_name=f"minhas_categorias_base_{datetime.now().strftime('%Y%m%d')}.json",
            mime="application/json",
            key="download_contrib_categorias_v7"
        )
        st.markdown("""2. Após baixar, envie para: **jcaxavier2@gmail.com** com o assunto "Contribuição - Categorias Dashboard Faturas".
        Sua contribuição é anônima em relação aos seus dados de fatura, pois apenas o mapeamento de NOMES DE ESTABELECIMENTOS para CATEGORIAS é compartilhado (armazenado no `Categorias.json`). Nenhuma informação pessoal ou valor de transação é incluído neste arquivo.""")
        mailto_link = "mailto:jcaxavier2@gmail.com?subject=Contribuição%20-%20Categorias%20Dashboard%20Faturas&body=Olá,%0A%0ASegue%20meu%20arquivo%20de%20categorias%20(Categorias.json)%20em%20anexo.%0A%0ASe%20possível,%20informe%20o%20contexto%20de%20uso%20(ex:%20uso%20pessoal,%20teste,%20região%20predominante%20das%20compras%20se%20relevante%20para%20estabelecimentos%20locais).%0A%0AObrigado!"
        st.markdown(f"<a href='{mailto_link}'>Ou clique aqui para abrir seu e-mail e anexar o arquivo</a>", unsafe_allow_html=True)

else: 
    if not uploaded_files:
        if 'log_messages' not in st.session_state or st.session_state.log_messages == ["Aqui aparecerão as mensagens de informação do processo."]:
             st.info("⬆️ FAÇA O UPLOAD DAS FATURAS EM CSV na barra lateral para iniciar a análise.")
    elif uploaded_files :
        st.info("📂 Arquivos selecionados. Clique em '🚀 Processar' na barra lateral para visualizar os dados.")