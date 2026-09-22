"""
Servidor HTTP local da Interface Web.

Decisões (seções 10, 11 e 15 do pedido):
  - Só biblioteca padrão (http.server + threading): nada novo para instalar
    nem para empacotar no .exe.
  - Escuta em 127.0.0.1 por padrão (só este computador acessa). Porta e
    endereço vêm de settings["web"]; se a porta estiver ocupada, tenta as 10
    seguintes.
  - Chave de acesso aleatória a cada execução: o link aberto no navegador a
    contém; na primeira visita ela vira um cookie HttpOnly/SameSite=Strict e
    some da barra de endereço. Sem a chave, nenhuma rota da API responde.
  - Proteções contra sites maliciosos abertos no mesmo navegador: checagem do
    cabeçalho Host (bloqueia DNS rebinding), cabeçalho obrigatório
    X-Requested-With nas chamadas da API (força preflight CORS, que nunca é
    autorizado — bloqueia CSRF) e Content-Security-Policy restritiva.
"""
from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import socket
import sys
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlsplit

from app.utils.paths import pasta_recursos
from app.web.estado import ErroApi, EstadoWeb

NOME_COOKIE = "sniper_chave"
CABECALHO_API = "X-Requested-With"
VALOR_CABECALHO_API = "SIGAA-Sniper"
TAMANHO_MAX_CORPO = 2 * 1024 * 1024  # 2 MB — suficiente para importar configuração
TENTATIVAS_PORTA = 10

ARQUIVOS_ESTATICOS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/static/app.css": ("app.css", "text/css; charset=utf-8"),
    "/static/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/static/icone.svg": ("icone.svg", "image/svg+xml"),
}

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; "
    "form-action 'self'; frame-ancestors 'none'"
)

PAGINA_SEM_CHAVE = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>SIGAA Sniper — acesso</title>
<link rel="stylesheet" href="/static/app.css"></head><body class="pagina-simples"><main class="cartao-simples">
<h1>🔒 Link de acesso necessário</h1>
<p>Por segurança, a Interface Web só abre pelo link completo exibido no terminal do SIGAA Sniper
(ele contém uma chave de acesso gerada nesta execução).</p>
<p>Volte à janela do terminal e copie o endereço que começa com <code>http://127.0.0.1</code>.</p>
</main></body></html>"""

PASTA_ESTATICOS = os.path.join("app", "web", "static")


def _pasta_estaticos() -> str:
    return os.path.join(pasta_recursos(), PASTA_ESTATICOS)


def _eh_loopback(host: str) -> bool:
    return host in ("127.0.0.1", "localhost", "::1") or host.startswith("127.")


class _Rota:
    def __init__(self, metodo: str, padrao: str, funcao: Callable, exige_aviso: bool = True):
        self.metodo = metodo
        self.regex = re.compile("^" + padrao + "$")
        self.funcao = funcao
        self.exige_aviso = exige_aviso


def _montar_rotas(e: EstadoWeb):
    def corpo(f):  # adapta funções que recebem só o corpo JSON
        return lambda _m, _q, dados: f(dados)

    def sem_args(f):
        return lambda _m, _q, _d: f()

    return [
        _Rota("GET", r"/api/estado", sem_args(e.estado), exige_aviso=False),
        _Rota("GET", r"/api/aviso-legal", sem_args(e.aviso_legal), exige_aviso=False),
        _Rota("POST", r"/api/aviso-legal/aceitar", corpo(e.aceitar_aviso), exige_aviso=False),
        _Rota("POST", r"/api/aviso-legal/recusar", sem_args(e.recusar_aviso), exige_aviso=False),

        _Rota("GET", r"/api/credenciais", sem_args(e.credenciais)),
        _Rota("POST", r"/api/credenciais", corpo(e.salvar_credenciais)),
        _Rota("POST", r"/api/credenciais/limpar", sem_args(e.limpar_credenciais)),

        _Rota("GET", r"/api/disciplinas", sem_args(e.listar_disciplinas)),
        _Rota("POST", r"/api/disciplinas", corpo(e.adicionar_disciplina)),
        _Rota("POST", r"/api/disciplinas/(\d+)/editar", lambda m, _q, d: e.editar_disciplina(int(m.group(1)), d)),
        _Rota("POST", r"/api/disciplinas/(\d+)/remover", lambda m, _q, d: e.remover_disciplina(int(m.group(1)), d)),
        _Rota("POST", r"/api/disciplinas/(\d+)/alternar", lambda m, _q, d: e.alternar_disciplina(int(m.group(1)), d)),
        _Rota("GET", r"/api/departamentos", lambda _m, q, _d: e.buscar_departamentos(q.get("q", [""])[0])),

        _Rota("GET", r"/api/execucao", sem_args(e.status_execucao)),
        _Rota("POST", r"/api/execucao/iniciar", corpo(e.iniciar)),
        _Rota("POST", r"/api/execucao/parar", sem_args(e.parar)),

        _Rota("GET", r"/api/dashboard", sem_args(e.dashboard)),
        _Rota("GET", r"/api/logs", lambda _m, q, _d: e.logs(int(q.get("desde", ["0"])[0] or 0))),
        _Rota("POST", r"/api/logs/abrir-arquivo", sem_args(e.abrir_arquivo_log)),

        _Rota("GET", r"/api/notificacoes", sem_args(e.notificacoes)),
        _Rota("POST", r"/api/notificacoes", corpo(e.salvar_notificacoes)),
        _Rota("POST", r"/api/notificacoes/persistencia", corpo(e.alterar_persistencia_notificacoes)),
        _Rota("POST", r"/api/notificacoes/testar", corpo(e.testar_notificacoes)),

        _Rota("GET", r"/api/avancado", sem_args(e.avancado)),
        _Rota("POST", r"/api/avancado", corpo(e.salvar_avancado)),
        _Rota("POST", r"/api/avancado/restaurar", corpo(e.restaurar)),
        _Rota("POST", r"/api/avancado/limpar-dumps", sem_args(e.limpar_dumps)),
        _Rota("POST", r"/api/config/importar/previa", corpo(e.previa_importacao)),
        _Rota("POST", r"/api/config/importar/aplicar", corpo(e.aplicar_importacao)),

        _Rota("POST", r"/api/diagnostico/completo", sem_args(e.diagnostico_completo)),
        _Rota("POST", r"/api/diagnostico/camadas", sem_args(e.diagnostico_camadas)),

        _Rota("GET", r"/api/experimental", sem_args(e.experimentos)),
        _Rota("POST", r"/api/experimental/executar", corpo(e.executar_experimento)),

        _Rota("GET", r"/api/ajuda", sem_args(e.ajuda)),
        _Rota("GET", r"/api/sobre", sem_args(e.sobre)),
        _Rota("POST", r"/api/sobre/atalho", sem_args(e.criar_atalho)),

        _Rota("POST", r"/api/assistente/finalizar", corpo(e.finalizar_assistente)),
        _Rota("POST", r"/api/encerrar", corpo(e.encerrar), exige_aviso=False),
    ]


class _Handler(BaseHTTPRequestHandler):
    server: "ServidorWeb"
    # HTTP/1.0 = uma conexão por requisição. Com keep-alive, threads presas a
    # conexões abertas pelo navegador continuariam vivas (e respondendo) depois
    # que a Interface Web fosse encerrada e o programa voltasse ao menu.
    protocol_version = "HTTP/1.0"
    server_version = "SIGAA-Sniper"
    sys_version = ""

    # ── infraestrutura ────────────────────────────────────────────────────

    def log_message(self, formato, *args):  # silencia o log de acesso no console
        return

    def _cabecalhos_seguranca(self):
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")

    def _responder(self, status: int, corpo: bytes, tipo: str, extras: Optional[Dict[str, str]] = None):
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self._cabecalhos_seguranca()
        for chave, valor in (extras or {}).items():
            self.send_header(chave, valor)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corpo)

    def _json(self, status: int, dados: Any, extras: Optional[Dict[str, str]] = None):
        corpo = json.dumps(dados, ensure_ascii=False, default=str).encode("utf-8")
        self._responder(status, corpo, "application/json; charset=utf-8", extras)

    def _erro(self, status: int, mensagem: str, **extra):
        self._json(status, {"ok": False, "erro": mensagem, **extra})

    def _host_permitido(self) -> bool:
        host = (self.headers.get("Host") or "").strip().lower()
        return host in self.server.hosts_permitidos or self.server.aceita_qualquer_host

    def _chave_valida(self) -> bool:
        cookies = self.headers.get("Cookie") or ""
        for parte in cookies.split(";"):
            nome, _, valor = parte.strip().partition("=")
            if nome == NOME_COOKIE and hmac.compare_digest(valor, self.server.chave):
                return True
        return False

    # ── GET / HEAD / POST ────────────────────────────────────────────────

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        self._tratar("GET")

    def do_POST(self):
        self._tratar("POST")

    def _tratar(self, metodo: str):
        try:
            if not self._host_permitido():
                self._erro(HTTPStatus.MISDIRECTED_REQUEST, "Host não permitido.")
                return
            url = urlsplit(self.path)
            if url.path.startswith("/api/"):
                self._api(metodo if metodo != "HEAD" else "GET", url)
            elif metodo in ("GET", "HEAD"):
                self._estatico(url)
            else:
                self._erro(HTTPStatus.METHOD_NOT_ALLOWED, "Método não permitido.")
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # navegador fechou a conexão no meio — nada a fazer
        except Exception as e:  # nunca derruba o servidor por causa de uma requisição
            try:
                self._erro(HTTPStatus.INTERNAL_SERVER_ERROR, f"Erro interno inesperado: {type(e).__name__}: {e}")
            except Exception:
                pass

    def _estatico(self, url):
        if url.path == "/":
            chave = parse_qs(url.query).get("chave", [""])[0]
            if chave:
                if hmac.compare_digest(chave, self.server.chave):
                    # Troca a chave da URL por um cookie e limpa a barra de endereço.
                    self._responder(HTTPStatus.SEE_OTHER, b"", "text/plain; charset=utf-8", {
                        "Location": "/",
                        "Set-Cookie": f"{NOME_COOKIE}={self.server.chave}; HttpOnly; SameSite=Strict; Path=/",
                    })
                    return
            if not self._chave_valida():
                self._responder(HTTPStatus.FORBIDDEN, PAGINA_SEM_CHAVE.encode("utf-8"), "text/html; charset=utf-8")
                return

        arquivo = ARQUIVOS_ESTATICOS.get(url.path)
        if arquivo is None:
            self._erro(HTTPStatus.NOT_FOUND, "Não encontrado.")
            return
        nome, tipo = arquivo
        try:
            with open(os.path.join(_pasta_estaticos(), nome), "rb") as f:
                conteudo = f.read()
        except OSError:
            self._erro(HTTPStatus.INTERNAL_SERVER_ERROR, f"Arquivo da interface ausente: {nome}")
            return
        self._responder(HTTPStatus.OK, conteudo, tipo)

    def _ler_corpo(self) -> Dict[str, Any]:
        try:
            tamanho = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ErroApi(400, "Content-Length inválido.")
        if tamanho > TAMANHO_MAX_CORPO:
            # Descarta o corpo antes de responder: sem isso o Windows derruba a
            # conexão (WinError 10053) e o navegador vê "servidor fora do ar"
            # em vez de uma mensagem de erro clara.
            restante = min(tamanho, 50 * 1024 * 1024)
            while restante > 0:
                pedaco = self.rfile.read(min(65536, restante))
                if not pedaco:
                    break
                restante -= len(pedaco)
            raise ErroApi(413, "Arquivo grande demais (máximo de 2 MB).")
        if tamanho == 0:
            return {}
        tipo = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if tipo != "application/json":
            raise ErroApi(415, "Envie os dados como JSON.")
        bruto = self.rfile.read(tamanho)
        try:
            dados = json.loads(bruto.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ErroApi(400, "JSON inválido.")
        if not isinstance(dados, dict):
            raise ErroApi(400, "Formato inválido: esperado um objeto JSON.")
        return dados

    def _api(self, metodo: str, url):
        if not self._chave_valida():
            self._erro(HTTPStatus.UNAUTHORIZED, "Acesso não autorizado. Abra a Interface Web pelo link exibido no terminal.")
            return
        if self.headers.get(CABECALHO_API) != VALOR_CABECALHO_API:
            self._erro(HTTPStatus.FORBIDDEN, "Requisição recusada (cabeçalho de segurança ausente).")
            return

        estado = self.server.estado

        # Downloads (respostas que não são JSON)
        if metodo == "GET" and url.path == "/api/config/exportar":
            if not estado.aviso_aceito:
                self._erro(HTTPStatus.FORBIDDEN, "Aceite o aviso legal primeiro.", aviso_pendente=True)
                return
            self._responder(HTTPStatus.OK, estado.exportar_configuracao(), "application/json; charset=utf-8",
                            {"Content-Disposition": 'attachment; filename="sigaa_sniper_config.json"'})
            return
        if metodo == "GET" and url.path == "/api/logs/arquivo":
            if not estado.aviso_aceito:
                self._erro(HTTPStatus.FORBIDDEN, "Aceite o aviso legal primeiro.", aviso_pendente=True)
                return
            caminho = estado.caminho_log()
            if not os.path.exists(caminho):
                self._erro(HTTPStatus.NOT_FOUND, "O arquivo de log ainda não existe (nenhuma execução foi feita).")
                return
            with open(caminho, "rb") as f:
                conteudo = f.read()
            self._responder(HTTPStatus.OK, conteudo, "application/json; charset=utf-8",
                            {"Content-Disposition": 'attachment; filename="sigaa_sniper_audit.json"'})
            return

        try:
            dados = self._ler_corpo() if metodo == "POST" else {}
        except ErroApi as erro:
            self.close_connection = True  # corpo possivelmente não lido por inteiro
            self._erro(erro.status, erro.mensagem, **erro.extra)
            return
        query = parse_qs(url.query)

        for rota in self.server.rotas:
            if rota.metodo != metodo:
                continue
            m = rota.regex.match(url.path)
            if not m:
                continue
            if rota.exige_aviso and not estado.aviso_aceito:
                self._erro(HTTPStatus.FORBIDDEN, "Aceite o aviso legal primeiro.", aviso_pendente=True)
                return
            try:
                resultado = rota.funcao(m, query, dados)
            except ErroApi as erro:
                self._erro(erro.status, erro.mensagem, **erro.extra)
                return
            self._json(HTTPStatus.OK, resultado)
            return

        self._erro(HTTPStatus.NOT_FOUND, "Rota não encontrada.")


class ServidorWeb(ThreadingHTTPServer):
    daemon_threads = True
    # No Windows, SO_REUSEADDR permite que DOIS programas escutem a mesma porta
    # sem erro (o segundo "rouba" conexões). Desligado lá, e SO_EXCLUSIVEADDRUSE
    # ligado, para que uma porta ocupada seja detectada de verdade.
    allow_reuse_address = sys.platform != "win32"

    def __init__(self, estado: EstadoWeb, host: str, porta: int):
        self.estado = estado
        self.chave = secrets.token_urlsafe(24)
        self.rotas = _montar_rotas(estado)
        super().__init__((host, porta), _Handler)
        porta_real = self.server_address[1]
        self.aceita_qualquer_host = not _eh_loopback(host)
        self.hosts_permitidos = {f"127.0.0.1:{porta_real}", f"localhost:{porta_real}", f"[::1]:{porta_real}", f"{host}:{porta_real}".lower()}

    def server_bind(self):
        if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    @property
    def porta(self) -> int:
        return self.server_address[1]


def criar_servidor(estado: EstadoWeb, host: str, porta: int, tentativas: int = TENTATIVAS_PORTA) -> ServidorWeb:
    """Cria o servidor na porta pedida ou, se ocupada, numa das seguintes."""
    ultimo_erro: Optional[OSError] = None
    for deslocamento in range(max(1, tentativas)):
        try:
            return ServidorWeb(estado, host, porta + deslocamento if porta else 0)
        except OSError as e:
            ultimo_erro = e
            if not porta:
                break
    raise OSError(f"Não foi possível abrir a Interface Web em {host}:{porta} (nem nas {tentativas - 1} portas seguintes): {ultimo_erro}")


def url_de_acesso(servidor: ServidorWeb, host: str) -> Tuple[str, str]:
    """(endereço base, link completo com a chave de acesso)."""
    host_url = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host
    if ":" in host_url and not host_url.startswith("["):
        host_url = f"[{host_url}]"
    base = f"http://{host_url}:{servidor.porta}"
    return base, f"{base}/?chave={servidor.chave}"


def _aguardar_encerramento(evento: threading.Event) -> None:
    """Espera ENTER no terminal OU o botão "Encerrar" na página.

    Em terminal interativo não usa input() numa thread — isso deixaria uma
    leitura pendurada competindo com o menu depois que a Web fosse encerrada
    pelo navegador. No Windows usa msvcrt; em outros sistemas, select."""
    entrada = sys.stdin
    interativo = bool(entrada) and hasattr(entrada, "isatty") and entrada.isatty()

    if not interativo:
        def ler():
            try:
                entrada.readline() if entrada else None
            except Exception:
                return
            evento.set()
        if entrada:
            threading.Thread(target=ler, daemon=True).start()
        while not evento.wait(0.3):
            pass
        return

    if os.name == "nt":
        import msvcrt
        while not evento.wait(0.2):
            while msvcrt.kbhit():
                tecla = msvcrt.getwch()
                if tecla in ("\r", "\n"):
                    evento.set()
        return

    import select
    while not evento.is_set():
        prontos, _, _ = select.select([entrada], [], [], 0.2)
        if prontos:
            entrada.readline()
            evento.set()


def executar_interface_web(abrir_navegador: Optional[bool] = None) -> None:
    """Ponto de entrada do modo Web (opção [0] do menu). Bloqueia até o
    usuário encerrar (ENTER no terminal, botão "Encerrar" na página, recusar o
    aviso legal ou Ctrl+C) e então volta ao menu."""
    estado = EstadoWeb()
    cfg_web = estado.settings.get("web", {})
    host = str(cfg_web.get("host") or "127.0.0.1")
    porta = int(cfg_web.get("porta") or 8765)
    if abrir_navegador is None:
        abrir_navegador = bool(cfg_web.get("abrir_navegador", True))

    try:
        servidor = criar_servidor(estado, host, porta)
    except OSError as e:
        print(f"\n❌ {e}")
        print("Altere a porta em Configurações Avançadas (GUI) ou em config/settings.json → \"web\": {\"porta\": ...}.")
        estado.finalizar()
        input("\nPressione ENTER para voltar ao menu...")
        return

    base, link = url_de_acesso(servidor, host)
    thread = threading.Thread(target=servidor.serve_forever, kwargs={"poll_interval": 0.3}, name="InterfaceWeb", daemon=True)
    thread.start()

    print("\n" + "=" * 62)
    print("  🌐 INTERFACE WEB (modo recomendado) — em execução")
    print("=" * 62)
    print(f"\n  Endereço:  {base}")
    print("  Abra ESTE link completo (contém a chave de acesso desta execução):\n")
    print(f"  {link}\n")
    if servidor.porta != porta:
        print(f"  (a porta {porta} estava ocupada — usando {servidor.porta})\n")
    if not _eh_loopback(host):
        print("  ⚠️  ATENÇÃO: o servidor está aceitando conexões de OUTROS computadores da rede")
        print(f"     (host configurado: {host}). O padrão seguro é 127.0.0.1.\n")
    print("  Pressione ENTER aqui (ou use o botão \"Encerrar\" na página) para")
    print("  encerrar a Interface Web e voltar ao menu.")
    print("=" * 62 + "\n", flush=True)

    if abrir_navegador:
        try:
            if not webbrowser.open(link):
                print("  (não foi possível abrir o navegador automaticamente — copie o link acima)")
        except Exception:
            print("  (não foi possível abrir o navegador automaticamente — copie o link acima)")

    try:
        _aguardar_encerramento(estado.evento_encerrar)
    except KeyboardInterrupt:
        pass
    finally:
        time.sleep(0.2)  # deixa a última resposta (ex: "Encerrar") chegar ao navegador
        servidor.shutdown()
        servidor.server_close()
        estado.finalizar()
        print("\nInterface Web encerrada. Credenciais apagadas da memória.", flush=True)
