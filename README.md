# prepdev
Script de preparação do ambiente de desenvolvimento do sistema SIGMA.

# O que este script faz?
#### *Não necessáriamente nesta ordem*
* Verifica se as chaves RSA para acesso aos repositórios existe, e caso não exista, as gera;
* Verifica se as chaves RSA existentes dá acesso aos repositórios, caso não dê, exibe as chaves públicas para que o usuário possa fazer/solicitar a configuração dos repositórios;
* Configura o ssh para acessar cada repositório com sua respectiva chave;
* Instala as dependências do S.O.;
* Cria o ambiente virtual;
* Atualiza pacotes essenciais do ambiente virtual(pip e setuptools);
* Clona os repositórios;
* Instala as dependências dos projetos;
* Instala as dependências de testes e desenvolvimento;
* Valida a versão do SGDB;
* Valida a configuração do banco de dados, e, caso necessário, instrui o usuário a configurá-lo;
* Derruba conexões existentes com o banco de dados;
* Cria o banco de dados;
* Executa as migrações;
* Popula o banco de dados com dados de desenvolvimento;
* Cria comandos personalizados para facilitar o desenvolvimento;
* Imprime uma ajuda rápida dos comandos personalizados;
