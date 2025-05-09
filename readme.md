
# Syn(tagmᵃ)

[![Abrir Painel](https://img.shields.io/badge/Abrir%20Online-Streamlit-brightgreen?logo=streamlit)](https://projeto-sintagma.streamlit.app/) [![Instalar Painel](https://img.shields.io/badge/Instalar%20Local-pip%20install-blue?logo=pypi)](https://pypi.org/project/syntagma/) [![Documentação](https://img.shields.io/badge/Documentação-Docs-orange?logo=readthedocs)](https://projeto-sintagma-docs.com) [![Reportar Problema](https://img.shields.io/badge/Reportar%20Problema-GitHub-red?logo=github)](https://github.com/juliocax/Projeto-Sintagma/issues)

Este painel interativo que visa ser uma ferramenta simples para acompanhar e entender melhor o consumo no cartão de crédito.

O nome "Syn(tagmᵃ)" faz referência ao conceito de "sintagma", que representa uma unidade de palavras que se organizam para formar um significado. A ideia conversa com o intuito do painel que é categorizae os dados de faturas de cartão de crédito, transformando informações dispersas em um painel para facilitar o entendimento de consumo.

## Funcionalidades do Painel

#### 📂 **Faturas**
Permite o upload de arquivos CSV contendo dados das faturas do cartão de crédito (atualmente compatível com Nubank).

#### 🏷️ **Classificação de Compras**
Classifica automaticamente as compras em categorias.
A classificação pode ser ajustada manualmente, e o sistema aprende com as alterações realizadas.

#### 📊 **Visualização de Dados**
Exibe gráficos interativos para análise, incluindo:
- **Gastos Totais:** Média diária, custos com juros e taxas.
- **Evolução Temporal:** Gastos ao longo do tempo.
- **Frequência de Uso:** Dias e horários mais frequentes.
- **Categorias e Estabelecimentos:** Gastos por categoria, dia da semana, dia do mês e estabelecimentos mais utilizados.

#### ✏️ **Edição de Categorias**
Permite revisar e alterar categorias de determinadas compras, criar e excluir categorias diretamente no painel.

#### 💾 **Salvamento de Sessão**
Salve o progresso da análise em um arquivo JSON para continuar posteriormente.

> **Nota:** As edições manuais realizadas pelo usuário são salvas localmente e ajudam a melhorar a precisão do sistema.

## Instalação Local

**Pré-requisitos:**
* Python 3.10 ou superior.
* Git.

**Passos:**
1. Clone o repositório do projeto:
   ```bash
   git clone https://github.com/juliocax/Projeto-Sintagma.git
   cd Projeto-Sintagma
   ```
2. Crie e ative um ambiente virtual:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/macOS
   venv\Scripts\activate     # Windows
   ```
3. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```
4. Execute o painel:
   ```bash
   streamlit run sintagma.py
   ```

## Contribuição do Usuário

A categorização automática pode não ser perfeita para todos os estabelecimentos. Por isso, as edições manuais realizadas pelo usuário são salvas localmente no arquivo `Categorias.json`. Essas edições ajudam a refinar o sistema para atender melhor às suas necessidades.

Se desejar, o usuário pode compartilhar seu arquivo de categorias para contribuir com a melhoria da base de conhecimento geral do categorizador. Essa colaboração ajuda a aprimorar o sistema para todos os usuários, tornando-o mais preciso e eficiente.
