# Quoridor

Implementacao em Python do jogo de tabuleiro Quoridor para 2 ou 4 jogadores, com suporte a partidas locais e partidas distribuidas em rede. O projeto conta com duas modalidades de interface: grafica (baseada em Pygame) e console (baseada em linha de comando/CLI).

A camada de rede utiliza chamada de procedimento remoto (RPC) via biblioteca Pyro5, operando com arquitetura de callbacks bidirecionais assincronos e sincronizacao de estado thread-safe.

---

## Indice

1. [Visao Geral e Arquitetura](#visao-geral-e-arquitetura)
2. [Regras e Mecanicas do Jogo](#regras-e-mecanicas-do-jogo)
3. [Camada de Rede (Pyro5)](#camada-de-rede-pyro5)
4. [Dependencias e Instalacao](#dependencias-e-instalacao)
5. [Instrucoes de Execucao](#instrucoes-de-execucao)
   - [Partida Local](#partida-local)
   - [Partida em Rede](#partida-em-rede)
6. [Controles e Comandos](#controles-e-comandos)
   - [Interface Grafica (Pygame)](#interface-grafica-pygame)
   - [Interface de Linha de Comando (CLI)](#interface-de-linha-de-comando-cli)
7. [Estrutura do Repositorio](#estrutura-do-repositorio)

---

## Visao Geral e Arquitetura

O sistema e estruturado em tres camadas independentes, seguindo o principio de separacao de responsabilidades:

- **`core/` (Logica de Dominio):** Nao possui dependencias de interface visual nem de rede. Contem as definicoes de modelos de dados (`Player`, `Wall`), a maquina de estados das regras do Quoridor (`QuoridorGame`) e os algoritmos de grafos e conectividade (`has_path_to_goal`).
- **`network/` (Comunicacao Distribuida):** Implementa o servidor remoto (`QuoridorServer`), o cliente RPC (`QuoridorClient`), o manipulador de callbacks remotos (`GameClientCallback`), a configuracao de serializadores customizados (`network.config`) e o protocolo de serializacao do estado (`network.protocol`).
- **`ui/` (Apresentacao):** Prove duas formas de interacao desacopladas da logica central:
  - `ui/gui.py`: Renderizacao grafica com Pygame, com layout responsivo e anti-aliasing via supersampling.
  - `ui/cli.py`: Renderizacao em texto para terminal, com interpretador de comandos.

---

## Regras e Mecanicas do Jogo

O jogo segue as regras formais do Quoridor:

### Tabuleiro e Coordenadas

- O tabuleiro e composto por uma grade de 9x9 casas (indices de linha e coluna de 0 a 8).
- As paredes sao posicionadas nas ranhuras entre as casas. A grade de paredes tem dimensao 8x8 (indices de 0 a 7), correspondendo ao vertice superior/esquerdo da barreira. Cada parede ocupa o comprimento equivalente a duas casas.

### Participantes e Metas

- **Partidas com 2 jogadores:** Cada jogador inicia com 10 paredes.
  - Jogador 1 (P1): Inicia em (0, 4) e vence ao atingir qualquer casa da linha 8.
  - Jogador 2 (P2): Inicia em (8, 4) e vence ao atingir qualquer casa da linha 0.
- **Partidas com 4 jogadores:** Cada jogador inicia com 5 paredes.
  - Jogador 1 (P1): Inicia em (0, 4), meta linha 8.
  - Jogador 2 (P2): Inicia em (8, 4), meta linha 0.
  - Jogador 3 (P3): Inicia em (4, 0), meta coluna 8.
  - Jogador 4 (P4): Inicia em (4, 8), meta coluna 0.

### Movimentacao de Peoes

Em cada turno, o jogador pode movimentar seu peao ou colocar uma parede:

- **Movimento Simples:** Deslocamento de 1 casa em linha reta (ortogonal), desde que nao haja parede bloqueando o trajeto e a casa de destino nao esteja ocupada.
- **Salto Reto:** Se houver um peao adversario na casa adjacente e a casa diretamente atras dele estiver livre e sem bloqueio de parede, o jogador pode saltar sobre ele (avanco de 2 casas).
- **Salto Diagonal:** Se o salto reto estiver impedido por uma parede ou pela borda do tabuleiro, o peao pode saltar para as casas diagonais adjacentes ao peao adversario (desde que nao haja paredes bloqueando o trajeto).

### Posicionamento de Paredes e Validacao de Caminho

A colocacao de paredes obedece aos seguintes criterios:

1. Posição dentro dos limites da grade de paredes (0 a 7 tanto para linha quanto para coluna).
2. Orientacao valida: horizontal (`H`) ou vertical (`V`).
3. Proibicao de sobreposicao com paredes ja existentes na mesma orientacao.
4. Proibicao de cruzamento perpendicular no mesmo ponto central de ancoragem.
5. **Garantia de Caminho Livre:** Uma parede nao pode isolar completamente nenhum jogador. O modulo `core/pathfinding.py` executa uma Busca em Largura (BFS) simulando a adicao da parede antes de efetiva-la; caso o caminho de qualquer jogador ativo ate sua borda meta seja interrompido, a jogada e recusada como ilegal.

### Eliminacao e Resiliencia

Caso um jogador se desconecte ou saia durante a partida em andamento, ele e marcado como inativo (`is_active = False`). O jogo recalcula o proximo turno entre os remanescentes. Se restar apenas um jogador ativo, a partida e declarada encerrada com vitoria imediata por W.O.

---

## Camada de Rede (Pyro5)

A comunicacao cliente-servidor opera sob o modelo de objetos distribuidos:

```text
[ Cliente 1 (QuoridorClient) ] <----\
  - Daemon local de Callback         \     Pyro5 RPC (TCP)
                                      +--> [ Servidor (QuoridorServer) ]
[ Cliente 2 (QuoridorClient) ] <-----/     - Singleton thread-safe
  - Daemon local de Callback               - Name Server (pyro5-ns)
```

1. **Resolucao de Nomes:** O servidor se registra em um Pyro5 Name Server com um identificador amigavel (padrao: `quoridor.servidor`). Os clientes localizam o servidor via `PYRONAME:quoridor.servidor`.
2. **Callbacks Assincronos Bidirecionais:** Cada cliente inicializa um Daemon Pyro5 proprio em thread secundaria e fornece seu URI de callback no momento da conexao. Metodos de notificacao do cliente sao decorados com `@Pyro5.api.oneway`, impedindo que atrasos em um cliente bloqueiem a thread do servidor.
3. **Concorrencia e Seguranca:** O servidor opera com `instance_mode="single"`, sincronizando mutacoes no estado atraves de `threading.Lock()`.
4. **Serializacao:** As classes `Player` e `Wall` sao registradas explicitamente no subsistema de serializacao Serpent do Pyro5 em `network/config.py`.

---

## Dependencias e Instalacao

O projeto requer **Python 3.10** ou superior.

### 1. Clonar o repositorio

```bash
git clone <url-do-repositorio>
cd quoridor
```

### 2. Criar e ativar o ambiente virtual

No Linux / macOS:

```bash
python3 -m venv venv
source venv/bin/activate
```

No Windows (PowerShell):

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

Dependencias diretas:

- `pygame >= 2.6.0`: Renderizacao grafica 2D, tratamento de eventos e fontes.
- `Pyro5 >= 5.15`: Middleware de comunicacao remota (RPC).
- `serpent >= 1.40`: Serializador de estruturas de dados para Pyro5.

---

## Instrucoes de Execucao

### Partida Local

Para jogar localmente no mesmo computador, revezando o turno:

**Modo Grafico (Pygame):**

```bash
# Partida com 2 jogadores (padrao)
python local_game.py

# Partida com 4 jogadores
python local_game.py --players 4
```

**Modo Console (CLI):**

```bash
python local_game.py --cli --players 2
```

---

### Partida em Rede

Uma partida em rede requer a inicializacao de uma instancia do servidor e duas ou quatro instancias do cliente.

#### 1. Iniciar o Servidor

O servidor gerencia o Name Server do Pyro5 automaticamente caso nao haja um em execucao.

```bash
python run_server.py
```

Opcoes de linha de comando do servidor:

- `--server-name <nome>`: Nome amigavel registrado no Name Server (padrao: `quoridor.servidor`).
- `--host <ip>`: Endereco de rede para bind do servidor (padrao: `localhost`).
- `--port <porta>`: Porta do servidor (padrao: `0` para porta dinamica).
- `--ns-host <ip>`: Host do Name Server Pyro5 (padrao: `localhost`).
- `--ns-port <porta>`: Porta do Name Server Pyro5 (padrao: `9090`).
- `--no-auto-ns`: Desativa a inicializacao automatica do Name Server embutido.

#### 2. Conectar os Clientes

Abra um terminal para cada jogador:

**Jogador 1 (Interface Grafica):**

```bash
python run_client.py --name "Alice"
```

**Jogador 2 (Interface Grafica):**

```bash
python run_client.py --name "Bob"
```

**Conexao via Terminal (CLI):**
Qualquer cliente pode optar por rodar em linha de comando passando a flag `--cli`:

```bash
python run_client.py --name "Carlos" --cli
```

Opcoes de linha de comando do cliente:

- `--name <nome>`: Nome do jogador.
- `--server-name <nome>`: Nome do servidor registrado no Name Server.
- `--ns-host <ip>`: Host do Name Server Pyro5.
- `--ns-port <porta>`: Porta do Name Server Pyro5.
- `--cli`: Ativa a interface em modo texto no terminal.

Ao atingir a quantidade necessaria de participantes no lobby (2 ou 4), qualquer jogador pode iniciar a partida pressionando `ENTER` ou `ESPACO` (GUI) ou digitando `start` (CLI).

---

## Controles e Comandos

### Interface Grafica (Pygame)

| Acao | Entrada |
| --- | --- |
| Mover peao | Clicar com o botao esquerdo em uma casa valida |
| Alternar modo (Mover / Parede) | Pressionar barra de `ESPACO` |
| Rotacionar parede (Horizontal / Vertical) | Pressionar tecla `R` ou clicar com botao direito |
| Posicionar parede | Clicar com o botao esquerdo no slot desejado (modo parede ativo) |
| Iniciar partida (Lobby) | Pressionar `ENTER` ou `ESPACO` |
| Reiniciar partida apos fim de jogo | Pressionar `ENTER` |
| Encerrar o jogo | Pressionar `ESC` ou fechar a janela |

A interface grafica exibe:

- Marcadores de destino com a cor correspondente a borda que o peao deve atingir.
- Indicador visual translucido (ghost) da parede sob o cursor (amarelo para posicoes validas, vermelho para posicoes ilegais).
- Projecao de movimentos e saltos permitidos para o turno corrente.
- Cards laterais com contagem regressiva de paredes e estado dos jogadores.

### Interface de Linha de Comando (CLI)

No prompt do console:

- `m <linha> <coluna>` ou `<linha> <coluna>`: Move o peao para as coordenadas especificadas (ex: `m 1 4` ou `1 4`).
- `w <linha> <coluna> <H|V>` ou `p <linha> <coluna> <H|V>`: Posiciona parede na coordenada e orientacao indicadas (ex: `w 3 3 H`).
- `start` ou `s`: Inicia a partida enquanto estiver no lobby.
- `sair` ou `q`: Desconecta da sala ou encerra a partida local.

---

## Estrutura do Repositorio

```text
quoridor/
├── core/
│   ├── __init__.py
│   ├── game.py            # Maquina de estados, regras do Quoridor e movimentacao
│   ├── models.py          # Dataclasses Wall e Player
│   └── pathfinding.py     # Busca em Largura (BFS) para garantia de caminho livre
├── network/
│   ├── __init__.py
│   ├── client.py          # Cliente QuoridorClient e callbacks GameClientCallback
│   ├── config.py          # Parametros de rede e configuracao de serializadores Pyro5
│   ├── protocol.py        # Serializacao e desserializacao do estado do jogo
│   └── server.py          # Servidor QuoridorServer e gerenciamento de conexoes
├── ui/
│   ├── __init__.py
│   ├── cli.py             # Interface baseada em console (CLI)
│   ├── constants.py       # Paleta de cores, FPS e dimensoes
│   ├── gui.py             # Interface grafica interativa em Pygame
│   └── utils.py           # Funcoes utilitarias de desenho e anti-aliasing
├── local_game.py          # Ponto de entrada para partidas locais
├── run_client.py          # Ponto de entrada do cliente multiplayer
├── run_server.py          # Ponto de entrada do servidor multiplayer
├── requirements.txt       # Dependencias do projeto
└── README.md              # Documentacao do sistema
```
