# Ligar o botão à planilha Google

1. Abra a planilha Google e escolha **Extensões → Apps Script**.
2. Cole o conteúdo de `Code.gs` no editor e salve.
3. Em **Configurações do projeto**, ative a exibição do arquivo `appsscript.json` e substitua seu conteúdo pelo manifesto deste diretório.
4. Em **Configurações do projeto → Propriedades do script**, crie `API_URL` com o endereço do serviço Cloud Run e `API_KEY` com a chave definida para o serviço.
5. Atualize a planilha. Use o menu **Reconciliação → Processar contrato selecionado**. Para usar um desenho como botão, selecione o desenho, abra o menu de três pontos, escolha **Atribuir script** e informe `processSelectedContract`.

O botão lê a linha selecionada na aba `contracts`, chama o serviço para aquele contrato e atualiza as abas `installments`, `accounting`, `reconciliations`, `statements`, `reconciliation_evidence` e `processing_runs`.

## Antes de usar

- As abas precisam manter os cabeçalhos da planilha de demonstração; o script aceita os nomes atuais, inclusive os erros de digitação existentes em alguns cabeçalhos contábeis.
- Para o protótipo, o endpoint Cloud Run será acessível pela internet e protegido por `API_KEY`. Qualquer pessoa com a chave pode chamar o endpoint. Use somente dados sintéticos; não use dados de clientes ou credenciais bancárias.
- Não coloque a chave no código, em células ou em GitHub. Guarde-a somente nas propriedades do script e como variável secreta no serviço.
- A planilha e o serviço ainda não foram ligados à sua conta Google. Isso é feito depois da implantação do serviço e da autorização do Apps Script.
