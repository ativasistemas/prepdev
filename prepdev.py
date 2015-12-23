#! /usr/bin/env python3

"""
Configura automaticamente o ambiente de desenvolvimento para os projetos sigma
e sigmalib.
"""

import subprocess
import os
import sys
import configparser
from tempfile import NamedTemporaryFile
import getpass
import apt
import platform

INTERPOLATION_VALUES = {
    "schemas": {
        "cadastro": "cadastro",
        "planejamento": "planejamento"
    },
    "groups": {
        "group_dba": "gadministradores_do_sigma",
        "group_users": "gusuarios_do_sigma"
    }
}


class InvalidPostgresqlVersionError(Exception):
    pass


class GitHubNotConfiguredError(Exception):
    pass


class Prepdev():
    positive_answer = ["s", "S", "y", "Y", "sim", "Sim", "SIM"]
    local_repository = ""
    venv = ".sigmavenv"
    sigma_path = ""
    sigmalib_path = ""
    venv_path = ""
    python = ""
    pip = ""
    pip_timeout = 60
    pip_install = ""
    activate_venv = ""
    home_dir = os.path.expanduser("~")
    ssh_user_dir = os.path.join(home_dir, ".ssh")
    ssh_user_config = os.path.join(ssh_user_dir, "config")
    sigma_ssh_key = os.path.join(ssh_user_dir, "id_rsa_sigma")
    sigmalib_ssh_key = os.path.join(ssh_user_dir, "id_rsa_sigmalib")
    sigma_pub_key = sigma_ssh_key + ".pub"
    sigmalib_pub_key = sigmalib_ssh_key + ".pub"
    bashrc = os.path.join(home_dir, ".bashrc")
    url_sigmalib = "git@sigmalib.github.com:ativasistemas/sigmalib.git"
    url_sigma = "git@sigma.github.com:ativasistemas/sigma.git"
    min_postgres_version = "9.4"
    ini_file = "/tmp/sigma.ini"
    packages = ["libncurses5-dev", "libxml2-dev", "libxslt1-dev",
                "python3-dev", "libpq-dev",
                "postgresql-plpython3-9.4", "python-virtualenv"]
    database_name = ""

    def __init__(self):
        self.base_path = os.path.dirname(os.path.abspath(__file__))
        self.prepdevrc = os.path.join(self.base_path, ".prepdevrc")
        self._create_config_file(self.ini_file)
        # Alguns pacotes mudam de nome quando a arquitetura muda.
        # Aqui cuidamos desse detalhe.
        if platform.architecture()[0] == "64bit":
            self.packages.append("lib32z1-dev")
        else:
            self.packages.append("zlib1g-dev")

        self.database_name = self.config["sigma:database"]["name"]

        # Variáveis que devem ser substituídas nos arquivos sql.
        self.VARIABLES = {"schema_cadastro": INTERPOLATION_VALUES["schemas"]["cadastro"],
                          "schema_planejamento": INTERPOLATION_VALUES["schemas"]["planejamento"],
                          "user_importacao": self.config["sigma:database:users:importacao"]["name"],
                          "group_importacao": self.config["sigma:database:groups:importacao"]["name"]}

        self.DISCONNECT_DB_COMMAND = "\"SELECT pg_terminate_backend(pid) FROM "
        self.DISCONNECT_DB_COMMAND += "pg_stat_get_activity(NULL::integer) WHERE datid=("
        self.DISCONNECT_DB_COMMAND += "SELECT oid from pg_database where datname = '{}');\"".format(self.database_name)

    def write_config(self, name, value, section="default"):
        """
        Grava o parâmetro do prepdev no arquivo de configuração.
        """
        with open(self.prepdevrc, "w") as config_file:
            config = configparser.RawConfigParser()
            config.add_section(section)
            config.set(section, name, value)
            config.write(config_file)

    def read_config(self, name, section="default"):
        """
        Lê o parâmetro do arquivo de configuração do prepdev.
        """
        if os.path.exists(self.prepdevrc) is True:
            config = configparser.RawConfigParser()
            config.read(self.prepdevrc)
            if section in config:
                if name in config[section]:
                    return config[section][name]
        return ""

    def _create_config_file(self, file_):
        # Cria o arquivo de configuração básico para criação do banco.
        with open(file_, "w") as config_file:
            config = configparser.RawConfigParser()
            section = "sigma:database"
            config.add_section(section)
            config.set(section, "host", "127.0.0.1")
            config.set(section, "port", "5432")
            config.set(section, "name", "sigma_db_dev")
            section = "sigma:database:users:sigma_dba"
            config.add_section(section)
            config.set(section, "password", "cfth#z>?3C>CDu-yn5nzgpaPy5NzS\Ce")

            section = "sigma:database:users:importacao"
            config.add_section(section)
            config.set(section, "name", "sigma_importacao")
            config.set(section, "password", "tLfuuGHm98xqj9k8TB3AVA8R")

            section = "sigma:database:groups:importacao"
            config.add_section(section)
            config.set(section, "name", "gimportacao_sigma")

            section = "sigma"
            config.add_section(section)
            config.set(section, "debug", "False")

            section = "server:main"
            config.add_section(section)
            config.set(section, "use", "egg:waitress#main")
            config.set(section, "host", "0.0.0.0")
            config.set(section, "port", "6543")

            section = "app:main"
            config.add_section(section)
            config.set(section, "use", "egg:sigma")

            section = "loggers"
            config.add_section(section)
            config.set(section, "keys", "root, sigma, sigma.core.utils")

            section = "handlers"
            config.add_section(section)
            config.set(section, "keys", "console")

            section = "formatters"
            config.add_section(section)
            config.set(section, "keys", "generic, color")

            section = "logger_root"
            config.add_section(section)
            config.set(section, "level", "INFO")
            config.set(section, "handlers", "console")

            section = "logger_sigma"
            config.add_section(section)
            config.set(section, "level", "INFO")
            config.set(section, "qualname", "sigma")
            config.set(section, "handlers", "")

            section = "logger_sigma.core.utils"
            config.add_section(section)
            config.set(section, "level", "INFO")
            config.set(section, "qualname", "sigma.core.utils")
            config.set(section, "handlers", "")

            section = "handler_console"
            config.add_section(section)
            config.set(section, "class", "StreamHandler")
            config.set(section, "args", "(sys.stderr,)")
            config.set(section, "level", "NOTSET")
            config.set(section, "formatter", "color")

            section = "formatter_generic"
            config.add_section(section)
            config.set(section, "format", "%(asctime)s %(levelname)-5.5s [%(name)s][%(threadName)s] %(message)s")

            section = "formatter_color"
            config.add_section(section)
            config.set(section, "class", "colorlog.ColoredFormatter")
            config.set(section, "format", "%(asctime)s %(log_color)s%(levelname)-5.5s%(reset)s %(bg_blue)s[%(name)s]%(reset)s %(message)s")
            config.set(section, "datefmt", "%Y/%m/%d %H:%M:%S")

            config.write(config_file)

        self.config = configparser.ConfigParser()
        self.config.read(file_)

    def so_dependencies(self):
        """
        Instala as dependências do S.O..
        """
        print_info("Instalando dependências do S.O...")
        cmd = "sudo apt-get install -f -y"
        for pkg in self.packages:
            cmd += " {}".format(pkg)
        call(cmd)

    def create_venv(self):
        """
        Cria o amebiente virtual.
        """
        print_info("Criando ambiente virtual...")
        if not os.path.exists(self.venv_path):
            cmd = "virtualenv {} -p python3".format(self.venv_path)
            call(cmd)

    def set_instalation_path(self):
        """
        Solicita ao usuário o diretório onde o repositório será criado.
        """
        section = "repository_path"
        default_dir = os.path.expanduser("~/repository")
        repository_path = self.read_config("repository_path")
        default_dir = repository_path or default_dir

        msg = Colors.WARNING
        msg += "Em qual diretório os códigos devem ficar? "
        msg += Colors.BLUE + "({}): ".format(default_dir) + Colors.ENDC
        answer = input(msg)

        if not answer:
            answer = default_dir

        if "~" in answer:
            answer = os.path.expanduser(answer)

        self.write_config(section, answer)

        self.local_repository = answer
        self.sigma_path = os.path.join(self.local_repository, "sigma")
        self.sigmalib_path = os.path.join(self.local_repository, "sigmalib")
        self.venv_path = os.path.join(self.local_repository, self.venv)
        self.python = "{}/bin/python".format(self.venv_path)
        self.pip = "{}/bin/pip".format(self.venv_path)
        self.pip_install = "{} install --timeout {} {{}}"
        self.pip_install = self.pip_install.format(self.pip, self.pip_timeout)
        self.activate_venv = "source {}/bin/activate;".format(self.venv_path)
        os.makedirs(self.local_repository, exist_ok=True)

    def check_postgresql_version(self):
        """
        Verifica se a versão do postgresql é válida.
        """
        cmd = ["bash", "-c"]
        cmd.append("psql --version")
        # Se o banco existir o script retorna "1".
        ret = subprocess.check_output(cmd).decode("utf-8")
        ret = ret.replace("psql", "").replace("(PostgreSQL)", "")
        version = ret.replace("\n", "").strip()
        major = version.split(".")[0]
        minor = version.split(".")[1]
        major = int(major) >= int(self.min_postgres_version.split(".")[0])
        minor = int(minor) >= int(self.min_postgres_version.split(".")[1])
        if all((major, minor)) is False:
            msg = "Instale o postgresql {} ou superior. Sua versão é: {}"
            msg = msg.format(self.min_postgres_version, version)
            raise InvalidPostgresqlVersionError(msg)

    def search_dependencies(self):
        """
        Verifica se as dependências estão disponíveis para instalação.
        """
        missing_packages = []
        print_info("Verificando disponibilidade de pacotes...")
        cache = apt.cache.Cache()
        # cache.update() # Para usar este comando é preciso acesso root.
        for pkg in self.packages:
            try:
                cache[pkg]
            except KeyError:
                missing_packages.append(pkg)
        if missing_packages:
            packages = ", ".join(missing_packages)
            msg = "ATENÇÃO: O pacote(s) " + Colors.BLUE + "{}" + Colors.WARNING
            msg += " não está(ão) disponível(is) em seu sistema."
            msg = msg.format(packages)
            print_warning(msg)
            msg = "Verifique seus repositórios e atualize-o com:"
            msg += " sudo apt-get update"
            print_warning(msg)
            sys.exit(-1)

    def create_ssh_keys(self):
        """
        Cria(caso necessário) o par de chaves do sigma e sigmalib.
        """
        print_info("Verificando par de chaves...")
        keygen_cmd = 'ssh-keygen -t rsa -N ""'

        keygen_cmd_sigma = keygen_cmd
        keygen_cmd_sigma += ' -f {}'.format(self.sigma_ssh_key)

        keygen_cmd_sigmalib = keygen_cmd
        keygen_cmd_sigmalib += ' -f {}'.format(self.sigmalib_ssh_key)

        if os.path.exists(self.sigma_pub_key) is False:
            print_info("Criando par de chaves do sigma.")
            call(keygen_cmd_sigma)

        if os.path.exists(self.sigmalib_pub_key) is False:
            print_info("Criando par de chaves do sigmalib.")
            call(keygen_cmd_sigmalib)

    def set_ssh_config_permissions(self):
        """
        Ajusta as permissões do arquivo de configuração do ssh.

        Caso as permissões não estejam corretas o ssh impede qualquer tipo de
        conexão por questões de segurança.
        """
        msg = "Ajustando premissões dos arquivos do ssh"
        print_info(msg)

        cmd = "chmod u=rw,g-rwx,o-rwx {}"

        ssh_config = cmd.format(self.ssh_user_config)
        call(ssh_config)

        sigma_keys = cmd.format(self.sigma_ssh_key + " " + self.sigma_pub_key)
        call(sigma_keys)

        sigmalib_keys = self.sigmalib_ssh_key + " " + self.sigmalib_pub_key
        sigmalib_keys = cmd.format(sigmalib_keys)
        call(sigmalib_keys)

    def create_ssh_config(self):
        """
        Cria(caso necessário) a configuração do ssh para os repositórios.
        """
        ssh_config = """# Criado pelo comando prepdev do sigma.
    Host {}
        HostName github.com
        User git
        IdentityFile {}
        StrictHostKeyChecking no
    """
        if os.path.exists(self.ssh_user_config) is False:
            msg = "Criando arquivo de configuração do ssh..."
            print_info(msg)
            with open(self.ssh_user_config, "w+") as f:
                msg = "Configurando ssh para o sigma."
                print_info(msg)
                f.write(ssh_config.format("sigma.github.com",
                                          self.sigma_ssh_key))
                msg = "Configurando ssh para o sigmalib."
                print_info(msg)
                f.write(ssh_config.format("sigmalib.github.com",
                                          self.sigmalib_ssh_key))
        else:
            msg = "Verificando arquivo de configuração do ssh..."
            print_info(msg)
            with open(self.ssh_user_config, "r+") as f:
                if "Host sigma.github.com" not in f.read():
                    msg = "Configurando ssh para o sigma."
                    print_info(msg)
                    f.write("# Criado pelo comando prepdev do sigma.\n")
                    f.write(ssh_config.format("sigma.github.com",
                                              self.sigma_ssh_key))
                f.seek(0)
                if "Host sigmalib.github.com" not in f.read():
                    msg = "Configurando ssh para o sigmalib."
                    print_info(msg)
                    f.write("# Criado pelo comando prepdev do sigma.\n")
                    f.write(ssh_config.format("sigmalib.github.com",
                                              self.sigmalib_ssh_key))
        self.set_ssh_config_permissions()

    def github_sigma_configured(self):
        """
        Verifica se o github foi configurado com a chave do sigma.
        """
        ssh_sigma = "ssh -T git@sigma.github.com"
        output = ""

        with subprocess.Popen(ssh_sigma,
                              shell=True,
                              bufsize=255,
                              stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,
                              close_fds=True) as ssh:
            output = str(ssh.stderr.readlines()[0])

        return "ativasistemas/sigma" in output


    def github_sigmalib_configured(self):
        """
        Verifica se o github foi configurado com a chave do sigmalib.
        """
        ssh_sigmalib = "ssh -T git@sigmalib.github.com"

        with subprocess.Popen(ssh_sigmalib,
                              shell=True,
                              bufsize=255,
                              stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,
                              close_fds=True) as ssh:
            output = str(ssh.stderr.readlines()[0])

        return "ativasistemas/sigmalib" in output

    def github_configured(self):
        configured = True

        if self.github_sigma_configured() is False:
            msg = "Configure o repositório do sigma para permitir acesso "
            msg += "com a chave:"
            print_warning(msg)
            msg = " chave sigma(copie todo conteúdo dentro deste bloco) "
            msg = "{:#^80}".format(msg)
            print_blue(msg)
            call("cat {}".format(self.sigma_pub_key), True)
            msg = "{:#^80}".format("(fim do bloco)")
            print_blue(msg)
            configured = False

        if self.github_sigmalib_configured() is False:
            msg = "Configure o repositório do sigmalib para permitir acesso "
            msg += "com a chave:"
            print_warning(msg)
            msg = " chave sigmalib(copie todo conteúdo dentro deste bloco) "
            msg = "{:#^80}".format(msg)
            print_blue(msg)
            call("cat {}".format(self.sigmalib_pub_key), True)
            msg = "{:#^80}".format("(fim do bloco)")
            print_blue(msg)
            configured = False

        if configured is False:
            msg = "Acesse o github e permita o acesso para a(s) chave(s) acima."
            raise GitHubNotConfiguredError(msg)

    def clone_sigmalib(self):
        msg = "Clonando sigmalib..."
        print_info(msg)
        cmd = "git clone {} {}".format(self.url_sigmalib,
                                       self.sigmalib_path)
        call(cmd)

    def clone_sigma(self):
        msg = "Clonando sigma..."
        print_info(msg)
        cmd = "git clone {} {}".format(self.url_sigma, self.sigma_path)
        call(cmd)

    def update_packages(self):
        print_info("Atualizando pip...")
        cmd = self.pip_install.format("-U pip")
        call(cmd)

        print_info("Atualizando setuptools...")
        cmd = self.pip_install.format("-U setuptools")
        call(cmd)

    def setup_develop(self):
        """
        Prepara o ambiente para rodar o sigma.
        """
        print_info("Preparando virtualenv para ambiente de desenvolvimento...")
        # sigma
        cmd = "cd {}; {} setup.py develop".format(self.sigma_path, self.python)
        call(cmd)

        # Dependências para testes e ferramentas de auxílio ao desenvolvimento.
        cmd = "cd {}; {} install -e .[test,dev]".format(self.sigma_path,
                                                        self.pip)
        call(cmd)

        # sigmalib
        cmd = "cd {}; {} setup.py develop".format(self.sigmalib_path,
                                                  self.python)
        call(cmd)

    def install_sigmalib(self):
        msg = "Instalando sigmalib..."
        print_info(msg)

        # jscrambler
        url = "git+ssh://git@github.com/gjcarneiro/python-jscrambler.git"
        url += "#egg=jscrambler-2.0b1"
        cmd = self.pip_install.format(url)
        call(cmd)

        # sigmalib
        url = "git+ssh://git@sigmalib.github.com/ativasistemas/sigmalib.git"
        url += "#egg=sigmalib-0.9.2"
        cmd = self.pip_install.format(url)
        call(cmd)

    def close_connections(self):
        print_info("Derrubando conexões com o banco de dados.")
        cmd = "psql -h localhost -U postgres -c {}"
        cmd += cmd.format(self.DISCONNECT_DB_COMMAND)
        call(cmd)

    def prepare_database(self):
        if self._database_exists() is True:
            msg = "O banco de dados " + Colors.BOLD + "{}"
            msg += Colors.ENDC + Colors.WARNING + " já existe! Posso "
            msg += "excluí-lo e criá-lo novamente?(s/" + Colors.BOLD + "[N]"
            msg += Colors.ENDC + Colors.WARNING + ")"
            msg = msg.format(self.database_name)
            answer = input(Colors.WARNING + msg + Colors.ENDC)
            if answer in self.positive_answer:
                self._drop_database()
                self._drop_user("sigma_dba")
                self._drop_user("sigma_importacao")
                self._drop_user("u03491509408")
                self._drop_user("u03455624456")
                self._drop_user("u03895607401")
                self._drop_group("gadministradores_do_sigma")
                self._drop_group("gusuarios_do_sigma")
                self._drop_group("gimportacao_sigma")
        else:
            # Precisamos garantir que os usuários abaixo não existam.
            self._drop_user("sigma_dba")
            self._drop_user("sigma_importacao")
            self._drop_user("u03491509408")
            self._drop_user("u03455624456")
            self._drop_user("u03895607401")
            self._drop_group("gadministradores_do_sigma")
            self._drop_group("gusuarios_do_sigma")
            self._drop_group("gimportacao_sigma")
        self._generate_environment()
        self._copy_environment()
        self._set_postgres_permissions()
        self._restart_database()
        self._set_postgres_password()

    def _restart_database(self):
        print_info("Reiniciando banco de dados...")
        cmd = "sudo service postgresql restart"
        call(cmd)

    def _database_exists(self):
        cmd = ["bash", "-c"]
        cmd_psql = "psql -h localhost -U postgres -lqt | cut -d \| -f 1 | "
        cmd_psql += "grep -w {} | wc -l"
        cmd_psql = cmd_psql.format(self.database_name)
        cmd.append(cmd_psql)
        # Se o banco existir o script retorna "1".
        return "1" in str(subprocess.check_output(cmd))

    def _drop_database(self):
        print_info("Excluindo banco de dados...")
        cmd = "dropdb -h localhost -U postgres {}".format(self.database_name)
        call(cmd)

    def _drop_user(self, username):
        username = username.strip()
        msg = "Excluindo usuário " + Colors.BOLD + Colors.BLUE + "{}"
        msg = msg.format(username)
        print_info(msg)
        cmd = "dropuser -h localhost -U postgres --if-exists {}"
        cmd = cmd.format(username)
        call(cmd)

    def _drop_group(self, groupname):
        msg = "Excluindo grupo " + Colors.BOLD + Colors.BLUE + "{}"
        msg = msg.format(groupname)
        print_info(msg)
        cmd = "psql -h localhost -U postgres -c \"drop group if exists {}\""
        cmd = cmd.format(groupname)
        call(cmd)

    def _generate_environment(self):
        print_info("Gerando arquivo environment...")
        cmd = "source {}/bin/activate; sigma_update_postgres_env"
        cmd = cmd.format(self.venv_path)
        call(cmd)

    def _copy_environment(self):
        print_info("Copiando environment para o servidor de banco de dados...")
        cmd = "sudo cp -f /tmp/environment /etc/postgresql/9.4/main/"
        call(cmd)

    def _set_postgres_permissions(self):
        """
        Adiciona o usuário postgres ao grupo do usuário atualmente logado.

        Como o ambiente virtual é criado para o usuário logado, o postgres
        precisa ser colocado no grupo deste usuário. Caso contrário ele não
        conseguirá ter acesso as bibliotecas do virtualenv.
        """
        user = getpass.getuser()
        cmd = "sudo usermod -G {} -a postgres".format(user)
        call(cmd)

    def _set_postgres_password(self):
        print_info("Configurando senha do usuário postgres...")
        cmd = "psql -h localhost -U postgres -c \"alter user postgres with "
        cmd += "encrypted password '123Abcde'\""
        call(cmd)

    def run_migrations(self):
        print_info("Executando migrações...")
        if self._database_exists() is False:
            # cmd = self.activate_venv
            cmd = "cd {}; {} sigma/migrations/sprint_1.py {};"
            cmd = cmd.format(self.sigma_path, self.python, self.ini_file)
            call(cmd)
        cmd = self.activate_venv
        cmd += "cd {}; sigma_run_migrations -b {}".format(self.sigma_path,
                                                          self.ini_file)
        call(cmd)

    def populate_db(self):
        msg = "Deseja carregar os dados de desenvolvimento no banco de dados? "
        msg += "([" + Colors.BOLD + "S]" + Colors.ENDC + Colors.WARNING + "/n)"
        msg += Colors.ENDC
        answer = input(Colors.WARNING + msg + Colors.ENDC)
        if answer == "":
            answer = "s"
        if answer in self.positive_answer:
            sqls = os.path.join(self.sigma_path, "sigma", "sql", "dev")
            for files in reversed(list(os.walk(sqls, topdown=False))):
                for sql in files[-1]:
                    if ".sql" in sql[-4:]:
                        sql_file = files[0] + "/" + sql
                        sql_file = self._pre_process_sql(sql_file)
                        cmd = "psql -h localhost -U postgres -d {} -f {}"
                        cmd = cmd.format(self.database_name, sql_file)
                        call(cmd)

    def _pre_process_sql(self, filename):
        """
        Faz o pré-processamento do arquivo sql.

        Durante o pré-processamento as {variáveis} informadas no arquivo são
        substituídas.

        Retorna o path do arquivo pré-processado.
        """
        sqls = None
        with open(filename, "r") as sql_file:
            sqls = sql_file.read()
            sqls = sqls.format(**self.VARIABLES)
        sql_temp = NamedTemporaryFile(delete=False)
        sql_temp.write(bytes(sqls, 'utf-8'))
        sql_temp.seek(0)
        return sql_temp.name

    def make_commands(self):
        print_info("Criando comandos personalizados...")
        comment = "\n# Alias criado pelo comando prepdev do sigma.\n"
        sigma = "alias sigma='{} cd {}'"
        sigma = sigma.format(self.activate_venv, self.sigma_path)
        sigmalib = "alias sigmalib='{} cd {}'"
        sigmalib = sigmalib.format(self.activate_venv, self.sigmalib_path)
        prepdev = "alias prepdev='{}/prepdev.py'".format(self.base_path)
        if os.path.exists(self.bashrc) is True:
            with open(self.bashrc, "r+") as f:
                # Se o alias ainda não foi criado. Crie-o.
                if sigma not in f.read():
                    f.write(comment)
                    f.write(sigma)
                    f.write("\n")
                f.seek(0)
                if sigmalib not in f.read():
                    f.write(sigmalib)
                    f.write("\n")
                f.seek(0)
                if prepdev not in f.read():
                    f.write(prepdev)
                    f.write("\n")
        else:
            with open(self.bashrc, "w") as f:
                f.write(comment)
                f.write(sigma)
                f.write("\n")
                f.write(sigmalib)
                f.write("\n")
                f.write(prepdev)
                f.write("\n")

    def finish(self):
        print_format = "{:^80}"
        msg = "██████╗██╗ ██████╗ ███╗   ███╗ █████╗"
        print_blue(print_format.format(msg))
        msg = "██╔════╝██║██╔════╝ ████╗ ████║██╔══██╗"
        print_blue(print_format.format(msg))
        msg = "███████╗██║██║  ███╗██╔████╔██║███████║"
        print_blue(print_format.format(msg))
        msg = "╚════██║██║██║   ██║██║╚██╔╝██║██╔══██║"
        print_blue(print_format.format(msg))
        msg = "███████║██║╚██████╔╝██║ ╚═╝ ██║██║  ██║"
        print_blue(print_format.format(msg))
        msg = "╚══════╝╚═╝ ╚═════╝ ╚═╝     ╚═╝╚═╝  ╚═╝"
        print_blue(print_format.format(msg))

    def print_help(self):
        cmd, cmd_help = "sigma_server", "Executa o servidor."
        print_warning(format_cmd_print(cmd, cmd_help))
        cmd, cmd_help = "sigma_run_migrations", "Faz upgrade do banco de dados."
        print_warning(format_cmd_print(cmd, cmd_help))
        cmd, cmd_help = "sigma_run_tests", "Executa os testes do sistema."
        print_warning(format_cmd_print(cmd, cmd_help))
        cmd, cmd_help = "sigma_update_postgres_env", "Gera um novo arquivo de "
        cmd_help += "ambiente para o postgresql."
        print_warning(format_cmd_print(cmd, cmd_help))
        cmd, cmd_help = "sigma_update_settings", "Gera os arquivos development."
        cmd_help += "ini e production.ini. Usa sigma.ini como base."
        print_warning(format_cmd_print(cmd, cmd_help))
        cmd, cmd_help = "sigma_update_static", "Processa os arquivos estáticos "
        cmd_help += "da pasta static_full e os copia para a pasta static."
        print_warning(format_cmd_print(cmd, cmd_help))
        cmd, cmd_help = "sigma", "Ativa o ambiente virtual do sigma e muda "
        cmd_help += "para o diretório do projeto."
        print_warning(format_cmd_print(cmd, cmd_help))
        msg = "Para entrar manualmente no ambiente virtual, use o comando:"
        print_warning(msg, end=" ")
        msg = "source {}/bin/activate".format(self.venv)
        print(Colors.BLUE + Colors.BOLD + msg + Colors.ENDC)
        msg = "Caso algum dos comandos acima não seja reconhecido, feche esse "
        msg += "terminal e abra novamente."
        print_warning(Colors.BOLD + msg)

    def postgres_warning(self):
        print("{:#^80}".format("Atenção"))
        print_warning("As seguintes linhas devem estar presentes no pg_hba.conf" + Colors.BOLD + "(na mesma ordem)" + Colors.ENDC + Colors.WARNING + ":")
        print(Colors.BLUE + "host    all             postgres        127.0.0.1/32            trust" + Colors.ENDC)
        print(Colors.BLUE + "host    all             all             127.0.0.1/32            md5" + Colors.ENDC)

    def important_message(self):
        """
        Mensagens importantes.
        """
        msg = Colors.WARNING
        msg += "Você já configurou o postgresql para aceitar conexões do localhost"
        msg += "(127.0.0.1) como confiáveis? (s/" + Colors.BOLD + "[N]"
        msg += Colors.ENDC + Colors.WARNING + ")" + Colors.ENDC
        answer = input(msg)
        if answer == "":
            answer = "n"
        if answer in self.positive_answer:
            return True
        else:
            return False

    def run(self):
        if self.important_message() is True:
            self.set_instalation_path()
            self.check_postgresql_version()
            self.create_venv()
            self.search_dependencies()
            self.create_ssh_keys()
            self.create_ssh_config()
            self.github_configured()
            self.so_dependencies()
            self.clone_sigma()
            self.clone_sigmalib()
            self.update_packages()
            self.setup_develop()
            self.install_sigmalib()
            self.close_connections()
            self.prepare_database()
            self.run_migrations()
            self.populate_db()
            self.make_commands()
            self.finish()
            self.print_help()
        else:
            msg = "Configure o postgresql para aceitar conexões confiáveis "
            msg += "vindas de localhost(" + Colors.BLUE + "/etc/postgresql/"
            msg += "<version>/pg_hba.conf" + Colors.GREEN + ")."
            print_warning(msg)
            self.postgres_warning()

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_info(msg, end="\n"):
    print(Colors.GREEN + msg + Colors.ENDC, end=end)


def print_warning(msg, end="\n"):
    print(Colors.WARNING + msg + Colors.ENDC, end=end)


def print_blue(msg, end="\n"):
    print(Colors.BLUE + msg + Colors.ENDC, end=end)


def call(command, print_output=False):
    cmd = ["bash", "-c"]
    cmd.append(command)
    if print_output is False:
        with open(os.devnull, 'w') as fnull:
            subprocess.call(cmd, stdout=fnull, stderr=subprocess.STDOUT)
    else:
        subprocess.call(cmd, stderr=subprocess.STDOUT)

def format_cmd_print(cmd, help):
    msg = Colors.BLUE + Colors.BOLD + cmd + Colors.ENDC + Colors.GREEN
    msg += " => " + help
    return msg

if __name__ == "__main__":
    instance = Prepdev()
    try:
        instance.run()
    except Exception as exc:
        print_warning(exc.args[0])
