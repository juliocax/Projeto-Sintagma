
# Syn(tagmᵃ)

Este painel interativo que visa ser uma ferramenta simples para acompanhar e entender melhor o consumo no cartão de crédito.

O nome "Syn(tagmᵃ)" faz referência ao conceito de "sintagma", que representa uma unidade de palavras que se organizam para formar um significado. A ideia conversa com o intuito do painel que é categorizae os dados de faturas de cartão de crédito, transformando informações dispersas em um painel para facilitar o entendimento de consumo.

### 1. Funcionalidades do Painel

Este painel oferece as seguintes funcionalidades:

*   **Recebe as Faturas do Seu Cartão de Credito:** Permite o upload de arquivos CSV contendo dados das faturas do cartão de credito, por enquanto apenas da Nubank.
*   **Classificação de Compras:** Classifica automaticamente as compras em categorias como "Alimentação", "Transporte" dentre outras. A classificação pode ser ajustada ou adicionada manualmente, e o sistema aprende com as alterações.
*   **Visualização de Dados:** Exibe gráficos que mostram:
    *   Gastos totais, média diária e custos com juros e taxas.
    *   Evolução dos gastos ao longo do tempo.
    *   Frequência de uso do cartão.
    *   Gastos por categoria, dia da semana e dia do mês.
    *   Estabelecimentos mais utilizados e médias mensais por categoria.
*   **Edição de Categorias:** Permite revisar e alterar categorias de compras diretamente no painel.
*   **Consulta de Faturas:** Exibe detalhes de compras de faturas específicas.
*   **Salvamento de Sessão:** Permite salvar o progresso em um arquivo JSON para continuar a análise posteriormente.

### 2. Instruções de Uso

1. **Acesse o Painel:**
   * Online: Abra o link fornecido no navegador.
   * Local: Siga as instruções de instalação e execução descritas na seção "Instalação Local".

2. **Carregue as Faturas:**
   * Use a opção "Selecione CSVs de fatura" na barra lateral para carregar os arquivos.

3. **Configure a Classificação:**
   * Escolha entre classificação genérica ou específica (com base em dados públicos de CNPJs, se disponível).

4. **Processe os Dados:**
   * Clique em "Processar" para organizar e visualizar os dados.

5. **Explore os Resultados:**
   * Analise os gráficos e resumos exibidos no painel principal.

6. **Edite Categorias:**
   * Ajuste categorias manualmente na seção de revisão.

7. **Salve ou Restaure Sessões:**
   * Use as opções de salvar ou carregar progresso na barra lateral.

8. **Reinicie se Necessário:**
   * Utilize a opção "Limpar Dados" para começar do zero.

### 3. Instalação Local

**Pré-requisitos:**
* Python 3.10 ou superior.
* Git.

**Passos:**
1. Clone o repositório do projeto:
   ```bash
   git clone <URL_DO_REPOSITORIO>
   cd <NOME_DO_REPOSITORIO>
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
   streamlit run dashboard_faturas.py
   ```

### 4. Uso Online

Se o painel estiver disponível online, basta acessar o link fornecido. Para manter alterações e dados entre sessões, utilize a funcionalidade de salvar e carregar progresso.

### 5. Observações

* Certifique-se de que os arquivos CSV estejam no formato esperado.
* Ajustes manuais nas categorias ajudam a melhorar a precisão do sistema.
* Para dúvidas ou problemas, consulte o desenvolvedor do projeto.


### 6. Contribuição do Usuário

A categorização automática pode não ser perfeita para todos os estabelecimentos. Por isso, as edições manuais realizadas pelo usuário são salvas localmente no arquivo `Categorias.json`. Essas edições ajudam a refinar o sistema para atender melhor às suas necessidades.

Se desejar, o usuário pode compartilhar seu arquivo de categorias para contribuir com a melhoria da base de conhecimento geral do categorizador. Essa colaboração ajuda a aprimorar o sistema para todos os usuários, tornando-o mais preciso e eficiente.
