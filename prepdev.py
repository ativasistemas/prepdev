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
    POSITIVE_ANSWER = ["s", "S", "y", "Y", "sim", "Sim", "SIM"]
    LOCAL_REPOSITORY = ""
    VENV = ".sigmavenv"
    SIGMA_DIR = ""
    SIGMALIB_DIR = ""
    VENV_DIR = ""
    PYTHON = ""
    PIP = ""
    PIP_TIMEOUT = 60
    PIP_INSTALL = ""
    ACTIVATE_VENV = ""
    HOME_DIR = os.path.expanduser("~")
    SSH_DIR = os.path.join(HOME_DIR, ".ssh")
    SSH_CONFIG = os.path.join(SSH_DIR, "config")
    SIGMA_SSH_KEY = os.path.join(SSH_DIR, "id_rsa_sigma")
    SIGMALIB_SSH_KEY = os.path.join(SSH_DIR, "id_rsa_sigmalib")
    SIGMA_PUB_KEY = SIGMA_SSH_KEY + ".pub"
    SIGMALIB_PUB_KEY = SIGMALIB_SSH_KEY + ".pub"
    BASHRC = os.path.join(HOME_DIR, ".bashrc")
    REPO_URL_SIGMALIB = "git@sigmalib.github.com:ativasistemas/sigmalib.git"
    REPO_URL_SIGMA = "git@sigma.github.com:ativasistemas/sigma.git"
    MIN_POSTGRES_VERSION = "9.4"
    PACKAGES = ["libncurses5-dev", "libxml2-dev", "libxslt1-dev",
                "python3-dev", "libpq-dev",
                "postgresql-plpython3-9.4", "python-virtualenv"]
    DATABASE_NAME = ""

    def __init__(self):
        self._create_config_file("/tmp/sigma.ini")
        # Alguns pacotes mudam de nome quando a arquitetura muda.
        # Aqui cuidamos desse detalhe.
        if platform.architecture()[0] == "64bit":
            self.PACKAGES.append("lib32z1-dev")
        else:
            self.PACKAGES.append("zlib1g-dev")

        self.DATABASE_NAME = self.config["sigma:database"]["name"]

        # Variáveis que devem ser substituídas nos arquivos sql.
        self.VARIABLES = {"schema_cadastro": INTERPOLATION_VALUES["schemas"]["cadastro"],
                     "schema_planejamento": INTERPOLATION_VALUES["schemas"]["planejamento"],
                     "user_importacao": self.config["sigma:database:users:importacao"]["name"],
                     "group_importacao": self.config["sigma:database:groups:importacao"]["name"]}

        self.DISCONNECT_DB_COMMAND = "\"SELECT pg_terminate_backend(pid) FROM "
        self.DISCONNECT_DB_COMMAND += "pg_stat_get_activity(NULL::integer) WHERE datid=("
        self.DISCONNECT_DB_COMMAND += "SELECT oid from pg_database where datname = '{}');\"".format(self.DATABASE_NAME)


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
        for pkg in self.PACKAGES:
            cmd += " {}".format(pkg)
        call(cmd)

    def create_venv(self):
        """
        Cria o amebiente virtual.
        """
        print_info("Criando ambiente virtual...")
        if not os.path.exists(self.VENV_DIR):
            cmd = "virtualenv {} -p python3".format(self.VENV_DIR)
            call(cmd, True)

    def set_instalation_path(self):
        """
        Solicita ao usuário o diretório onde o repositório será criado.
        """
        default_dir = "~/repository"
        msg = Colors.WARNING
        msg += "Em qual diretório os códigos devem ficar? "
        msg += Colors.BLUE + "({}): ".format(default_dir) + Colors.ENDC
        answer = input(msg)

        if not answer:
            answer = default_dir

        if "~" in answer:
            answer = os.path.expanduser(answer)

        self.LOCAL_REPOSITORY = answer
        self.SIGMA_DIR = os.path.join(self.LOCAL_REPOSITORY, "sigma")
        self.SIGMALIB_DIR = os.path.join(self.LOCAL_REPOSITORY, "sigmalib")
        self.VENV_DIR = os.path.join(self.LOCAL_REPOSITORY, self.VENV)
        self.PYTHON = "{}/bin/python".format(self.VENV_DIR)
        self.PIP = "{}/bin/pip".format(self.VENV_DIR)
        self.PIP_INSTALL = "{} install --timeout {} {{}}".format(self.PIP,self.PIP_TIMEOUT)
        self.ACTIVATE_VENV = "source {}/bin/activate;".format(self.VENV_DIR)
        os.makedirs(self.LOCAL_REPOSITORY, exist_ok=True)


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

        if all((int(major) >= int(self.MIN_POSTGRES_VERSION.split(".")[0]),
                int(minor) >= int(self.MIN_POSTGRES_VERSION.split(".")[1]))) is False:
            msg = "Instale o postgresql {} ou superior. Sua versão é: {}"
            msg = msg.format(self.MIN_POSTGRES_VERSION, version)
            raise InvalidPostgresqlVersionError(msg)

    def search_dependencies(self):
        """
        Verifica se as dependências estão disponíveis para instalação.
        """
        missing_packages = []
        print_info("Verificando disponibilidade de pacotes...")
        cache = apt.cache.Cache()
        # cache.update() # Para usar este comando é preciso acesso root.
        for pkg in self.PACKAGES:
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
        keygen_cmd_sigma += ' -f {}'.format(self.SIGMA_SSH_KEY)

        keygen_cmd_sigmalib = keygen_cmd
        keygen_cmd_sigmalib += ' -f {}'.format(self.SIGMALIB_SSH_KEY)

        if os.path.exists(self.SIGMA_PUB_KEY) is False:
            print_info("Criando par de chaves do sigma.")
            call(keygen_cmd_sigma)

        if os.path.exists(self.SIGMALIB_PUB_KEY) is False:
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

        ssh_config = cmd.format(self.SSH_CONFIG)
        call(ssh_config)

        sigma_keys = cmd.format(self.SIGMA_SSH_KEY + " " + self.SIGMA_PUB_KEY)
        call(sigma_keys)

        sigmalib_keys = cmd.format(self.SIGMALIB_SSH_KEY + " " + self.SIGMALIB_PUB_KEY)
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
        if os.path.exists(self.SSH_CONFIG) is False:
            msg = "Criando arquivo de configuração do ssh..."
            print_info(msg)
            with open(self.SSH_CONFIG, "w+") as f:
                msg = "Configurando ssh para o sigma."
                print_info(msg)
                f.write(ssh_config.format("sigma.github.com", self.SIGMA_SSH_KEY))
                msg = "Configurando ssh para o sigmalib."
                print_info(msg)
                f.write(ssh_config.format("sigmalib.github.com", self.SIGMALIB_SSH_KEY))
        else:
            msg = "Verificando arquivo de configuração do ssh..."
            print_info(msg)
            with open(self.SSH_CONFIG, "r+") as f:
                if "Host sigma.github.com" not in f.read():
                    msg = "Configurando ssh para o sigma."
                    print_info(msg)
                    f.write("# Criado pelo comando prepdev do sigma.\n")
                    f.write(ssh_config.format("sigma.github.com", self.SIGMA_SSH_KEY))
                f.seek(0)
                if "Host sigmalib.github.com" not in f.read():
                    msg = "Configurando ssh para o sigmalib."
                    print_info(msg)
                    f.write("# Criado pelo comando prepdev do sigma.\n")
                    f.write(ssh_config.format("sigmalib.github.com", self.SIGMALIB_SSH_KEY))
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
            msg = "Configure o repositório do sigma para permitir acesso com a chave:"
            print_warning(msg)
            msg = " chave sigma(copie todo conteúdo dentro deste bloco) "
            msg = "{:#^80}".format(msg)
            print_blue(msg)
            call("cat {}".format(self.SIGMA_PUB_KEY), True)
            msg = "{:#^80}".format("(fim do bloco)")
            print_blue(msg)
            configured = False

        if self.github_sigmalib_configured() is False:
            msg = "Configure o repositório do sigmalib para permitir acesso com a chave:"
            print_warning(msg)
            msg = " chave sigmalib(copie todo conteúdo dentro deste bloco) "
            msg = "{:#^80}".format(msg)
            print_blue(msg)
            call("cat {}".format(self.SIGMALIB_PUB_KEY), True)
            msg = "{:#^80}".format("(fim do bloco)")
            print_blue(msg)
            configured = False

        if configured is False:
            msg = "Acesse o github e permita o acesso para a(s) chave(s) acima."
            raise GitHubNotConfiguredError(msg)

    def clone_sigmalib(self):
        msg = "Clonando sigmalib..."
        print_info(msg)
        cmd = "git clone {} {}".format(self.REPO_URL_SIGMALIB,
                                       self.SIGMALIB_DIR)
        call(cmd)

    def clone_sigma(self):
        msg = "Clonando sigma..."
        print_info(msg)
        cmd = "git clone {} {}".format(self.REPO_URL_SIGMA, self.SIGMA_DIR)
        call(cmd)

    def update_packages(self):
        print_info("Atualizando pip...")
        cmd = "{}".format(self.PIP_INSTALL.format("-U pip"))
        call(cmd)

        print_info("Atualizando setuptools...")
        cmd = "{}".format(self.PIP_INSTALL.format("-U setuptools"))
        call(cmd)

    def setup_develop(self):
        """
        Prepara o ambiente para rodar o sigma.
        """
        print_info("Preparando virtualenv para ambiente de desenvolvimento...")
        # sigma
        cmd = "cd {}; {} setup.py develop".format(self.SIGMA_DIR, self.PYTHON)
        call(cmd)

        # Dependências para testes e ferramentas de auxílio ao desenvolvimento.
        cmd = "cd {}; {} install -e .[test,dev]".format(self.SIGMA_DIR,
                                                        self.PIP)
        call(cmd)

        # sigmalib
        cmd = "cd {}; {} setup.py develop".format(self.SIGMALIB_DIR, self.PYTHON)
        call(cmd)

    def install_sigmalib(self):
        msg = "Instalando sigmalib..."
        print_info(msg)

        # jscrambler
        url = "git+ssh://git@github.com/gjcarneiro/python-jscrambler.git"
        url += "#egg=jscrambler-2.0b1"
        cmd = self.PIP_INSTALL.format(url)
        call(cmd)

        # sigmalib
        url = "git+ssh://git@sigmalib.github.com/ativasistemas/sigmalib.git"
        url += "#egg=sigmalib-0.9.2"
        cmd = self.PIP_INSTALL.format(url)
        call(cmd)

    def close_connections(self):
        print_info("Derrubando conexões com o banco de dados.")
        cmd = "psql -h localhost -U postgres -c {}"
        cmd += cmd.format(self.DISCONNECT_DB_COMMAND)
        call(cmd)

    def run(self):
        self.set_instalation_path()
        self.check_postgresql_version()
        self.so_dependencies()
        self.create_venv()
        self.search_dependencies()
        self.create_ssh_keys()
        self.create_ssh_config()
        self.github_configured()
        self.clone_sigma()
        self.clone_sigmalib()
        self.update_packages()
        self.setup_develop()
        self.install_sigmalib()
        self.close_connections()

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


def _generate_environment():
    print_info("Gerando arquivo environment...")
    cmd = "source {}/bin/activate; sigma_update_postgres_env".format(VENV_DIR)
    call(cmd)


def _copy_environment():
    print_info("Copiando environment para o servidor de banco de dados...")
    cmd = "sudo cp -f /tmp/environment /etc/postgresql/9.4/main/"
    call(cmd)


def _restart_database():
    print_info("Reiniciando banco de dados...")
    cmd = "sudo service postgresql restart"
    call(cmd)


def _database_exists():
    cmd = ["bash", "-c"]
    cmd.append("psql -h localhost -U postgres -lqt | cut -d \| -f 1 | grep -w {} | wc -l".format(DATABASE_NAME))
    # Se o banco existir o script retorna "1".
    return "1" in str(subprocess.check_output(cmd))


def _drop_database():
    print_info("Excluindo banco de dados...")
    cmd = "dropdb -h localhost -U postgres {}".format(DATABASE_NAME)
    call(cmd)


def _drop_user(username):
    username = username.strip()
    print_info("Excluindo usuário " + Colors.BOLD + Colors.BLUE + "{}".format(username))
    cmd = "dropuser -h localhost -U postgres --if-exists {}".format(username)
    call(cmd)


def _drop_group(groupname):
    print_info("Excluindo grupo " + Colors.BOLD + Colors.BLUE + "{}".format(groupname))
    cmd = "psql -h localhost -U postgres -c \"drop group if exists {}\"".format(groupname)
    call(cmd)


def _set_postgres_password():
    print_info("Configurando senha do usuário postgres...")
    cmd = "psql -h localhost -U postgres -c \"alter user postgres with encrypted password '123Abcde'\""
    call(cmd)


def _set_postgres_permissions():
    """
    Adiciona o usuário postgres ao grupo do usuário atualmente logado.

    Como o ambiente virtual é criado para o usuário logado, o postgres precisa
    ser colocado no grupo deste usuário, caso contrário ele não conseguirá ter
    acesso as bibliotecas do virtualenv.
    """
    user = getpass.getuser()
    cmd = "sudo usermod -G {} -a postgres".format(user)
    call(cmd)


def prepare_database():
    if _database_exists() is True:
        msg = "O banco de dados " + Colors.BOLD + "{}".format(DATABASE_NAME)
        msg += Colors.ENDC + Colors.WARNING + " já existe! Posso "
        msg += "excluí-lo e criá-lo novamente?(s/" + Colors.BOLD + "[N]"
        msg += Colors.ENDC + Colors.WARNING + ")"
        answer = input(Colors.WARNING + msg + Colors.ENDC)
        if answer in POSITIVE_ANSWER:
            _drop_database()
            _drop_user("sigma_dba")
            _drop_user("sigma_importacao")
            _drop_user("u03491509408")
            _drop_user("u03455624456")
            _drop_user("u03895607401")
            _drop_group("gadministradores_do_sigma")
            _drop_group("gusuarios_do_sigma")
            _drop_group("gimportacao_sigma")
    else:
        # Precisamos garantir que os usuários abaixo não existam.
        _drop_user("sigma_dba")
        _drop_user("sigma_importacao")
        _drop_user("u03491509408")
        _drop_user("u03455624456")
        _drop_user("u03895607401")
        _drop_group("gadministradores_do_sigma")
        _drop_group("gusuarios_do_sigma")
        _drop_group("gimportacao_sigma")
    _generate_environment()
    _copy_environment()
    _set_postgres_permissions()
    _restart_database()
    _set_postgres_password()


def finish():
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


def format_cmd_print(cmd, help):
    msg = Colors.BLUE + Colors.BOLD + cmd + Colors.ENDC + Colors.GREEN
    msg += " => " + help
    return msg


def print_help():
    print_warning(format_cmd_print("sigma_server", "Executa o servidor."))
    print_warning(format_cmd_print("sigma_run_migrations", "Faz upgrade do banco de dados."))
    print_warning(format_cmd_print("sigma_run_tests", "Executa os testes do sistema."))
    print_warning(format_cmd_print("sigma_update_postgres_env", "Gera um novo arquivo environment."))
    print_warning(format_cmd_print("sigma_update_settings", "Gera os arquivos development.ini e production.ini. Usa sigma.ini como base."))
    print_warning(format_cmd_print("sigma_update_static", "Processa os arquivos estáticos da pasta static_full e os copia para a pasta static."))
    print_warning(format_cmd_print("sigma", "Ativa o ambiente virtual do sigma e muda para o diretório do projeto."))
    print_warning("Para entrar manualmente no ambiente virtual, use o comando:", end=" ")
    msg = "source {}/bin/activate".format(VENV)
    print(Colors.BLUE + Colors.BOLD + msg + Colors.ENDC)
    msg = "Caso o comando sigma não seja reconhecido, feche esse terminal e "
    msg += "abra novamente."
    print_warning(Colors.BOLD + msg)


def important_message():
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
    if answer in POSITIVE_ANSWER:
        return True
    else:
        return False

def run_migrations():
    print_info("Executando migrações...")
    if _database_exists() is False:
        cmd = ACTIVATE_VENV
        cmd += "cd {}; python sigma/migrations/sprint_1.py {};"
        cmd = cmd.format(SIGMA_DIR, INI_FILE)
        call(cmd, True)
    cmd = ACTIVATE_VENV + "cd {}; sigma_run_migrations -b {}"
    cmd = cmd.format(SIGMA_DIR, INI_FILE)
    call(cmd, True)


def make_commands():
    print_info("Criando comandos personalizados...")
    sigma = "alias sigma='{} cd {}'\n"
    sigma = sigma.format(ACTIVATE_VENV, SIGMA_DIR)
    sigmalib = "alias sigmalib='{} cd {}'\n"
    sigmalib = sigmalib.format(ACTIVATE_VENV, SIGMALIB_DIR)
    if os.path.exists(BASHRC) is True:
        with open(BASHRC, "r+") as f:
            # Se o alias ainda não foi criado. Crie-o.
            if sigma not in f.read():
                f.write("# Alias criado pelo comando prepdev do sigma.\n")
                f.write(sigma)
            if sigmalib not in f.read():
                f.write(sigmalib)
    else:
        with open(BASHRC, "w") as f:
            f.write("# Alias criado pelo comando prepdev do sigma.\n")
            f.write(sigma)
            f.write(sigmalib)


def pre_process_sql(filename):
    """
    Faz o pré-processamento do arquivo sql.

    Durante o pré-processamento as {variáveis} informadas no arquivo são
    substituídas.

    Retorna o path do arquivo pré-processado.
    """
    sqls = None
    with open(filename, "r") as sql_file:
        sqls = sql_file.read()
        sqls = sqls.format(**VARIABLES)
    sql_temp = NamedTemporaryFile(delete=False)
    sql_temp.write(bytes(sqls, 'utf-8'))
    sql_temp.seek(0)
    return sql_temp.name


def populate_db():
    msg = "Deseja carregar os dados de desenvolvimento no banco de dados? ([" + Colors.BOLD + "S]" + Colors.ENDC + Colors.WARNING + "/n)" + Colors.ENDC
    answer = input(Colors.WARNING + msg + Colors.ENDC)
    if answer == "":
        answer = "s"
    if answer in POSITIVE_ANSWER:
        sqls = os.path.join(SIGMA_DIR, "sigma", "sql", "dev")
        for files in reversed(list(os.walk(sqls, topdown=False))):
            # O comando walk retorna tuplas no seguinte formato [dirpath, dirnames, filenames]
            for sql in files[-1]:
                if ".sql" in sql[-4:]:
                    sql_file = files[0] + "/" + sql
                    sql_file = pre_process_sql(sql_file)
                    call("psql -h localhost -U postgres -d {} -f {}".format(DATABASE_NAME, sql_file), True)


def postgres_warning():
    print("{:#^80}".format("Atenção"))
    print_warning("As seguintes linhas devem estar presentes no pg_hba.conf" + Colors.BOLD + "(na mesma ordem)" + Colors.ENDC + Colors.WARNING + ":")
    print(Colors.BLUE + "host    all             postgres        127.0.0.1/32            trust" + Colors.ENDC)
    print(Colors.BLUE + "host    all             all             127.0.0.1/32            md5" + Colors.ENDC)


def run():
    if important_message() is True:
        # def_install_path()
        # if is_valid_postgresql_version() is False:
        #     msg = Colors.FAIL + "Versão inválida do postgresql detectada."
        #     msg += Colors.GREEN + " Versão mínima aceita: {}.{}" + Colors.ENDC
        #     exit(msg.format(MIN_POSTGRES_VERSION[0], MIN_POSTGRES_VERSION[1]))
        # search_dependencies()
        # create_ssh_keys()
        # create_ssh_config()
        # if github_configured() is False:
        #     sys.exit(-1)
        # clone_sigma()
        # clone_sigmalib()
        # so_dependencies()
        # create_venv()
        # update_packages()
        # setup_develop()
        # install_sigmalib()
        close_connections()
        prepare_database()
        run_migrations()
        populate_db()
        make_commands()
        finish()
        print_help()
        postgres_warning()
    else:
        print_warning("Configure o postgresql para aceitar conexões confiáveis vindas de localhost(" + Colors.BLUE + "/etc/postgresql/<version>/pg_hba.conf" + Colors.GREEN + ").")
        postgres_warning()


if __name__ == "__main__":
    # run()
    instance = Prepdev()
    try:
        instance.run()
    except Exception as exc:
        print_warning(exc.args[0])
